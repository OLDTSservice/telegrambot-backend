from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer
from services.telegram_service import bot_manager

router = APIRouter(prefix="/api/bots", tags=["機器人管理"])


@router.get("", response_model=List[schemas.BotOut])
def list_bots(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.TelegramBot).all()


@router.post("", response_model=schemas.BotOut)
def create_bot(payload: schemas.BotCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    if db.query(models.TelegramBot).filter(models.TelegramBot.token == payload.token).first():
        raise HTTPException(status_code=400, detail="Token 已存在")
    bot = models.TelegramBot(name=payload.name, token=payload.token)
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.put("/{bot_id}", response_model=schemas.BotOut)
def update_bot(bot_id: int, payload: schemas.BotUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    if payload.name is not None:
        bot.name = payload.name
    if payload.token is not None:
        existing = db.query(models.TelegramBot).filter(
            models.TelegramBot.token == payload.token,
            models.TelegramBot.id != bot_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Token 已被其他機器人使用")
        bot.token = payload.token
    if payload.is_enabled is not None:
        bot.is_enabled = payload.is_enabled
        if payload.is_enabled:
            bot_manager.start_bot(bot.id, bot.token, db)
        else:
            bot_manager.stop_bot(bot.id)
    db.commit()
    db.refresh(bot)
    return bot


@router.delete("/{bot_id}")
def delete_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    bot_manager.stop_bot(bot_id)
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}
