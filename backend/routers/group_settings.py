from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from database import get_db
import models
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/group-settings", tags=["群組管理"])


class GroupOut(BaseModel):
    chat_id: str
    chat_name: str
    chat_type: Optional[str]
    ai_enabled: bool
    last_active: Optional[str]

    class Config:
        from_attributes = True


@router.get("")
def list_groups(
    bot_id: int,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    # 取得此 bot 所有不重複群組（從 group_stats 彙整）
    subq = db.query(
        models.TelegramGroupStat.chat_id,
        func.max(models.TelegramGroupStat.chat_name).label("chat_name"),
        func.max(models.TelegramGroupStat.chat_type).label("chat_type"),
        func.max(models.TelegramGroupStat.date).label("last_active"),
    ).filter(
        models.TelegramGroupStat.bot_id == bot_id
    ).group_by(models.TelegramGroupStat.chat_id)

    if search:
        subq = subq.having(func.max(models.TelegramGroupStat.chat_name).ilike(f"%{search}%"))

    groups = subq.order_by(func.max(models.TelegramGroupStat.date).desc()).all()

    # 取得此 bot 的 AI 開關設定
    settings = {
        s.chat_id: s.ai_enabled
        for s in db.query(models.TelegramGroupSetting).filter(
            models.TelegramGroupSetting.bot_id == bot_id
        ).all()
    }

    total = len(groups)
    offset = (page - 1) * page_size
    page_groups = groups[offset: offset + page_size]

    items = [
        {
            "chat_id": g.chat_id,
            "chat_name": g.chat_name,
            "chat_type": g.chat_type,
            "ai_enabled": settings.get(g.chat_id, True),
            "last_active": g.last_active,
        }
        for g in page_groups
    ]
    return {"total": total, "items": items}


@router.put("/{chat_id}")
def update_group_setting(
    chat_id: str,
    bot_id: int,
    ai_enabled: bool,
    db: Session = Depends(get_db),
    _=Depends(require_editor),
):
    setting = db.query(models.TelegramGroupSetting).filter(
        models.TelegramGroupSetting.bot_id == bot_id,
        models.TelegramGroupSetting.chat_id == chat_id,
    ).first()
    if setting:
        setting.ai_enabled = ai_enabled
    else:
        db.add(models.TelegramGroupSetting(
            bot_id=bot_id, chat_id=chat_id, ai_enabled=ai_enabled
        ))
    db.commit()
    return {"message": "已更新"}
