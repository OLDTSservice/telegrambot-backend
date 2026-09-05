from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_viewer

router = APIRouter(prefix="/api/netwin", tags=["查輸贏回覆"])


@router.get("/logs", response_model=List[schemas.NetwinQueryLogOut])
def get_netwin_logs(bot_id: int, limit: int = 50,
                    db: Session = Depends(get_db), _=Depends(require_viewer)):
    """取得最近 N 筆查輸贏回覆處理記錄"""
    return (
        db.query(models.NetwinQueryLog)
        .filter(models.NetwinQueryLog.bot_id == bot_id)
        .order_by(models.NetwinQueryLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/stats")
def get_netwin_stats(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    """依群組名稱統計「查詢後回覆次數」（outcome=auto_replied）與「未查詢的次數」（其餘 outcome）。"""
    rows = (
        db.query(
            models.NetwinQueryLog.chat_id,
            models.NetwinQueryLog.chat_name,
            func.sum(case((models.NetwinQueryLog.outcome == "auto_replied", 1), else_=0)).label("replied_count"),
            func.sum(case((models.NetwinQueryLog.outcome != "auto_replied", 1), else_=0)).label("not_queried_count"),
        )
        .filter(models.NetwinQueryLog.bot_id == bot_id)
        .group_by(models.NetwinQueryLog.chat_id, models.NetwinQueryLog.chat_name)
        .order_by(func.sum(case((models.NetwinQueryLog.outcome == "auto_replied", 1), else_=0)).desc())
        .all()
    )
    return [
        {
            "chat_id": r.chat_id,
            "chat_name": r.chat_name,
            "replied_count": r.replied_count or 0,
            "not_queried_count": r.not_queried_count or 0,
        }
        for r in rows
    ]
