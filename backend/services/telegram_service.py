import asyncio
import threading
import logging
from typing import Dict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)


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

        # 1. 先嘗試關鍵字規則比對
        rules = db.query(models.KeywordRule).filter(
            models.KeywordRule.bot_id == bot_id,
            models.KeywordRule.is_enabled == True
        ).all()

        for rule in rules:
            if rule.keyword.lower() in text.lower():
                await update.message.reply_text(rule.reply_message)
                return

        # 2. 嘗試知識庫 AI 回覆
        try:
            result = await asyncio.to_thread(query_knowledge, bot_id, text, db)
        except Exception as e:
            logger.error(f"Bot {bot_id} query_knowledge 發生例外：{e}", exc_info=True)
            result = None

        if result:
            reply, input_tokens, output_tokens = result
            await update.message.reply_text(reply)
            record_usage(bot_id, input_tokens, output_tokens, db)
        else:
            # 3. 沒有關鍵字規則也沒有知識庫結果時，回傳備用訊息
            await update.message.reply_text("抱歉，我目前無法回答這個問題，請換個方式詢問或聯繫客服。")


bot_manager = BotManager()


def start_all_enabled_bots(db):
    import models
    bots = db.query(models.TelegramBot).filter(models.TelegramBot.is_enabled == True).all()
    for bot in bots:
        try:
            bot_manager.start_bot(bot.id, bot.token, db)
        except Exception as e:
            logger.error(f"啟動機器人 {bot.id} 失敗：{e}")
