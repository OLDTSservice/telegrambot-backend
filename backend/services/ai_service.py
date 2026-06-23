"""
知識庫 AI 服務
- 文件段落儲存於 SQLite（KnowledgeChunk / TeamsKnowledgeChunk）
- 以關鍵字評分找出相關段落，再呼叫 Claude 產生答案
- 完全不使用 ChromaDB/ONNX，記憶體佔用極低
"""
import os
import asyncio
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_anthropic_client = None


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _anthropic_client


# ── 文件解析 ────────────────────────────────────────────────────────────────

def _extract_text(file_path: str, ext: str) -> str:
    if ext == ".pdf":
        import PyPDF2
        text = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)

    elif ext in (".doc", ".docx"):
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext in (".xls", ".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        lines = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                lines.append("\t".join(str(c) if c is not None else "" for c in row))
        return "\n".join(lines)

    elif ext in (".txt", ".csv", ".md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    return ""


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 40):
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return chunks


# ── 文件處理（上傳時呼叫）──────────────────────────────────────────────────

async def process_document(file_path: str, ext: str, collection_name: str,
                           doc_id: int = None, bot_id: int = None,
                           db=None, platform: str = "telegram"):
    """
    解析文件並將段落存入 SQLite。
    collection_name 保留供相容，實際不使用 ChromaDB。
    """
    text = await asyncio.to_thread(_extract_text, file_path, ext)
    if not text.strip():
        raise ValueError("無法從文件中提取文字")

    chunks = _chunk_text(text)

    if db is not None and doc_id is not None and bot_id is not None:
        import models
        ChunkModel = models.TeamsKnowledgeChunk if platform == "teams" else models.KnowledgeChunk
        for i, chunk in enumerate(chunks):
            db.add(ChunkModel(doc_id=doc_id, bot_id=bot_id,
                              chunk_text=chunk, chunk_index=i))
        db.commit()
        logger.info(f"文件 doc_id={doc_id} 共 {len(chunks)} 個段落已存入 SQLite")


def delete_document_vectors(collection_name: str):
    """舊介面保留，ChromaDB 已移除，此處為空操作"""
    pass


# ── 關鍵字評分搜尋 ──────────────────────────────────────────────────────────

def _score_chunks(question: str, chunks) -> list[str]:
    """對段落以關鍵字出現次數評分，回傳前 5 名的文字"""
    words = [w.lower() for w in question.split() if len(w) > 1]
    scored = []
    for chunk in chunks:
        text_lower = chunk.chunk_text.lower()
        score = sum(text_lower.count(w) for w in words)
        if score > 0:
            scored.append((score, chunk.chunk_text))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:5]]


# ── 知識庫查詢（Telegram）────────────────────────────────────────────────────

def query_knowledge(bot_id: int, question: str, db) -> Optional[tuple]:
    import models
    logger.info(f"Telegram Bot {bot_id} 開始知識庫查詢：「{question[:50]}」")

    docs = db.query(models.KnowledgeDoc).filter(
        models.KnowledgeDoc.bot_id == bot_id,
        models.KnowledgeDoc.is_enabled == True
    ).all()

    if not docs:
        logger.info(f"Bot {bot_id} 無啟用的知識庫文件")
        return None

    doc_ids = [d.id for d in docs]
    all_chunks = db.query(models.KnowledgeChunk).filter(
        models.KnowledgeChunk.doc_id.in_(doc_ids)
    ).all()

    if not all_chunks:
        logger.warning(f"Bot {bot_id} 知識庫文件無段落資料（可能需重新上傳）")
        return None

    top_chunks = _score_chunks(question, all_chunks)
    if not top_chunks:
        logger.info(f"Bot {bot_id} 未找到相關段落")
        return None

    return _call_claude(question, top_chunks, bot_id)


# ── 知識庫查詢（Teams）───────────────────────────────────────────────────────

def query_teams_knowledge(bot_id: int, question: str, db) -> Optional[tuple]:
    import models
    logger.info(f"Teams Bot {bot_id} 開始知識庫查詢：「{question[:50]}」")

    docs = db.query(models.TeamsKnowledgeDoc).filter(
        models.TeamsKnowledgeDoc.bot_id == bot_id,
        models.TeamsKnowledgeDoc.is_enabled == True
    ).all()

    if not docs:
        return None

    doc_ids = [d.id for d in docs]
    all_chunks = db.query(models.TeamsKnowledgeChunk).filter(
        models.TeamsKnowledgeChunk.doc_id.in_(doc_ids)
    ).all()

    if not all_chunks:
        return None

    top_chunks = _score_chunks(question, all_chunks)
    if not top_chunks:
        return None

    return _call_claude(question, top_chunks, bot_id)


# ── 呼叫 Claude ──────────────────────────────────────────────────────────────

def _call_claude(question: str, chunks: list[str], bot_id: int) -> Optional[tuple]:
    context = "\n\n".join(chunks)
    logger.info(f"Bot {bot_id} 呼叫 Claude，context {len(context)} 字元")
    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "你是一個問答機器人。請根據以下知識庫內容，直接回答問題的答案，"
                    "不要加入任何額外補充、說明或開場白。"
                    "若知識庫中沒有相關資訊，只需回覆「抱歉，我找不到相關資訊。」\n\n"
                    f"知識庫內容：\n{context}\n\n"
                    f"問題：{question}\n\n答案："
                )
            }]
        )
        reply = message.content[0].text
        logger.info(f"Bot {bot_id} Claude 回覆成功，tokens: in={message.usage.input_tokens}")
        return reply, message.usage.input_tokens, message.usage.output_tokens
    except Exception as e:
        logger.error(f"Bot {bot_id} Claude API 失敗：{e}", exc_info=True)
        return None


# ── 使用量記錄 ────────────────────────────────────────────────────────────────

def record_usage(bot_id: int, input_tokens: int, output_tokens: int, db):
    import models
    today = date.today().isoformat()
    stat = db.query(models.UsageStat).filter(
        models.UsageStat.bot_id == bot_id,
        models.UsageStat.date == today
    ).first()
    if stat:
        stat.input_tokens += input_tokens
        stat.output_tokens += output_tokens
        stat.total_tokens += input_tokens + output_tokens
        stat.request_count += 1
    else:
        stat = models.UsageStat(
            bot_id=bot_id, date=today,
            input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens, request_count=1,
        )
        db.add(stat)
    db.commit()
