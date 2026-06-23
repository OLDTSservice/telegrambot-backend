import os
import asyncio
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_base_dir = "/data" if os.path.isdir("/data") else "."
CHROMA_PATH = os.path.join(_base_dir, "chroma_db")

_chroma_client = None
_anthropic_client = None

# 延遲載入，避免 import 時就崩潰
try:
    import anthropic as _anthropic_module
    import chromadb as _chromadb_module
    from chromadb.utils import embedding_functions as _ef_module
    _CHROMA_AVAILABLE = True
except Exception as e:
    logger.warning(f"chromadb/anthropic 載入失敗，知識庫 AI 功能暫不可用：{e}")
    _CHROMA_AVAILABLE = False


def get_chroma_client():
    global _chroma_client
    if not _CHROMA_AVAILABLE:
        raise RuntimeError("chromadb 不可用")
    if _chroma_client is None:
        _chroma_client = _chromadb_module.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def get_anthropic_client():
    global _anthropic_client
    if not _CHROMA_AVAILABLE:
        raise RuntimeError("anthropic 不可用")
    if _anthropic_client is None:
        _anthropic_client = _anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


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


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


async def process_document(file_path: str, ext: str, collection_name: str):
    if not _CHROMA_AVAILABLE:
        raise RuntimeError("知識庫功能不可用（chromadb 未載入）")
    text = await asyncio.to_thread(_extract_text, file_path, ext)
    if not text.strip():
        raise ValueError("無法從文件中提取文字")

    chunks = _chunk_text(text)
    client = get_chroma_client()
    ef = _ef_module.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(name=collection_name, embedding_function=ef)

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.add(documents=chunks, ids=ids)


def delete_document_vectors(collection_name: str):
    try:
        client = get_chroma_client()
        client.delete_collection(collection_name)
    except Exception:
        pass


def query_knowledge(bot_id: int, question: str, db) -> Optional[str]:
    """查詢知識庫並用 Claude 生成回覆，回傳 None 若無知識庫或不相關"""
    logger.info(f"Bot {bot_id} query_knowledge 開始，_CHROMA_AVAILABLE={_CHROMA_AVAILABLE}")
    if not _CHROMA_AVAILABLE:
        logger.warning(f"Bot {bot_id} chromadb/anthropic 不可用，跳過知識庫查詢")
        return None
    import models as m
    docs = db.query(m.KnowledgeDoc).filter(
        m.KnowledgeDoc.bot_id == bot_id,
        m.KnowledgeDoc.is_enabled == True
    ).all()

    if not docs:
        return None

    client = get_chroma_client()
    ef = _ef_module.DefaultEmbeddingFunction()

    all_results = []
    for doc in docs:
        try:
            collection = client.get_collection(name=doc.chroma_collection, embedding_function=ef)
            results = collection.query(query_texts=[question], n_results=3)
            if results["documents"]:
                all_results.extend(results["documents"][0])
                logger.info(f"Bot {bot_id} 從 {doc.chroma_collection} 找到 {len(results['documents'][0])} 段落")
        except Exception as e:
            logger.error(f"Bot {bot_id} 查詢 collection {doc.chroma_collection} 失敗：{e}", exc_info=True)
            continue

    if not all_results:
        logger.warning(f"Bot {bot_id} 查詢「{question}」未找到相關段落")
        return None

    context = "\n\n".join(all_results[:5])
    anthropic_client = get_anthropic_client()

    logger.info(f"Bot {bot_id} 呼叫 Claude API，問題：「{question[:50]}」，context 長度：{len(context)}")
    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"你是一個問答機器人。請根據以下知識庫內容，直接回答問題的答案，不要加入任何額外補充、說明或開場白。若知識庫中沒有相關資訊，只需回覆「抱歉，我找不到相關資訊。」\n\n知識庫內容：\n{context}\n\n問題：{question}\n\n答案："
        }]
    )
    logger.info(f"Bot {bot_id} Claude API 回覆成功，tokens: in={message.usage.input_tokens}, out={message.usage.output_tokens}")
    return message.content[0].text, message.usage.input_tokens, message.usage.output_tokens


def record_usage(bot_id: int, input_tokens: int, output_tokens: int, db):
    import models as m
    today = date.today().isoformat()
    stat = db.query(m.UsageStat).filter(
        m.UsageStat.bot_id == bot_id,
        m.UsageStat.date == today
    ).first()

    if stat:
        stat.input_tokens += input_tokens
        stat.output_tokens += output_tokens
        stat.total_tokens += input_tokens + output_tokens
        stat.request_count += 1
    else:
        stat = m.UsageStat(
            bot_id=bot_id,
            date=today,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            request_count=1,
        )
        db.add(stat)
    db.commit()
