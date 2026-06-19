from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
import models
from auth import require_viewer

router = APIRouter(prefix="/api/group-stats", tags=["群組回覆統計"])


def _period_filter(query, date_col, period: str, value: str):
    """
    period: daily   → value = YYYY-MM-DD
            monthly → value = YYYY-MM
            yearly  → value = YYYY
    """
    if period == "daily":
        return query.filter(date_col == value)
    elif period == "monthly":
        return query.filter(date_col.like(f"{value}-%"))
    else:  # yearly
        return query.filter(date_col.like(f"{value}-%"))


@router.get("/telegram")
def telegram_group_stats(
    period: str = Query("monthly", pattern="^(daily|monthly|yearly)$"),
    value: str = Query(..., description="daily=YYYY-MM-DD, monthly=YYYY-MM, yearly=YYYY"),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.TelegramGroupStat.chat_id,
        models.TelegramGroupStat.chat_name,
        models.TelegramGroupStat.chat_type,
        func.sum(models.TelegramGroupStat.reply_count).label("total"),
    ).filter(models.TelegramGroupStat.date.like(f"{value}%"))

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
    period: str = Query("monthly", pattern="^(daily|monthly|yearly)$"),
    value: str = Query(..., description="daily=YYYY-MM-DD, monthly=YYYY-MM, yearly=YYYY"),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.TeamsGroupStat.conversation_id,
        models.TeamsGroupStat.conversation_name,
        func.sum(models.TeamsGroupStat.reply_count).label("total"),
    ).filter(models.TeamsGroupStat.date.like(f"{value}%"))

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
    period: str = Query("monthly", pattern="^(daily|monthly|yearly)$"),
    value: str = Query(...),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    """每日/每月趨勢，供折線圖使用"""
    if period == "daily":
        # 以小時分組（當天各時段）
        q = db.query(
            models.TelegramGroupStat.date,
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date == value)
    elif period == "monthly":
        q = db.query(
            models.TelegramGroupStat.date,
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date.like(f"{value}-%"))
    else:
        q = db.query(
            func.substr(models.TelegramGroupStat.date, 1, 7).label("date"),
            func.sum(models.TelegramGroupStat.reply_count).label("total"),
        ).filter(models.TelegramGroupStat.date.like(f"{value}-%"))

    if bot_id:
        q = q.filter(models.TelegramGroupStat.bot_id == bot_id)

    rows = q.group_by("date").order_by("date").all()
    return [{"date": r.date, "reply_count": r.total} for r in rows]


@router.get("/teams/trend")
def teams_trend(
    period: str = Query("monthly", pattern="^(daily|monthly|yearly)$"),
    value: str = Query(...),
    bot_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    if period == "yearly":
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
