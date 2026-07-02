import asyncio
import threading
import logging
import time
from typing import Dict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

# ── 每人冷卻記錄（bot_id + user_id → 上次「無匹配」回應的時間戳）──────────
_no_match_ts: Dict[str, float] = {}
_COOLDOWN_SECS = 6        # 無匹配冷卻秒數
_MIN_TEXT_LEN  = 10       # 無匹配時最短回應字元數


class BotManager:
    def __init__(self):
        self._bots: Dict[int, threading.Thread] = {}
        self._loops: Dict[int, asyncio.AbstractEventLoop] = {}
        self._apps: Dict[int, Application] = {}

    def start_bot(self, bot_id: int, token: str, db):
        if bot_id in self._bots and self._bots[bot_id].is_alive():
            return

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loops[bot_id] = loop
            loop.run_until_complete(self._run_bot(bot_id, token))

        t = threading.Thread(target=run, daemon=True)
        self._bots[bot_id] = t
        t.start()
        logger.info(f"Bot {bot_id} 已啟動")

    def stop_bot(self, bot_id: int):
        if bot_id in self._apps:
            app = self._apps[bot_id]
            loop = self._loops.get(bot_id)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(app.stop(), loop)
                asyncio.run_coroutine_threadsafe(app.shutdown(), loop)
            del self._apps[bot_id]
        logger.info(f"Bot {bot_id} 已停止")

    def send_message(self, bot_id: int, chat_id: str, text: str, reply_to_message_id: int = None):
        """從後台主動向指定聊天室發送訊息（同步呼叫），可帶 reply_to_message_id 引用原訊息"""
        if bot_id not in self._apps or bot_id not in self._loops:
            raise ValueError(f"Bot {bot_id} 未在運行中")
        loop = self._loops[bot_id]
        app = self._apps[bot_id]
        kwargs = {"chat_id": int(chat_id), "text": text}
        if reply_to_message_id:
            kwargs["reply_to_message_id"] = reply_to_message_id
        future = asyncio.run_coroutine_threadsafe(
            app.bot.send_message(**kwargs),
            loop
        )
        future.result(timeout=10)

    async def _run_bot(self, bot_id: int, token: str):
        from database import SessionLocal
        try:
            app = Application.builder().token(token).build()
        except Exception as e:
            logger.error(f"Bot {bot_id} 建立失敗（Token 可能無效）：{e}")
            return

        self._apps[bot_id] = app

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            text = update.message.text.strip()
            db = SessionLocal()
            try:
                await self._process_message(bot_id, update, text, db)
            except Exception as e:
                logger.error(f"Bot {bot_id} 處理訊息時發生例外：{e}", exc_info=True)
                try:
                    await update.message.reply_text(f"⚠️ 處理訊息時發生錯誤，請稍後再試。")
                except Exception:
                    pass
            finally:
                db.close()

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        try:
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            logger.info(f"Bot {bot_id} polling 已啟動，等待訊息中...")
        except Exception as e:
            logger.error(f"Bot {bot_id} polling 啟動失敗：{e}")
            if bot_id in self._apps:
                del self._apps[bot_id]
            return

        # 保持運行直到被停止
        try:
            while bot_id in self._apps:
                await asyncio.sleep(1)
        finally:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception:
                pass

    async def _process_message(self, bot_id: int, update: Update, text: str, db):
        import models
        from services.ai_service import query_knowledge, record_usage

        bot_record = db.query(models.TelegramBot).filter(
            models.TelegramBot.id == bot_id,
            models.TelegramBot.is_enabled == True
        ).first()

        if not bot_record:
            return

        # 0. 忽略名單檢查
        sender_id = str(update.message.from_user.id) if update.message.from_user else None
        sender_username = (update.message.from_user.username or "").lower() if update.message.from_user else ""
        if sender_id or sender_username:
            ignores = db.query(models.TelegramIgnore).filter(
                models.TelegramIgnore.bot_id == bot_id,
                models.TelegramIgnore.is_enabled == True
            ).all()
            for ig in ignores:
                val = ig.identifier.lstrip("@").lower()
                if sender_id == val or sender_username == val:
                    logger.info(f"Bot {bot_id} 忽略來自 {ig.identifier} 的訊息")
                    return

        # 取得聊天室資訊（供統計使用）
        chat = update.message.chat
        chat_id = str(chat.id)
        chat_name = chat.title or chat.full_name or chat.username or f"Chat {chat.id}"
        chat_type = chat.type or "unknown"
        sender_name = update.message.from_user.full_name if update.message.from_user else None

        is_managed = bool(bot_record.is_managed)

        # 1. 先嘗試關鍵字規則比對
        rules = db.query(models.KeywordRule).filter(
            models.KeywordRule.bot_id == bot_id,
            models.KeywordRule.is_enabled == True
        ).all()

        tg_msg_id = update.message.message_id  # Telegram 原生訊息 ID

        for rule in rules:
            if rule.keyword.lower() in text.lower():
                if is_managed:
                    # 管控模式：記錄訊息 + 建立待發送回覆
                    msg = _save_live_message(bot_id, chat_id, chat_name, chat_type,
                                             sender_id, sender_name, text, db,
                                             telegram_message_id=tg_msg_id)
                    _save_pending_reply(bot_id, chat_id, msg.id, rule.reply_message, db)
                else:
                    await update.message.reply_text(rule.reply_message)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                return

        # 功能一：訊息少於 10 字元且關鍵字無匹配 → 跳過
        if len(text.strip()) < _MIN_TEXT_LEN:
            logger.debug(f"Bot {bot_id} 訊息長度 {len(text.strip())} < {_MIN_TEXT_LEN}，略過")
            return

        # 功能二：同一使用者的無匹配冷卻（6 秒內不重複 fallback）
        cooldown_key = f"{bot_id}:{sender_id or chat_id}"
        now = time.monotonic()
        last_ts = _no_match_ts.get(cooldown_key, 0)

        # 2. 嘗試知識庫 AI 回覆
        try:
            result = await asyncio.to_thread(query_knowledge, bot_id, text)
        except Exception as e:
            logger.error(f"Bot {bot_id} query_knowledge 發生例外：{e}", exc_info=True)
            result = None

        if result:
            reply, input_tokens, output_tokens = result
            if is_managed:
                # 管控模式：記錄訊息 + 建立待發送回覆
                msg = _save_live_message(bot_id, chat_id, chat_name, chat_type,
                                         sender_id, sender_name, text, db,
                                         telegram_message_id=tg_msg_id)
                _save_pending_reply(bot_id, chat_id, msg.id, reply, db)
            else:
                await update.message.reply_text(reply)
                record_usage(bot_id, input_tokens, output_tokens, db)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
        else:
            # 3. 沒有關鍵字規則也沒有知識庫結果
            if now - last_ts < _COOLDOWN_SECS:
                logger.debug(f"Bot {bot_id} 使用者 {cooldown_key} 冷卻中，略過 fallback")
                return
            _no_match_ts[cooldown_key] = now
            if not is_managed:
                await update.message.reply_text("您好，人員將會協助確認，請稍後")
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)


def _save_live_message(bot_id, chat_id, chat_name, chat_type, sender_id, sender_name, text, db, telegram_message_id=None):
    import models
    msg = models.TelegramMessage(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name, chat_type=chat_type,
        sender_id=sender_id, sender_name=sender_name, text=text, is_read=False,
        telegram_message_id=telegram_message_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _save_pending_reply(bot_id, chat_id, message_id, reply_text, db):
    import models
    pending = models.TelegramPendingReply(
        bot_id=bot_id, chat_id=chat_id, message_id=message_id,
        reply_text=reply_text, status="pending",
    )
    db.add(pending)
    db.commit()


def _record_group_stat(bot_id: int, chat_id: str, chat_name: str, chat_type: str, db):
    from datetime import date
    import models
    today = date.today().isoformat()
    stat = db.query(models.TelegramGroupStat).filter(
        models.TelegramGroupStat.bot_id == bot_id,
        models.TelegramGroupStat.chat_id == chat_id,
        models.TelegramGroupStat.date == today,
    ).first()
    if stat:
        stat.reply_count += 1
        stat.chat_name = chat_name  # 更新最新名稱
    else:
        stat = models.TelegramGroupStat(
            bot_id=bot_id, chat_id=chat_id, chat_name=chat_name,
            chat_type=chat_type, date=today, reply_count=1,
        )
        db.add(stat)
    try:
        db.commit()
    except Exception as e:
        logger.error(f"記錄群組統計失敗：{e}")
        db.rollback()


bot_manager = BotManager()


def start_all_enabled_bots(db):
    import models
    bots = db.query(models.TelegramBot).filter(models.TelegramBot.is_enabled == True).all()
    for bot in bots:
        try:
            bot_manager.start_bot(bot.id, bot.token, db)
        except Exception as e:
            logger.error(f"啟動機器人 {bot.id} 失敗：{e}")
