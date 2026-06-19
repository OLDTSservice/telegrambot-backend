from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/telegram-ignores", tags=["Telegram忽略名單"])


@router.get("", response_model=List[schemas.TelegramIgnoreOut])
def list_ignores(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.TelegramIgnore).all()


@router.post("", response_model=schemas.TelegramIgnoreOut)
def create_ignore(payload: schemas.TelegramIgnoreCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == payload.bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    existing = db.query(models.TelegramIgnore).filter(
        models.TelegramIgnore.bot_id == payload.bot_id,
        models.TelegramIgnore.identifier == payload.identifier,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="此帳號已在忽略名單中")
    item = models.TelegramIgnore(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}", response_model=schemas.TelegramIgnoreOut)
def update_ignore(item_id: int, payload: schemas.TelegramIgnoreUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    item = db.query(models.TelegramIgnore).filter(models.TelegramIgnore.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="記錄不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_ignore(item_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    item = db.query(models.TelegramIgnore).filter(models.TelegramIgnore.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="記錄不存在")
    db.delete(item)
    db.commit()
    return {"message": "已刪除"}
