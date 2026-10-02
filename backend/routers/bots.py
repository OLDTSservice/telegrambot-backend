from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_viewer, require_page_edit, ensure_field_permissions, can_edit_page
from services.telegram_service import bot_manager

router = APIRouter(prefix="/api/bots", tags=["機器人管理"])
_EDIT_BOTS = require_page_edit("telegram_bots")
# 機器人設定被多個頁面共用：這些欄位除了「機器人管理」，也可由對應頁面的編輯權限修改
_NETWIN_PAGES = ("telegram_bots", "telegram_netwin")
_BOT_FIELD_PAGES = {
    "is_managed": ("telegram_bots", "telegram_live"),
    "whitelist_enabled": ("telegram_bots", "telegram_whitelist"),
    "netwin_query_enabled": _NETWIN_PAGES, "netwin_key_id": _NETWIN_PAGES, "netwin_api_key": _NETWIN_PAGES,
    "netwin_api_base_url": _NETWIN_PAGES, "netwin_threshold": _NETWIN_PAGES, "netwin_reply_zh": _NETWIN_PAGES,
    "netwin_reply_en": _NETWIN_PAGES, "netwin_reply_delay_seconds": _NETWIN_PAGES,
    "netwin_rtp_threshold": _NETWIN_PAGES,
}


def _mask(secret):
    return f"••••••{secret[-4:]}" if secret else secret


@router.get("", response_model=List[schemas.BotOut])
def list_bots(db: Session = Depends(get_db), current_user=Depends(require_viewer)):
    """各頁面共用的機器人下拉清單，登入即可讀取；但 Telegram Token 只給能編輯「機器人管理」的人、
    tjadmin 完整金鑰只給能編輯「機器人管理」或「查輸贏回覆」的人，其他人看到的是遮罩值
    （仍保留是否已設定的判斷，例如 Teams 查輸贏頁的「已設定」標示）。"""
    show_token = can_edit_page(current_user, "telegram_bots")
    show_netwin_key = can_edit_page(current_user, "telegram_bots", "telegram_netwin")
    out = []
    for bot in db.query(models.TelegramBot).all():
        item = schemas.BotOut.model_validate(bot).model_dump()
        if not show_token:
            item["token"] = _mask(item["token"])
        if not show_netwin_key:
            item["netwin_api_key"] = _mask(item.get("netwin_api_key"))
        out.append(item)
    return out


@router.post("", response_model=schemas.BotOut)
def create_bot(payload: schemas.BotCreate, db: Session = Depends(get_db), _=Depends(_EDIT_BOTS)):
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
def update_bot(bot_id: int, payload: schemas.BotUpdate, db: Session = Depends(get_db),
               current_user=Depends(require_page_edit("telegram_bots", "telegram_live",
                                                      "telegram_whitelist", "telegram_netwin"))):
    ensure_field_permissions(current_user, payload.model_dump(exclude_unset=True).keys(),
                             _BOT_FIELD_PAGES, ("telegram_bots",))
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
    if payload.is_managed is not None:
        bot.is_managed = payload.is_managed
    if payload.whitelist_enabled is not None:
        bot.whitelist_enabled = payload.whitelist_enabled
    if payload.game_asset_enabled is not None:
        bot.game_asset_enabled = payload.game_asset_enabled
    if payload.tada_asset_enabled is not None:
        bot.tada_asset_enabled = payload.tada_asset_enabled
    if payload.tada_gamelist_query_enabled is not None:
        bot.tada_gamelist_query_enabled = payload.tada_gamelist_query_enabled
    if payload.tada_certification_query_enabled is not None:
        bot.tada_certification_query_enabled = payload.tada_certification_query_enabled
    if payload.netwin_query_enabled is not None:
        bot.netwin_query_enabled = payload.netwin_query_enabled
    if payload.netwin_key_id is not None:
        bot.netwin_key_id = payload.netwin_key_id
    if payload.netwin_api_key is not None:
        bot.netwin_api_key = payload.netwin_api_key
    if payload.netwin_api_base_url is not None:
        bot.netwin_api_base_url = payload.netwin_api_base_url
    if payload.netwin_threshold is not None:
        bot.netwin_threshold = payload.netwin_threshold
    if payload.netwin_reply_zh is not None:
        bot.netwin_reply_zh = payload.netwin_reply_zh
    if payload.netwin_reply_en is not None:
        bot.netwin_reply_en = payload.netwin_reply_en
    if payload.netwin_reply_delay_seconds is not None:
        bot.netwin_reply_delay_seconds = payload.netwin_reply_delay_seconds
    if payload.netwin_rtp_threshold is not None:
        bot.netwin_rtp_threshold = payload.netwin_rtp_threshold
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
def restart_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(_EDIT_BOTS)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    bot_manager.stop_bot(bot_id)
    import time; time.sleep(1)
    bot_manager.start_bot(bot.id, bot.token, db)
    return {"message": f"機器人 {bot.name} 已重新啟動"}


@router.delete("/{bot_id}")
def delete_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(_EDIT_BOTS)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    bot_manager.stop_bot(bot_id)
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}
