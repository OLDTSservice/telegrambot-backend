from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/telegram-bot-admins", tags=["Telegram機器人管理員名單"])


@router.get("", response_model=List[schemas.TelegramBotAdminOut])
def list_bot_admins(bot_id: Optional[int] = None, db: Session = Depends(get_db), _=Depends(require_viewer)):
    q = db.query(models.TelegramBotAdmin)
    if bot_id is not None:
        q = q.filter(models.TelegramBotAdmin.bot_id == bot_id)
    return q.all()


@router.post("", response_model=schemas.TelegramBotAdminOut)
def create_bot_admin(payload: schemas.TelegramBotAdminCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == payload.bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    existing = db.query(models.TelegramBotAdmin).filter(
        models.TelegramBotAdmin.bot_id == payload.bot_id,
        models.TelegramBotAdmin.identifier == payload.identifier,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="此帳號已在管理員名單中")
    item = models.TelegramBotAdmin(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}", response_model=schemas.TelegramBotAdminOut)
def update_bot_admin(item_id: int, payload: schemas.TelegramBotAdminUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    item = db.query(models.TelegramBotAdmin).filter(models.TelegramBotAdmin.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="記錄不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_bot_admin(item_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    item = db.query(models.TelegramBotAdmin).filter(models.TelegramBotAdmin.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="記錄不存在")
    db.delete(item)
    db.commit()
    return {"message": "已刪除"}
