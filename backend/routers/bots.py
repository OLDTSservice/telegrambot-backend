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
    bot = models.TelegramBot(name=payload.name, token=payload.token, is_enabled=True)
    db.add(bot)
    db.commit()
    db.refresh(bot)
    # 新增後立即啟動 polling
    try:
        bot_manager.start_bot(bot.id, bot.token, db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"機器人 {bot.id} 啟動失敗：{e}")
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


@router.get("/{bot_id}/status")
def bot_status(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    is_polling = bot_id in bot_manager._apps
    thread_alive = bot_id in bot_manager._bots and bot_manager._bots[bot_id].is_alive()
    return {
        "bot_id": bot_id,
        "name": bot.name,
        "db_enabled": bot.is_enabled,
        "polling_active": is_polling,
        "thread_alive": thread_alive,
    }


@router.post("/{bot_id}/restart")
def restart_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    bot_manager.stop_bot(bot_id)
    import time; time.sleep(1)
    bot_manager.start_bot(bot.id, bot.token, db)
    return {"message": f"機器人 {bot.name} 已重新啟動"}


@router.delete("/{bot_id}")
def delete_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    bot_manager.stop_bot(bot_id)
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}
