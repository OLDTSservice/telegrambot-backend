from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
import models
from auth import require_viewer

router = APIRouter(prefix="/api/group-stats", tags=["群組回覆統計"])


def _apply_date_filter(query, date_col, period: str, value: str,
                       date_from: str = None, date_to: str = None):
    if date_from and date_to:
        return query.filter(date_col >= date_from, date_col <= date_to)
    if not value:
        return query
    return query.filter(date_col.like(f"{value}%"))


@router.get("/telegram")
def telegram_group_stats(
    period: str = Query("monthly"),
    value: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.TelegramGroupStat.chat_id,
        models.TelegramGroupStat.chat_name,
        models.TelegramGroupStat.chat_type,
        func.sum(models.TelegramGroupStat.reply_count).label("total"),
    )
    q = _apply_date_filter(q, models.TelegramGroupStat.date, period, value, date_from, date_to)
    if bot_id:
        q = q.filter(models.TelegramGroupStat.bot_id == bot_id)
    rows = q.group_by(
        models.TelegramGroupStat.chat_id,
        models.TelegramGroupStat.chat_name,
        models.TelegramGroupStat.chat_type,
    ).order_by(func.sum(models.TelegramGroupStat.reply_count).desc()).all()
    return [
        {"chat_id": r.chat_id, "chat_name": r.chat_name,
         "chat_type": r.chat_type, "reply_count": r.total}
        for r in rows
    ]


@router.get("/teams")
def teams_group_stats(
    period: str = Query("monthly"),
    value: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.TeamsGroupStat.conversation_id,
        models.TeamsGroupStat.conversation_name,
        func.sum(models.TeamsGroupStat.reply_count).label("total"),
    )
    q = _apply_date_filter(q, models.TeamsGroupStat.date, period, value, date_from, date_to)
    if bot_id:
        q = q.filter(models.TeamsGroupStat.bot_id == bot_id)
    rows = q.group_by(
        models.TeamsGroupStat.conversation_id,
        models.TeamsGroupStat.conversation_name,
    ).order_by(func.sum(models.TeamsGroupStat.reply_count).desc()).all()
    return [
        {"conversation_id": r.conversation_id, "conversation_name": r.conversation_name,
         "reply_count": r.total}
        for r in rows
    ]


@router.get("/telegram/trend")
def telegram_trend(
    period: str = Query("monthly"),
    value: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    if date_from and date_to:
        q = db.query(
            models.TelegramGroupStat.date,
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date >= date_from,
                 models.TelegramGroupStat.date <= date_to)
    elif period == "daily":
        q = db.query(
            models.TelegramGroupStat.date,
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date == value)
    elif period == "yearly":
        q = db.query(
            func.substr(models.TelegramGroupStat.date, 1, 7).label("date"),
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date.like(f"{value}-%"))
    else:
        q = db.query(
            models.TelegramGroupStat.date,
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date.like(f"{value}-%"))

    if bot_id:
        q = q.filter(models.TelegramGroupStat.bot_id == bot_id)
    rows = q.group_by("date").order_by("date").all()
    return [{"date": r.date, "reply_count": r.total} for r in rows]


@router.get("/teams/trend")
def teams_trend(
    period: str = Query("monthly"),
    value: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    if date_from and date_to:
        q = db.query(
            models.TeamsGroupStat.date,
            func.sum(models.TeamsGroupStat.reply_count).label("total"),
        ).filter(models.TeamsGroupStat.date >= date_from,
                 models.TeamsGroupStat.date <= date_to)
    elif period == "yearly":
        q = db.query(
            func.substr(models.TeamsGroupStat.date, 1, 7).label("date"),
            func.sum(models.TeamsGroupStat.reply_count).label("total"),
        ).filter(models.TeamsGroupStat.date.like(f"{value}-%"))
    else:
        q = db.query(
            models.TeamsGroupStat.date,
            func.sum(models.TeamsGroupStat.reply_count).label("total"),
        ).filter(models.TeamsGroupStat.date.like(f"{value}-%"))

    if bot_id:
        q = q.filter(models.TeamsGroupStat.bot_id == bot_id)
    rows = q.group_by("date").order_by("date").all()
    return [{"date": r.date, "reply_count": r.total} for r in rows]


@router.get("/ticket-counts")
def ticket_counts(
    date_from: str = Query(None),
    date_to: str = Query(None),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    """知識庫工單數 + 白名單工單數"""
    # SQLite 的 CAST(datetime AS DATE) 不截斷字串，直接比對 datetime 字串
    # 需以 date_to 的隔天作為排除上界，否則 date_to 當天資料全被過濾
    def apply(q, col):
        if date_from and date_to:
            from datetime import datetime, timedelta
            date_to_next = (datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
            q = q.filter(col >= date_from, col < date_to_next)
        return q

    kb_q = db.query(func.count(models.ConversationLog.id))
    if bot_id:
        kb_q = kb_q.filter(models.ConversationLog.bot_id == bot_id)
    kb_q = apply(kb_q, models.ConversationLog.created_at)
    kb_count = kb_q.scalar() or 0

    wl_q = db.query(func.count(models.WhitelistLog.id)).filter(
        models.WhitelistLog.status == "success"
    )
    if bot_id:
        wl_q = wl_q.filter(models.WhitelistLog.bot_id == bot_id)
    wl_q = apply(wl_q, models.WhitelistLog.created_at)
    wl_count = wl_q.scalar() or 0

    return {"kb_tickets": kb_count, "whitelist_tickets": wl_count}
