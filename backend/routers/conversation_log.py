from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import get_db
import models
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/conversation-logs", tags=["對話日誌"])


class LogOut(BaseModel):
    id: int
    bot_id: int
    chat_id: str
    chat_name: str
    question: str
    answer: str
    created_at: datetime

    class Config:
        from_attributes = True


class AddToKnowledge(BaseModel):
    doc_id: int
    question: Optional[str] = None
    answer: Optional[str] = None


@router.get("", response_model=List[LogOut])
def list_logs(
    bot_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    since = datetime.utcnow() - timedelta(days=7)
    q = db.query(models.ConversationLog).filter(
        models.ConversationLog.created_at >= since
    )
    if bot_id:
        q = q.filter(models.ConversationLog.bot_id == bot_id)
    total = q.count()
    offset = (page - 1) * page_size
    logs = q.order_by(models.ConversationLog.created_at.desc()).offset(offset).limit(page_size).all()
    return logs


@router.get("/count")
def count_logs(bot_id: Optional[int] = None, db: Session = Depends(get_db), _=Depends(require_viewer)):
    since = datetime.utcnow() - timedelta(days=7)
    q = db.query(models.ConversationLog).filter(models.ConversationLog.created_at >= since)
    if bot_id:
        q = q.filter(models.ConversationLog.bot_id == bot_id)
    return {"total": q.count()}


@router.post("/{log_id}/to-knowledge")
def add_log_to_knowledge(
    log_id: int,
    payload: AddToKnowledge,
    db: Session = Depends(get_db),
    _=Depends(require_editor),
):
    log = db.query(models.ConversationLog).filter(models.ConversationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="對話記錄不存在")

    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")

    max_order = db.query(models.KnowledgeQA).filter(
        models.KnowledgeQA.doc_id == payload.doc_id
    ).count()

    q_text = payload.question or log.question
    a_text = payload.answer or log.answer

    qa = models.KnowledgeQA(
        doc_id=payload.doc_id,
        bot_id=doc.bot_id,
        question=q_text,
        keywords="",
        answer=a_text,
        order_index=max_order,
    )
    db.add(qa)

    chunk_text = f"Q: {q_text}\nA: {a_text}"
    db.add(models.KnowledgeChunk(
        doc_id=payload.doc_id, bot_id=doc.bot_id,
        chunk_text=chunk_text, chunk_index=max_order,
    ))
    db.commit()
    return {"message": "已新增至知識庫"}
