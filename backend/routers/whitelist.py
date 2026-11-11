from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_page_view, require_page_edit

router = APIRouter(prefix="/api/whitelist", tags=["後台白名單處理"])
_VIEW = require_page_view("telegram_whitelist")
_EDIT = require_page_edit("telegram_whitelist")
_VIEW_NEW = require_page_view("telegram_whitelist_new")


def _logs(db: Session, bot_id: int, limit: int, site: str):
    # 既有紀錄的 site 為 NULL／'old'，一律視為舊後台
    return (
        db.query(models.WhitelistLog)
        .filter(models.WhitelistLog.bot_id == bot_id,
                func.coalesce(models.WhitelistLog.site, "old") == site)
        .order_by(models.WhitelistLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/logs", response_model=List[schemas.WhitelistLogOut])
def get_whitelist_logs(bot_id: int, limit: int = 50,
                       db: Session = Depends(get_db), _=Depends(_VIEW)):
    """取得最近 N 筆舊後台白名單處理記錄"""
    return _logs(db, bot_id, limit, "old")


@router.get("/logs-new", response_model=List[schemas.WhitelistLogOut])
def get_whitelist_logs_new(bot_id: int, limit: int = 50,
                           db: Session = Depends(get_db), _=Depends(_VIEW_NEW)):
    """取得最近 N 筆新後台（tj-report）白名單處理記錄"""
    return _logs(db, bot_id, limit, "new")
