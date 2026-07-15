from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
import models
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/ai-rescue", tags=["AI救援"])


class RescueSettingOut(BaseModel):
    bot_id: int
    enabled: bool
    timeout_minutes: int

    class Config:
        from_attributes = True


class RescueSettingUpdate(BaseModel):
    enabled: bool
    timeout_minutes: int


@router.get("/{bot_id}", response_model=RescueSettingOut)
def get_setting(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    s = db.query(models.AIRescueSetting).filter(
        models.AIRescueSetting.bot_id == bot_id
    ).first()
    if not s:
        return RescueSettingOut(bot_id=bot_id, enabled=False, timeout_minutes=5)
    return s


@router.put("/{bot_id}")
def update_setting(
    bot_id: int,
    payload: RescueSettingUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_editor),
):
    s = db.query(models.AIRescueSetting).filter(
        models.AIRescueSetting.bot_id == bot_id
    ).first()
    if s:
        s.enabled = payload.enabled
        s.timeout_minutes = payload.timeout_minutes
    else:
        s = models.AIRescueSetting(
            bot_id=bot_id,
            enabled=payload.enabled,
            timeout_minutes=payload.timeout_minutes,
        )
        db.add(s)
    db.commit()
    return {"message": "已更新"}
