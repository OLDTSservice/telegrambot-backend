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


def _taipei_range_to_utc(date_from: str, date_to: str):
    """把台灣日曆日期範圍換算成對應的 UTC datetime 範圍，用於比對 created_at（UTC 儲存）欄位。
    未提供 date_from/date_to 時回傳 (None, None)，呼叫端應略過此過濾條件。"""
    if not (date_from and date_to):
        return None, None
    from datetime import datetime, timedelta
    taipei_offset = timedelta(hours=8)
    start_utc = datetime.strptime(date_from, '%Y-%m-%d') - taipei_offset
    end_utc = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1) - taipei_offset
    return start_utc, end_utc


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

    # 依群組分別統計知識庫工單數 / 白名單工單數（僅在有指定日期範圍時套用，與整體 ticket-counts 邏輯一致）
    start_utc, end_utc = _taipei_range_to_utc(date_from, date_to)

    kb_q = db.query(models.ConversationLog.chat_id, func.count(models.ConversationLog.id))
    if bot_id:
        kb_q = kb_q.filter(models.ConversationLog.bot_id == bot_id)
    if start_utc:
        kb_q = kb_q.filter(models.ConversationLog.created_at >= start_utc, models.ConversationLog.created_at < end_utc)
    kb_by_chat = dict(kb_q.group_by(models.ConversationLog.chat_id).all())

    wl_q = db.query(models.WhitelistLog.chat_id, func.count(models.WhitelistLog.id)).filter(
        models.WhitelistLog.status == "success"
    )
    if bot_id:
        wl_q = wl_q.filter(models.WhitelistLog.bot_id == bot_id)
    if start_utc:
        wl_q = wl_q.filter(models.WhitelistLog.created_at >= start_utc, models.WhitelistLog.created_at < end_utc)
    wl_by_chat = dict(wl_q.group_by(models.WhitelistLog.chat_id).all())

    return [
        {"chat_id": r.chat_id, "chat_name": r.chat_name,
         "chat_type": r.chat_type, "reply_count": r.total,
         "kb_tickets": kb_by_chat.get(r.chat_id, 0),
         "whitelist_tickets": wl_by_chat.get(r.chat_id, 0)}
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
    # created_at 以 UTC 儲存，但 date_from/date_to 是前端送來的台灣日曆日期，
    # 需先把台灣日期範圍換算成對應的 UTC 時間範圍，再拿去跟 created_at 比較，
    # 否則台灣時間每天 00:00–08:00 的資料會被歸類到前一天，統計對不上。
    start_utc, end_utc = _taipei_range_to_utc(date_from, date_to)

    def apply(q, col):
        if start_utc:
            q = q.filter(col >= start_utc, col < end_utc)
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
