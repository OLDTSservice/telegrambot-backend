import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer
from services.ai_service import process_document, delete_document_vectors

_base_dir = "/data" if os.path.isdir("/data") else "."
UPLOAD_DIR = os.path.join(_base_dir, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv"}

router = APIRouter(prefix="/api/knowledge", tags=["知識庫"])


@router.get("", response_model=List[schemas.DocOut])
def list_docs(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.KnowledgeDoc).all()


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

    collection_name = f"bot_{bot_id}_{uuid.uuid4().hex[:8]}"
    try:
        await process_document(file_path, ext, collection_name)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件處理失敗：{str(e)}")

    doc = models.KnowledgeDoc(
        bot_id=bot_id,
        filename=saved_filename,
        original_filename=file.filename,
        file_type=ext.lstrip("."),
        file_size=len(content),
        chroma_collection=collection_name,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


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
