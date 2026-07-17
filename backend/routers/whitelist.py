from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/whitelist", tags=["後台白名單處理"])


@router.get("/logs", response_model=List[schemas.WhitelistLogOut])
def get_whitelist_logs(bot_id: int, limit: int = 50,
                       db: Session = Depends(get_db), _=Depends(require_viewer)):
    """取得最近 N 筆白名單處理記錄"""
    return (
        db.query(models.WhitelistLog)
        .filter(models.WhitelistLog.bot_id == bot_id)
        .order_by(models.WhitelistLog.created_at.desc())
        .limit(limit)
        .all()
    )
