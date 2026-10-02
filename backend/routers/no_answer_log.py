from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import get_db
import models
from auth import require_page_view, require_page_edit

router = APIRouter(prefix="/api/no-answer-logs", tags=["AI無解答對話紀錄"])
_VIEW = require_page_view("telegram_knowledge")
_EDIT = require_page_edit("telegram_knowledge")


class NoAnswerLogOut(BaseModel):
    id: int
    bot_id: int
    chat_id: str
    chat_name: str
    question: str
    created_at: datetime

    class Config:
        from_attributes = True


class AddToKnowledge(BaseModel):
    doc_id: int
    question: Optional[str] = None
    answer: Optional[str] = None


def _recent_query(db: Session, bot_id: Optional[int], q: Optional[str]):
    """近 7 日紀錄；q 有值時只保留「問題內容」包含該關鍵字的紀錄（不分大小寫）。
    關鍵字裡的 % 與 _ 視為一般字元（帳號常含底線，不能當成 LIKE 萬用字元）。"""
    since = datetime.utcnow() - timedelta(days=7)
    query = db.query(models.NoAnswerLog).filter(models.NoAnswerLog.created_at >= since)
    if bot_id:
        query = query.filter(models.NoAnswerLog.bot_id == bot_id)
    kw = (q or "").strip()
    if kw:
        escaped = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(models.NoAnswerLog.question.ilike(f"%{escaped}%", escape="\\"))
    return query


@router.get("", response_model=List[NoAnswerLogOut])
def list_logs(
    bot_id: Optional[int] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(_VIEW),
):
    offset = (page - 1) * page_size
    return (_recent_query(db, bot_id, q)
            .order_by(models.NoAnswerLog.created_at.desc()).offset(offset).limit(page_size).all())


@router.get("/count")
def count_logs(bot_id: Optional[int] = None, q: Optional[str] = None,
               db: Session = Depends(get_db), _=Depends(_VIEW)):
    return {"total": _recent_query(db, bot_id, q).count()}


@router.post("/{log_id}/to-knowledge")
def add_to_knowledge(
    log_id: int,
    payload: AddToKnowledge,
    db: Session = Depends(get_db),
    _=Depends(_EDIT),
):
    log = db.query(models.NoAnswerLog).filter(models.NoAnswerLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="紀錄不存在")

    doc = db.query(models.KnowledgeDoc).filter(models.KnowledgeDoc.id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")

    q_text = payload.question or log.question
    a_text = payload.answer or ""

    max_order = db.query(models.KnowledgeQA).filter(
        models.KnowledgeQA.doc_id == payload.doc_id
    ).count()

    db.add(models.KnowledgeQA(
        doc_id=payload.doc_id, bot_id=doc.bot_id,
        question=q_text, keywords="", answer=a_text,
        order_index=max_order,
    ))
    db.add(models.KnowledgeChunk(
        doc_id=payload.doc_id, bot_id=doc.bot_id,
        chunk_text=f"Q: {q_text}\nA: {a_text}",
        chunk_index=max_order,
    ))
    db.commit()
    return {"message": "已新增至知識庫"}
