from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import timedelta, datetime
from database import get_db
import models, schemas
from auth import require_viewer
from pydantic import BaseModel
from timezone_utils import taipei_today

router = APIRouter(prefix="/api/stats", tags=["使用量統計"])

# claude-haiku-4-5 定價（USD / 1M tokens），僅供費用預估參考，與前端 StatsPage.jsx 的 PRICE 常數一致
_PRICE = {"input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08}


def _calc_usd(input_tok: int, output_tok: int, cache_read: int, cache_write: int) -> float:
    return (
        input_tok * _PRICE["input"] +
        output_tok * _PRICE["output"] +
        cache_read * _PRICE["cache_read"] +
        cache_write * _PRICE["cache_write"]
    ) / 1_000_000


def _month_token_totals(db: Session, month_str: str):
    row = db.query(
        func.sum(models.UsageStat.input_tokens),
        func.sum(models.UsageStat.output_tokens),
        func.sum(models.UsageStat.cache_read_tokens),
        func.sum(models.UsageStat.cache_write_tokens),
    ).filter(models.UsageStat.date.like(f"{month_str}%")).first()
    return [x or 0 for x in row]


@router.get("", response_model=schemas.StatsSummary)
def get_stats(
    days: int = Query(30, ge=1, le=365),
    date_from: str = Query(None),
    date_to: str = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    _today_date = taipei_today()
    today = _today_date.isoformat()
    this_month = _today_date.strftime("%Y-%m")
    last_month_date = _today_date.replace(day=1) - timedelta(days=1)
    last_month = last_month_date.strftime("%Y-%m")
    # 每日/機器人分布圖表：優先使用前端傳入的日期範圍（與回覆統計一致的快捷/自訂選擇），
    # 未指定時 fallback 回舊有的「近 N 天」模式
    start_date = date_from if (date_from and date_to) else (_today_date - timedelta(days=days)).isoformat()
    end_date = date_to if (date_from and date_to) else today

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

    # 本月 / 上月合計費用（依實際 token 組成精確估算，非近 N 筆的粗略估算）
    month_cost_usd = _calc_usd(*_month_token_totals(db, this_month))
    last_month_cost_usd = _calc_usd(*_month_token_totals(db, last_month))

    # 每日統計
    daily_rows = db.query(
        models.UsageStat.date,
        func.sum(models.UsageStat.total_tokens).label("total_tokens"),
        func.sum(models.UsageStat.input_tokens).label("input_tokens"),
        func.sum(models.UsageStat.output_tokens).label("output_tokens"),
        func.sum(models.UsageStat.request_count).label("request_count"),
    ).filter(
        models.UsageStat.date >= start_date, models.UsageStat.date <= end_date
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
        models.UsageStat.date >= start_date, models.UsageStat.date <= end_date
    ).group_by(models.UsageStat.bot_id, models.TelegramBot.name).all()

    return _build_summary(today_row, month_row, daily_rows, bot_rows, month_cost_usd, last_month_cost_usd)


def _build_summary(today_row, month_row, daily_rows, bot_rows, month_cost_usd, last_month_cost_usd):
    return schemas.StatsSummary(
        total_tokens_today=today_row[0] or 0,
        total_tokens_month=month_row[0] or 0,
        total_requests_today=today_row[1] or 0,
        total_requests_month=month_row[1] or 0,
        month_cost_usd=month_cost_usd,
        last_month_cost_usd=last_month_cost_usd,
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


class GroupCostOut(BaseModel):
    chat_id: str
    chat_name: str
    total_tokens: int
    cost_usd: float


@router.get("/cost-by-group", response_model=List[GroupCostOut])
def get_cost_by_group(
    date_from: str = Query(None),
    date_to: str = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    """群組花費排行（AI Token 費用），依 chat_id 彙總 ConversationLog（有解答）與
    NoAnswerLog（無解答，同樣會呼叫 Claude 消耗 Token）兩張表，取花費前 N 名的群組。
    可用 date_from/date_to（台灣日曆日期）篩選時間範圍，未帶入時不限制時間。
    注意：ConversationLog/NoAnswerLog 只保留近 7 日資料（見 models.py 註解），
    篩選超過 7 天前的區間會查不到資料。"""
    from routers.group_stats import _taipei_range_to_utc
    start_utc, end_utc = _taipei_range_to_utc(date_from, date_to)

    def _grouped(model):
        q = db.query(
            model.chat_id,
            model.chat_name,
            func.sum(model.input_tokens).label("input_tokens"),
            func.sum(model.output_tokens).label("output_tokens"),
            func.sum(model.cache_read_tokens).label("cache_read_tokens"),
            func.sum(model.cache_write_tokens).label("cache_write_tokens"),
        )
        if start_utc:
            q = q.filter(model.created_at >= start_utc, model.created_at < end_utc)
        return q.group_by(model.chat_id, model.chat_name).all()

    totals: dict[str, dict] = {}
    for rows in (_grouped(models.ConversationLog), _grouped(models.NoAnswerLog)):
        for r in rows:
            key = r.chat_id
            entry = totals.setdefault(key, {
                "chat_name": r.chat_name,
                "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            })
            entry["input"] += r.input_tokens or 0
            entry["output"] += r.output_tokens or 0
            entry["cache_read"] += r.cache_read_tokens or 0
            entry["cache_write"] += r.cache_write_tokens or 0

    results = [
        GroupCostOut(
            chat_id=str(chat_id),
            chat_name=entry["chat_name"],
            total_tokens=entry["input"] + entry["output"] + entry["cache_read"] + entry["cache_write"],
            cost_usd=_calc_usd(entry["input"], entry["output"], entry["cache_read"], entry["cache_write"]),
        )
        for chat_id, entry in totals.items()
    ]
    results.sort(key=lambda x: x.cost_usd, reverse=True)
    return results[:limit]


class RecentQueryOut(BaseModel):
    id: int
    source: str  # "conversation"（有解答） | "no_answer"（無解答）
    has_answer: bool
    chat_name: str
    question: str
    answer: Optional[str] = None
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
    """合併「有解答」與「無解答」兩種知識庫呼叫紀錄，依時間排序取最新 N 筆。
    無解答的呼叫同樣會消耗 Token（Claude 判斷找不到答案也要付費），
    但過去只記錄在 NoAnswerLog、不會出現在這份清單，容易讓人誤以為沒有消耗。"""
    answered = db.query(models.ConversationLog).order_by(
        models.ConversationLog.created_at.desc()
    ).limit(limit).all()
    unanswered = db.query(models.NoAnswerLog).order_by(
        models.NoAnswerLog.created_at.desc()
    ).limit(limit).all()

    combined = [
        RecentQueryOut(
            id=log.id, source="conversation", has_answer=True,
            chat_name=log.chat_name, question=log.question, answer=log.answer,
            input_tokens=log.input_tokens, output_tokens=log.output_tokens,
            cache_read_tokens=log.cache_read_tokens, cache_write_tokens=log.cache_write_tokens,
            created_at=log.created_at,
        ) for log in answered
    ] + [
        RecentQueryOut(
            id=log.id, source="no_answer", has_answer=False,
            chat_name=log.chat_name, question=log.question, answer=None,
            input_tokens=log.input_tokens, output_tokens=log.output_tokens,
            cache_read_tokens=log.cache_read_tokens, cache_write_tokens=log.cache_write_tokens,
            created_at=log.created_at,
        ) for log in unanswered
    ]
    combined.sort(key=lambda x: x.created_at, reverse=True)
    return combined[:limit]
