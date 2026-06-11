import os
import asyncio
from datetime import date
from typing import Optional
import anthropic
import chromadb
from chromadb.utils import embedding_functions

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHROMA_PATH = "./chroma_db"

_chroma_client = None
_anthropic_client = None


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
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

    elif ext in (".txt", ".csv"):
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
    text = await asyncio.to_thread(_extract_text, file_path, ext)
    if not text.strip():
        raise ValueError("無法從文件中提取文字")

    chunks = _chunk_text(text)
    client = get_chroma_client()
    ef = embedding_functions.DefaultEmbeddingFunction()
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
    import models as m
    docs = db.query(m.KnowledgeDoc).filter(
        m.KnowledgeDoc.bot_id == bot_id,
        m.KnowledgeDoc.is_enabled == True
    ).all()

    if not docs:
        return None

    client = get_chroma_client()
    ef = embedding_functions.DefaultEmbeddingFunction()

    all_results = []
    for doc in docs:
        try:
            collection = client.get_collection(name=doc.chroma_collection, embedding_function=ef)
            results = collection.query(query_texts=[question], n_results=3)
            if results["documents"]:
                all_results.extend(results["documents"][0])
        except Exception:
            continue

    if not all_results:
        return None

    context = "\n\n".join(all_results[:5])
    anthropic_client = get_anthropic_client()

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"請根據以下知識庫內容回答問題。若知識庫中沒有相關資訊，請回覆「抱歉，我找不到相關資訊。」\n\n知識庫內容：\n{context}\n\n問題：{question}"
        }]
    )

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
