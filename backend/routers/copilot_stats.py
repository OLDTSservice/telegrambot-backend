from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from database import get_db
import models
from auth import require_viewer

router = APIRouter(prefix="/api/copilot-stats", tags=["Copilot統計"])


@router.get("/groups")
def get_group_stats(
    period: str = "daily",
    value: str = None,
    bot_id: int = None,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.CopilotGroupStat.conversation_id,
        models.CopilotGroupStat.conversation_name,
        func.sum(models.CopilotGroupStat.reply_count).label("total"),
    )
    if bot_id:
        q = q.filter(models.CopilotGroupStat.bot_id == bot_id)
    if value:
        if period == "daily":
            q = q.filter(models.CopilotGroupStat.date == value)
        elif period == "monthly":
            q = q.filter(models.CopilotGroupStat.date.like(f"{value}%"))
        elif period == "yearly":
            q = q.filter(models.CopilotGroupStat.date.like(f"{value}%"))
    q = q.group_by(
        models.CopilotGroupStat.conversation_id,
        models.CopilotGroupStat.conversation_name,
    ).order_by(func.sum(models.CopilotGroupStat.reply_count).desc())
    rows = q.all()
    return [{"conversation_id": r[0], "conversation_name": r[1], "reply_count": r[2]} for r in rows]


@router.get("/trend")
def get_trend(
    period: str = "daily",
    value: str = None,
    bot_id: int = None,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    q = db.query(
        models.CopilotGroupStat.date,
        func.sum(models.CopilotGroupStat.reply_count).label("total"),
    )
    if bot_id:
        q = q.filter(models.CopilotGroupStat.bot_id == bot_id)
    if value:
        if period == "monthly":
            q = q.filter(models.CopilotGroupStat.date.like(f"{value}%"))
        elif period == "yearly":
            q = q.filter(models.CopilotGroupStat.date.like(f"{value}%"))
    q = q.group_by(models.CopilotGroupStat.date).order_by(models.CopilotGroupStat.date)
    rows = q.all()
    return [{"date": r[0], "reply_count": r[1]} for r in rows]
