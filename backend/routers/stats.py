from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, timedelta, datetime
from database import get_db
import models, schemas
from auth import require_viewer
from pydantic import BaseModel

router = APIRouter(prefix="/api/stats", tags=["使用量統計"])


@router.get("", response_model=schemas.StatsSummary)
def get_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    today = date.today().isoformat()
    this_month = date.today().strftime("%Y-%m")
    start_date = (date.today() - timedelta(days=days)).isoformat()

    # 今日統計
    today_row = db.query(
        func.sum(models.UsageStat.total_tokens),
        func.sum(models.UsageStat.request_count),
    ).filter(models.UsageStat.date == today).first()

    # 本月統計
    month_row = db.query(
        func.sum(models.UsageStat.total_tokens),
        func.sum(models.UsageStat.request_count),
    ).filter(models.UsageStat.date.like(f"{this_month}%")).first()

    # 每日統計
    daily_rows = db.query(
        models.UsageStat.date,
        func.sum(models.UsageStat.total_tokens).label("total_tokens"),
        func.sum(models.UsageStat.input_tokens).label("input_tokens"),
        func.sum(models.UsageStat.output_tokens).label("output_tokens"),
        func.sum(models.UsageStat.request_count).label("request_count"),
    ).filter(
        models.UsageStat.date >= start_date
    ).group_by(models.UsageStat.date).order_by(models.UsageStat.date).all()

    # 各機器人統計
    bot_rows = db.query(
        models.UsageStat.bot_id,
        models.TelegramBot.name,
        func.sum(models.UsageStat.total_tokens).label("total_tokens"),
        func.sum(models.UsageStat.request_count).label("request_count"),
    ).join(
        models.TelegramBot, models.TelegramBot.id == models.UsageStat.bot_id
    ).filter(
        models.UsageStat.date >= start_date
    ).group_by(models.UsageStat.bot_id, models.TelegramBot.name).all()

    return _build_summary(today_row, month_row, daily_rows, bot_rows)


def _build_summary(today_row, month_row, daily_rows, bot_rows):
    return schemas.StatsSummary(
        total_tokens_today=today_row[0] or 0,
        total_tokens_month=month_row[0] or 0,
        total_requests_today=today_row[1] or 0,
        total_requests_month=month_row[1] or 0,
        daily=[
            schemas.DailyStatOut(
                date=r.date,
                total_tokens=r.total_tokens or 0,
                input_tokens=r.input_tokens or 0,
                output_tokens=r.output_tokens or 0,
                request_count=r.request_count or 0,
            ) for r in daily_rows
        ],
        by_bot=[
            schemas.BotStatOut(
                bot_id=r.bot_id,
                bot_name=r.name,
                total_tokens=r.total_tokens or 0,
                request_count=r.request_count or 0,
            ) for r in bot_rows
        ],
    )


class RecentQueryOut(BaseModel):
    id: int
    chat_name: str
    question: str
    answer: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/recent-queries", response_model=List[RecentQueryOut])
def get_recent_queries(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    logs = db.query(models.ConversationLog).order_by(
        models.ConversationLog.created_at.desc()
    ).limit(limit).all()
    return logs
