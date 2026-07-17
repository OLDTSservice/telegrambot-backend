from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer as SaInteger
from typing import List
from datetime import datetime, date
from database import get_db
import models, schemas
from auth import require_editor, require_viewer
from services.telegram_service import bot_manager

router = APIRouter(prefix="/api/telegram-live", tags=["即時對話管控"])


@router.get("/groups", response_model=List[schemas.ChatGroupOut])
def list_groups(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    """取得該機器人所有有訊息的群組，按最新訊息排序"""
    rows = (
        db.query(
            models.TelegramMessage.chat_id,
            models.TelegramMessage.chat_name,
            models.TelegramMessage.chat_type,
            func.max(models.TelegramMessage.created_at).label("last_message_at"),
            func.sum(
                (models.TelegramMessage.is_read == False).cast(SaInteger)
            ).label("unread_count"),
        )
        .filter(
            models.TelegramMessage.bot_id == bot_id,
            models.TelegramMessage.is_from_admin == False,
        )
        .group_by(
            models.TelegramMessage.chat_id,
            models.TelegramMessage.chat_name,
            models.TelegramMessage.chat_type,
        )
        .order_by(func.max(models.TelegramMessage.created_at).desc())
        .all()
    )

    result = []
    for r in rows:
        pending_count = (
            db.query(models.TelegramPendingReply)
            .filter(
                models.TelegramPendingReply.bot_id == bot_id,
                models.TelegramPendingReply.chat_id == r.chat_id,
                models.TelegramPendingReply.status == "pending",
            )
            .count()
        )
        result.append(schemas.ChatGroupOut(
            chat_id=r.chat_id,
            chat_name=r.chat_name,
            chat_type=r.chat_type,
            last_message_at=r.last_message_at,
            unread_count=int(r.unread_count or 0),
            pending_count=pending_count,
        ))
    return result


@router.get("/messages", response_model=List[schemas.TelegramMessageOut])
def get_messages(bot_id: int, chat_id: str, db: Session = Depends(get_db), _=Depends(require_viewer)):
    """取得指定群組的最新 100 則訊息（含待發送回覆）"""
    msgs = (
        db.query(models.TelegramMessage)
        .filter(
            models.TelegramMessage.bot_id == bot_id,
            models.TelegramMessage.chat_id == chat_id,
        )
        .order_by(models.TelegramMessage.created_at.asc())
        .limit(100)
        .all()
    )
    return msgs


@router.put("/read")
def mark_read(bot_id: int, chat_id: str, db: Session = Depends(get_db), _=Depends(require_viewer)):
    """將指定群組的訊息全部標為已讀"""
    db.query(models.TelegramMessage).filter(
        models.TelegramMessage.bot_id == bot_id,
        models.TelegramMessage.chat_id == chat_id,
        models.TelegramMessage.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"ok": True}


@router.post("/send")
def send_message(payload: schemas.LiveSendRequest, db: Session = Depends(get_db), _=Depends(require_editor)):
    """後台手動發送訊息到指定群組"""
    try:
        bot_manager.send_message(payload.bot_id, payload.chat_id, payload.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 記錄為後台發送的訊息（is_from_admin=True）
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == payload.bot_id).first()
    # 取得群組名稱
    last_msg = (
        db.query(models.TelegramMessage)
        .filter(
            models.TelegramMessage.bot_id == payload.bot_id,
            models.TelegramMessage.chat_id == payload.chat_id,
        )
        .order_by(models.TelegramMessage.created_at.desc())
        .first()
    )
    chat_name = last_msg.chat_name if last_msg else payload.chat_id
    chat_type = last_msg.chat_type if last_msg else "unknown"

    msg = models.TelegramMessage(
        bot_id=payload.bot_id,
        chat_id=payload.chat_id,
        chat_name=chat_name,
        chat_type=chat_type,
        sender_name="後台管理員",
        text=payload.text,
        is_read=True,
        is_from_admin=True,
    )
    db.add(msg)
    db.commit()

    # 自動開單
    import threading
    from services.telegram_service import _create_freshdesk_ticket_bg
    # 取得最後一則用戶訊息作為問題
    user_msg = (
        db.query(models.TelegramMessage)
        .filter(
            models.TelegramMessage.bot_id == payload.bot_id,
            models.TelegramMessage.chat_id == payload.chat_id,
            models.TelegramMessage.is_from_admin == False,
        )
        .order_by(models.TelegramMessage.created_at.desc())
        .first()
    )
    question = user_msg.text if user_msg else payload.text
    threading.Thread(
        target=_create_freshdesk_ticket_bg,
        args=(question, payload.text, chat_name),
        daemon=True,
    ).start()

    return {"ok": True}


@router.put("/pending/{pending_id}")
def update_pending(pending_id: int, payload: schemas.PendingReplyUpdate,
                   db: Session = Depends(get_db), _=Depends(require_editor)):
    """編輯待發送回覆的內容"""
    pending = db.query(models.TelegramPendingReply).filter(
        models.TelegramPendingReply.id == pending_id,
        models.TelegramPendingReply.status == "pending",
    ).first()
    if not pending:
        raise HTTPException(status_code=404, detail="找不到待發送回覆")
    pending.reply_text = payload.reply_text
    db.commit()
    return {"ok": True}


@router.post("/pending/{pending_id}/send")
def send_pending(pending_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    """發送待審回覆"""
    pending = db.query(models.TelegramPendingReply).filter(
        models.TelegramPendingReply.id == pending_id,
        models.TelegramPendingReply.status == "pending",
    ).first()
    if not pending:
        raise HTTPException(status_code=404, detail="找不到待發送回覆")

    # 取得對應的原始訊息（含 telegram_message_id 供引用回覆）
    last_msg = db.query(models.TelegramMessage).filter(
        models.TelegramMessage.id == pending.message_id
    ).first()

    try:
        bot_manager.send_message(
            pending.bot_id, pending.chat_id, pending.reply_text,
            reply_to_message_id=last_msg.telegram_message_id if last_msg else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pending.status = "sent"
    pending.sent_at = datetime.utcnow()
    admin_msg = models.TelegramMessage(
        bot_id=pending.bot_id,
        chat_id=pending.chat_id,
        chat_name=last_msg.chat_name if last_msg else pending.chat_id,
        chat_type=last_msg.chat_type if last_msg else "unknown",
        sender_name="後台機器人（已發送）",
        text=pending.reply_text,
        is_read=True,
        is_from_admin=True,
    )
    db.add(admin_msg)
    db.commit()

    # 更新回覆統計
    if last_msg:
        today = date.today().isoformat()
        stat = db.query(models.TelegramGroupStat).filter(
            models.TelegramGroupStat.bot_id == pending.bot_id,
            models.TelegramGroupStat.chat_id == pending.chat_id,
            models.TelegramGroupStat.date == today,
        ).first()
        if stat:
            stat.reply_count += 1
        else:
            db.add(models.TelegramGroupStat(
                bot_id=pending.bot_id, chat_id=pending.chat_id,
                chat_name=last_msg.chat_name, chat_type=last_msg.chat_type,
                date=today, reply_count=1,
            ))
        db.commit()

    # 自動開單（與 AI 回覆相同流程）
    if last_msg:
        import threading
        from services.telegram_service import _create_freshdesk_ticket_bg
        threading.Thread(
            target=_create_freshdesk_ticket_bg,
            args=(last_msg.text, pending.reply_text, last_msg.chat_name),
            daemon=True,
        ).start()

    return {"ok": True}


@router.delete("/pending/{pending_id}")
def discard_pending(pending_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    """捨棄待發送回覆"""
    pending = db.query(models.TelegramPendingReply).filter(
        models.TelegramPendingReply.id == pending_id,
        models.TelegramPendingReply.status == "pending",
    ).first()
    if not pending:
        raise HTTPException(status_code=404, detail="找不到待發送回覆")
    pending.status = "discarded"
    db.commit()
    return {"ok": True}
