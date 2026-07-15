import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
import models, schemas
from auth import require_editor, require_viewer
from services.ai_service import process_document, delete_document_vectors

_base_dir = "/data" if os.path.isdir("/data") else "."
UPLOAD_DIR = os.path.join(_base_dir, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".md"}

router = APIRouter(prefix="/api/knowledge", tags=["知識庫"])


# ── 文件 CRUD ──────────────────────────────────────────────────────────────

@router.get("", response_model=List[schemas.DocOut])
def list_docs(db: Session = Depends(get_db), _=Depends(require_viewer)):
    docs = db.query(models.KnowledgeDoc).all()
    for doc in docs:
        doc.qa_count = db.query(models.KnowledgeQA).filter(
            models.KnowledgeQA.doc_id == doc.id
        ).count()
    return docs


@router.post("", response_model=schemas.DocOut)
async def upload_doc(
    bot_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_editor),
):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支援的檔案格式，允許：{', '.join(ALLOWED_EXTENSIONS)}")

    saved_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, saved_filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc = models.KnowledgeDoc(
        bot_id=bot_id,
        filename=saved_filename,
        original_filename=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(content),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        await process_document(file_path, ext, collection_name="",
                               doc_id=doc.id, bot_id=bot_id, db=db, platform="telegram")
    except Exception as e:
        db.delete(doc)
        db.commit()
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件處理失敗：{str(e)}")

    return doc


@router.get("/{doc_id}/download")
def download_doc(doc_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(file_path, filename=doc.original_filename)


@router.put("/{doc_id}", response_model=schemas.DocOut)
def update_doc(doc_id: int, payload: schemas.DocUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    if doc.chroma_collection:
        delete_document_vectors(doc.chroma_collection)

    db.delete(doc)
    db.commit()
    return {"message": "已刪除"}


# ── Q&A CRUD ───────────────────────────────────────────────────────────────

class QACreate(BaseModel):
    doc_id: int
    question: str
    keywords: Optional[str] = ""
    answer: str


class QAUpdate(BaseModel):
    question: Optional[str] = None
    keywords: Optional[str] = None
    answer: Optional[str] = None


class QAOut(BaseModel):
    id: int
    doc_id: int
    bot_id: int
    question: str
    keywords: Optional[str]
    answer: str
    order_index: int

    class Config:
        from_attributes = True


@router.get("/{doc_id}/qas", response_model=List[QAOut])
def list_qas(
    doc_id: int,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    offset = (page - 1) * page_size
    return (
        db.query(models.KnowledgeQA)
        .filter(models.KnowledgeQA.doc_id == doc_id)
        .order_by(models.KnowledgeQA.order_index)
        .offset(offset)
        .limit(page_size)
        .all()
    )


@router.get("/{doc_id}/qas/count")
def count_qas(doc_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    total = db.query(models.KnowledgeQA).filter(models.KnowledgeQA.doc_id == doc_id).count()
    return {"total": total}


@router.post("/qas", response_model=QAOut)
def create_qa(payload: QACreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")
    max_order = db.query(models.KnowledgeQA).filter(
        models.KnowledgeQA.doc_id == payload.doc_id
    ).count()
    qa = models.KnowledgeQA(
        doc_id=payload.doc_id,
        bot_id=doc.bot_id,
        question=payload.question,
        keywords=payload.keywords or "",
        answer=payload.answer,
        order_index=max_order,
    )
    db.add(qa)
    # 同步寫入 chunk 讓查詢時能用到
    chunk_text = f"Q: {payload.question}\n{payload.keywords or ''}\nA: {payload.answer}".strip()
    db.add(models.KnowledgeChunk(
        doc_id=payload.doc_id, bot_id=doc.bot_id,
        chunk_text=chunk_text, chunk_index=max_order,
    ))
    db.commit()
    db.refresh(qa)
    return qa


@router.put("/qas/{qa_id}", response_model=QAOut)
def update_qa(qa_id: int, payload: QAUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    qa = db.query(models.KnowledgeQA).filter(models.KnowledgeQA.id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A 不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(qa, field, value)
    db.commit()
    db.refresh(qa)
    return qa


@router.delete("/qas/{qa_id}")
def delete_qa(qa_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    qa = db.query(models.KnowledgeQA).filter(models.KnowledgeQA.id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A 不存在")
    db.delete(qa)
    db.commit()
    return {"message": "已刪除"}
