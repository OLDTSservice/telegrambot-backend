from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import get_db
import models
from auth import require_page_view, require_page_edit

router = APIRouter(prefix="/api/conversation-logs", tags=["對話日誌"])
_VIEW = require_page_view("telegram_knowledge")
_EDIT = require_page_edit("telegram_knowledge")


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


def _recent_query(db: Session, bot_id: Optional[int], q: Optional[str], chat_id: Optional[str] = None):
    """近 7 日紀錄；chat_id 有值時只看該群組；q 有值時只保留「問題內容」包含該關鍵字的紀錄（不分大小寫）。
    關鍵字裡的 % 與 _ 視為一般字元（帳號常含底線，不能當成 LIKE 萬用字元）。"""
    since = datetime.utcnow() - timedelta(days=7)
    query = db.query(models.ConversationLog).filter(models.ConversationLog.created_at >= since)
    if bot_id:
        query = query.filter(models.ConversationLog.bot_id == bot_id)
    if chat_id:
        query = query.filter(models.ConversationLog.chat_id == chat_id)
    kw = (q or "").strip()
    if kw:
        escaped = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(models.ConversationLog.question.ilike(f"%{escaped}%", escape="\\"))
    return query


@router.get("", response_model=List[LogOut])
def list_logs(
    bot_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _=Depends(_VIEW),
):
    offset = (page - 1) * page_size
    return (_recent_query(db, bot_id, q, chat_id)
            .order_by(models.ConversationLog.created_at.desc()).offset(offset).limit(page_size).all())


@router.get("/count")
def count_logs(bot_id: Optional[int] = None, chat_id: Optional[str] = None, q: Optional[str] = None,
               db: Session = Depends(get_db), _=Depends(_VIEW)):
    return {"total": _recent_query(db, bot_id, q, chat_id).count()}


@router.get("/groups")
def list_groups(bot_id: Optional[int] = None, db: Session = Depends(get_db), _=Depends(_VIEW)):
    """近 7 日有紀錄的群組（給群組下拉選單用），依紀錄筆數多到少排序。
    以 chat_id 區分群組；群組改過名稱時顯示最新一筆紀錄的名稱。"""
    rows = (_recent_query(db, bot_id, None)
            .with_entities(models.ConversationLog.chat_id, models.ConversationLog.chat_name)
            .order_by(models.ConversationLog.created_at.desc()).all())
    groups = {}
    for chat_id, chat_name in rows:
        g = groups.setdefault(chat_id, {"chat_id": chat_id, "chat_name": chat_name, "count": 0})
        g["count"] += 1
    return sorted(groups.values(), key=lambda g: (-g["count"], g["chat_name"]))


@router.post("/{log_id}/to-knowledge")
def add_log_to_knowledge(
    log_id: int,
    payload: AddToKnowledge,
    db: Session = Depends(get_db),
    _=Depends(_EDIT),
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
