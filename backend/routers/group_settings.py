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
    whitelist_vendor_check: bool = False
    whitelist_allowed_vendors: Optional[str] = None
    last_active: Optional[str]

    class Config:
        from_attributes = True


class GroupUpdateIn(BaseModel):
    bot_id: int
    ai_enabled: Optional[bool] = None
    whitelist_vendor_check: Optional[bool] = None
    whitelist_allowed_vendors: Optional[str] = None


@router.get("")
def list_groups(
    bot_id: int,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_viewer),
):
    # 取得每個 chat_id 最新日期的記錄（含最新群組名稱）
    latest_date_sq = db.query(
        models.TelegramGroupStat.chat_id,
        func.max(models.TelegramGroupStat.date).label("max_date"),
    ).filter(
        models.TelegramGroupStat.bot_id == bot_id
    ).group_by(models.TelegramGroupStat.chat_id).subquery()

    from sqlalchemy import and_
    rows = db.query(
        models.TelegramGroupStat.chat_id,
        models.TelegramGroupStat.chat_name,
        models.TelegramGroupStat.chat_type,
        models.TelegramGroupStat.date.label("last_active"),
    ).join(
        latest_date_sq,
        and_(
            models.TelegramGroupStat.chat_id == latest_date_sq.c.chat_id,
            models.TelegramGroupStat.date == latest_date_sq.c.max_date,
            models.TelegramGroupStat.bot_id == bot_id,
        )
    ).order_by(models.TelegramGroupStat.date.desc()).all()

    # 去重（同一天可能有多筆，取第一筆）
    seen = set()
    groups = []
    for r in rows:
        if r.chat_id not in seen:
            seen.add(r.chat_id)
            groups.append(r)

    if search:
        groups = [g for g in groups if search.lower() in g.chat_name.lower()]

    # 取得此 bot 的群組設定
    settings = {
        s.chat_id: s
        for s in db.query(models.TelegramGroupSetting).filter(
            models.TelegramGroupSetting.bot_id == bot_id
        ).all()
    }

    total = len(groups)
    offset = (page - 1) * page_size
    page_groups = groups[offset: offset + page_size]

    items = []
    for g in page_groups:
        s = settings.get(g.chat_id)
        items.append({
            "chat_id": g.chat_id,
            "chat_name": g.chat_name,
            "chat_type": g.chat_type,
            "ai_enabled": s.ai_enabled if s else True,
            "whitelist_vendor_check": s.whitelist_vendor_check if s else False,
            "whitelist_allowed_vendors": s.whitelist_allowed_vendors if s else None,
            "last_active": g.last_active,
        })
    return {"total": total, "items": items}


@router.put("/{chat_id}")
def update_group_setting(
    chat_id: str,
    payload: GroupUpdateIn,
    db: Session = Depends(get_db),
    _=Depends(require_editor),
):
    setting = db.query(models.TelegramGroupSetting).filter(
        models.TelegramGroupSetting.bot_id == payload.bot_id,
        models.TelegramGroupSetting.chat_id == chat_id,
    ).first()
    if setting:
        if payload.ai_enabled is not None:
            setting.ai_enabled = payload.ai_enabled
        if payload.whitelist_vendor_check is not None:
            setting.whitelist_vendor_check = payload.whitelist_vendor_check
        if payload.whitelist_allowed_vendors is not None:
            setting.whitelist_allowed_vendors = payload.whitelist_allowed_vendors
    else:
        db.add(models.TelegramGroupSetting(
            bot_id=payload.bot_id,
            chat_id=chat_id,
            ai_enabled=payload.ai_enabled if payload.ai_enabled is not None else True,
            whitelist_vendor_check=payload.whitelist_vendor_check or False,
            whitelist_allowed_vendors=payload.whitelist_allowed_vendors,
        ))
    db.commit()
    return {"message": "已更新"}
