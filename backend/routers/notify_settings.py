from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
import models
from auth import require_page_view, require_page_edit

router = APIRouter(prefix="/api/notify-settings", tags=["通知設定"])
_VIEW = require_page_view("telegram_bots")
_EDIT = require_page_edit("telegram_bots")


class NotifySettingOut(BaseModel):
    bot_id: Optional[int] = None
    chat_id: Optional[str] = None
    chat_name: Optional[str] = None
    enabled: bool = False

    class Config:
        from_attributes = True


class NotifySettingIn(BaseModel):
    bot_id: int
    chat_id: str
    chat_name: str
    enabled: bool


@router.get("", response_model=NotifySettingOut)
def get_setting(db: Session = Depends(get_db), _=Depends(_VIEW)):
    setting = db.query(models.NotifySetting).first()
    if not setting:
        return NotifySettingOut()
    return setting


@router.put("")
def upsert_setting(payload: NotifySettingIn, db: Session = Depends(get_db), _=Depends(_EDIT)):
    setting = db.query(models.NotifySetting).first()
    if setting:
        setting.bot_id = payload.bot_id
        setting.chat_id = payload.chat_id
        setting.chat_name = payload.chat_name
        setting.enabled = payload.enabled
    else:
        setting = models.NotifySetting(
            bot_id=payload.bot_id,
            chat_id=payload.chat_id,
            chat_name=payload.chat_name,
            enabled=payload.enabled,
        )
        db.add(setting)
    db.commit()
    return {"message": "已更新"}
