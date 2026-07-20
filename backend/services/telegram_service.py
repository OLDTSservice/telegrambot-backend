import asyncio
import threading
import logging
import time
import requests
from typing import Dict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

# ── 每人冷卻記錄（bot_id + user_id → 上次「無匹配」回應的時間戳）──────────
_no_match_ts: Dict[str, float] = {}
_COOLDOWN_SECS = 6        # 無匹配冷卻秒數
_MIN_TEXT_LEN  = 10       # 無匹配時最短回應字元數

def _is_application_form(text: str) -> bool:
    """
    偵測結構化申請表單：多行含「數字編號 + 冒號欄位」格式
    例：1. 商戶名字：xxx  /  2. Domain URL：xxx
    條件：至少 3 行符合「編號. 內容：值」或「編號.內容：值」格式
    """
    import re
    lines = text.splitlines()
    # 符合「數字. 任意內容 ：或: 任意內容」的行
    field_line = re.compile(r'^\s*\d+[\.\、]\s*.+[：:].+')
    matched = sum(1 for line in lines if field_line.match(line))
    return matched >= 3


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

        # 每次收到訊息都更新群組名稱（確保改名後能同步）
        _refresh_chat_name(bot_id, chat_id, chat_name, db)

        # 0.5. 後台白名單自動處理（優先於關鍵字/KB，管控模式下仍執行）
        # 預先讀取該群組的廠商驗證設定（whitelist_service 需要）
        _group_wl = db.query(models.TelegramGroupSetting).filter(
            models.TelegramGroupSetting.bot_id == bot_id,
            models.TelegramGroupSetting.chat_id == chat_id,
        ).first()
        allowed_vendors: list = []
        if (_group_wl and _group_wl.whitelist_vendor_check
                and _group_wl.whitelist_allowed_vendors):
            allowed_vendors = [
                v.strip() for v in _group_wl.whitelist_allowed_vendors.split(',')
                if v.strip()
            ]

        if bot_record.whitelist_enabled:
            from services.whitelist_service import detect_whitelist_request, parse_whitelist_request, run_whitelist_sync
            if detect_whitelist_request(text):
                vendor_code, all_parts, ips = parse_whitelist_request(text)
                if all_parts and ips:
                    logger.info(f"Bot {bot_id} 偵測到白名單請求：帳號數={len(all_parts)}, IPs={ips}")
                    any_success = False
                    any_vendor_rejected = False
                    import re as _re_wl
                    _wl_is_chinese = bool(_re_wl.search(r'[一-鿿㐀-䶿]', text))
                    for username_parts in all_parts:
                        logger.info(f"Bot {bot_id} 處理帳號：{username_parts}")
                        try:
                            success, matched_vendor, vendor_rejected = await asyncio.to_thread(run_whitelist_sync, username_parts, ips, allowed_vendors)
                        except Exception as e:
                            logger.error(f"Bot {bot_id} 白名單自動化例外：{e}", exc_info=True)
                            success, matched_vendor, vendor_rejected = False, None, False
                        log_vendor = matched_vendor or (username_parts[0] if username_parts else "unknown")
                        _save_whitelist_log(bot_id, chat_id, chat_name,
                                            log_vendor, "\n".join(ips),
                                            "success" if success else "failed", db)
                        if success:
                            any_success = True
                        if vendor_rejected:
                            any_vendor_rejected = True
                    logger.info(f"Bot {bot_id} 白名單處理完畢，any_success={any_success}, any_vendor_rejected={any_vendor_rejected}")
                    if any_success:
                        try:
                            await update.message.reply_text("Done")
                            logger.info(f"Bot {bot_id} 已回覆 Done")
                        except Exception as e:
                            logger.error(f"Bot {bot_id} 回覆 Done 失敗：{e}", exc_info=True)
                        threading.Thread(
                            target=_create_freshdesk_ticket_bg,
                            args=(text, "Done", chat_name), daemon=True
                        ).start()
                    elif any_vendor_rejected:
                        _wl_reject_reply = (
                            "您好，人員將會協助確認，請稍後"
                            if _wl_is_chinese
                            else "Hello, our team will assist you shortly. Please wait."
                        )
                        try:
                            await update.message.reply_text(_wl_reject_reply)
                            logger.info(f"Bot {bot_id} 廠商驗證拒絕，已回覆固定訊息（{'中文' if _wl_is_chinese else '英文'}）")
                        except Exception as e:
                            logger.error(f"Bot {bot_id} 回覆廠商拒絕訊息失敗：{e}", exc_info=True)
                    # 其他失敗（廠商無法解析、登入失敗等）靜默，不回覆
                    return
                else:
                    logger.warning(f"Bot {bot_id} 白名單請求解析失敗（無法取得廠商或IP）")

        # 1. 先嘗試關鍵字規則比對
        rules = db.query(models.KeywordRule).filter(
            models.KeywordRule.bot_id == bot_id,
            models.KeywordRule.is_enabled == True
        ).all()

        tg_msg_id = update.message.message_id  # Telegram 原生訊息 ID

        import re as _re
        _is_chinese = bool(_re.search(r'[一-鿿㐀-䶿]', text))

        for rule in rules:
            if rule.keyword.lower() in text.lower():
                reply_text = (
                    rule.reply_message
                    if _is_chinese or not rule.reply_message_en
                    else rule.reply_message_en
                )
                if is_managed:
                    # 管控模式：記錄訊息 + 建立待發送回覆
                    msg = _save_live_message(bot_id, chat_id, chat_name, chat_type,
                                             sender_id, sender_name, text, db,
                                             telegram_message_id=tg_msg_id)
                    _save_pending_reply(bot_id, chat_id, msg.id, reply_text, db)
                else:
                    await update.message.reply_text(reply_text)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    threading.Thread(target=_create_freshdesk_ticket_bg, args=(text, reply_text, chat_name), daemon=True).start()
                return

        # 功能一：訊息少於 10 字元且關鍵字無匹配 → 跳過
        if len(text.strip()) < _MIN_TEXT_LEN:
            logger.debug(f"Bot {bot_id} 訊息長度 {len(text.strip())} < {_MIN_TEXT_LEN}，略過")
            return

        # 功能一-b：申請表單格式偵測 → 跳過知識庫，直接 fallback
        if _is_application_form(text):
            logger.info(f"Bot {bot_id} 偵測到申請表單格式，跳過知識庫直接 fallback")
            import re
            fallback_msg = (
                "您好，人員將會協助確認，請稍後"
                if re.search(r'[一-鿿㐀-䶿]', text)
                else "Hello, our team will assist you shortly. Please wait."
            )
            await update.message.reply_text(fallback_msg)
            _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
            _save_no_answer_log(bot_id, chat_id, chat_name, text, db)
            return

        # 功能二：同一使用者的無匹配冷卻（6 秒內不重複 fallback）
        cooldown_key = f"{bot_id}:{sender_id or chat_id}"
        now = time.monotonic()
        last_ts = _no_match_ts.get(cooldown_key, 0)

        # 2. 檢查此群組是否啟用 AI 問答
        group_setting = db.query(models.TelegramGroupSetting).filter(
            models.TelegramGroupSetting.bot_id == bot_id,
            models.TelegramGroupSetting.chat_id == chat_id,
        ).first()
        if group_setting and not group_setting.ai_enabled:
            logger.info(f"Bot {bot_id} 群組 {chat_id} AI 問答已關閉，跳過知識庫查詢")
            # 救援功能：記錄候選訊息 / 標記已被直接回覆
            rescue_setting = db.query(models.AIRescueSetting).filter(
                models.AIRescueSetting.bot_id == bot_id,
                models.AIRescueSetting.enabled == True,
            ).first()
            if rescue_setting:
                reply_to_id = (
                    update.message.reply_to_message.message_id
                    if update.message.reply_to_message else None
                )
                if reply_to_id:
                    # 若此訊息是直接 reply 某則候選 → 標記已被人工回應
                    candidate = db.query(models.AIRescueCandidate).filter(
                        models.AIRescueCandidate.bot_id == bot_id,
                        models.AIRescueCandidate.chat_id == chat_id,
                        models.AIRescueCandidate.telegram_message_id == reply_to_id,
                        models.AIRescueCandidate.is_handled == False,
                    ).first()
                    if candidate:
                        from datetime import datetime
                        candidate.is_handled = True
                        candidate.handled_at = datetime.utcnow()
                        try:
                            db.commit()
                            logger.info(f"[Rescue] 候選訊息 {reply_to_id} 已被人工回覆，標記 handled")
                        except Exception:
                            db.rollback()
                else:
                    # 非 reply 訊息 → 存為新的救援候選
                    _save_rescue_candidate(
                        bot_id, chat_id, chat_name, chat_type,
                        sender_id, sender_name, text,
                        update.message.message_id, db
                    )
            return

        # 3. 嘗試知識庫 AI 回覆
        try:
            result = await asyncio.to_thread(query_knowledge, bot_id, text)
        except Exception as e:
            logger.error(f"Bot {bot_id} query_knowledge 發生例外：{e}", exc_info=True)
            result = None

        # result = (reply, in_tok, out_tok, cache_read, cache_write)
        reply, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = \
            result if result else (None, 0, 0, 0, 0)

        if input_tokens or cache_read_tokens:
            record_usage(bot_id, input_tokens, output_tokens, db,
                         cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens)

        if is_managed:
            # 管控模式：無論 KB 是否找到答案，都記錄訊息讓管理員處理
            msg = _save_live_message(bot_id, chat_id, chat_name, chat_type,
                                     sender_id, sender_name, text, db,
                                     telegram_message_id=tg_msg_id)
            if reply:
                _save_pending_reply(bot_id, chat_id, msg.id, reply, db)
                logger.info(f"Bot {bot_id} 管控模式：已儲存訊息 + 待發回覆")
            else:
                logger.info(f"Bot {bot_id} 管控模式：已儲存訊息（無 KB 答案，等待管理員手動回覆）")
        else:
            if reply:
                await update.message.reply_text(reply)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                _save_conversation_log(bot_id, chat_id, chat_name, text, reply, db,
                                       input_tokens=input_tokens, output_tokens=output_tokens,
                                       cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens)
                threading.Thread(target=_create_freshdesk_ticket_bg, args=(text, reply, chat_name), daemon=True).start()
            else:
                # 沒有關鍵字規則也沒有知識庫結果 → fallback（含冷卻）
                if now - last_ts < _COOLDOWN_SECS:
                    logger.debug(f"Bot {bot_id} 使用者 {cooldown_key} 冷卻中，略過 fallback")
                    return
                _no_match_ts[cooldown_key] = now
                import re
                fallback_msg = (
                    "您好，人員將會協助確認，請稍後"
                    if re.search(r'[一-鿿㐀-䶿]', text)
                    else "Hello, our team will assist you shortly. Please wait."
                )
                await update.message.reply_text(fallback_msg)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                _save_no_answer_log(bot_id, chat_id, chat_name, text, db,
                                    input_tokens=input_tokens, output_tokens=output_tokens,
                                    cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens)


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


def _refresh_chat_name(bot_id: int, chat_id: str, chat_name: str, db):
    """每次收到訊息時，把最新群組名稱同步到最近一筆 stat 記錄，不影響計數。"""
    import models
    latest = db.query(models.TelegramGroupStat).filter(
        models.TelegramGroupStat.bot_id == bot_id,
        models.TelegramGroupStat.chat_id == chat_id,
    ).order_by(models.TelegramGroupStat.date.desc()).first()
    if latest and latest.chat_name != chat_name:
        latest.chat_name = chat_name
        try:
            db.commit()
        except Exception:
            db.rollback()


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


def _save_conversation_log(bot_id, chat_id, chat_name, question, answer, db,
                            input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0):
    import models
    from datetime import datetime, timedelta
    log = models.ConversationLog(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name,
        question=question, answer=answer,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens,
    )
    db.add(log)
    try:
        db.commit()
        cutoff = datetime.utcnow() - timedelta(days=7)
        db.query(models.ConversationLog).filter(
            models.ConversationLog.created_at < cutoff
        ).delete()
        db.commit()
    except Exception as e:
        logger.error(f"儲存對話 log 失敗：{e}")
        db.rollback()


def _save_no_answer_log(bot_id, chat_id, chat_name, question, db,
                         input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0):
    import models
    from datetime import datetime, timedelta
    log = models.NoAnswerLog(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name, question=question,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens,
    )
    db.add(log)
    try:
        db.commit()
        cutoff = datetime.utcnow() - timedelta(days=7)
        db.query(models.NoAnswerLog).filter(
            models.NoAnswerLog.created_at < cutoff
        ).delete()
        db.commit()
    except Exception as e:
        logger.error(f"儲存無解答 log 失敗：{e}")
        db.rollback()


def _save_whitelist_log(bot_id, chat_id, chat_name, vendor_name, ip_list, status, db):
    import models
    log = models.WhitelistLog(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name,
        vendor_name=vendor_name, ip_list=ip_list, status=status,
    )
    db.add(log)
    try:
        db.commit()
    except Exception as e:
        logger.error(f"儲存白名單 log 失敗：{e}")
        db.rollback()


def _save_rescue_candidate(bot_id, chat_id, chat_name, chat_type,
                            sender_id, sender_name, text, telegram_message_id, db):
    import models
    existing = db.query(models.AIRescueCandidate).filter(
        models.AIRescueCandidate.bot_id == bot_id,
        models.AIRescueCandidate.chat_id == chat_id,
        models.AIRescueCandidate.telegram_message_id == telegram_message_id,
    ).first()
    if existing:
        return
    candidate = models.AIRescueCandidate(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name, chat_type=chat_type,
        telegram_message_id=telegram_message_id, text=text,
        sender_id=sender_id, sender_name=sender_name,
    )
    db.add(candidate)
    try:
        db.commit()
        logger.debug(f"[Rescue] 已記錄候選訊息 msg_id={telegram_message_id} chat={chat_id}")
    except Exception as e:
        logger.error(f"[Rescue] 儲存候選失敗: {e}")
        db.rollback()


def _send_notify_message(ticket_id, group_name: str, error_msg: str = None):
    """發送 Freshdesk 工單建立通知到指定 Telegram 群組"""
    try:
        from database import SessionLocal
        import models as _models
        db = SessionLocal()
        try:
            setting = db.query(_models.NotifySetting).filter(
                _models.NotifySetting.enabled == True
            ).first()
            if not setting:
                return
            success = ticket_id is not None
            lines = [
                f"群組名稱：{group_name}",
                f"建立狀態：{'✅ 成功' if success else '❌ 失敗'}",
            ]
            if success:
                lines.append(f"工單編號：#{ticket_id}")
            else:
                lines.append(f"失敗原因：{error_msg or '未知錯誤'}")
            text = "\n".join(lines)
            bot_manager.send_message(setting.bot_id, setting.chat_id, text)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Notify] 發送通知失敗: {e}")


def _create_freshdesk_ticket_bg(question: str, answer: str, group_name: str):
    """背景建立 Freshdesk 工單，不阻擋 bot 回覆流程"""
    ticket_id = None
    error_msg = None
    try:
        resp = requests.post(
            "https://freshdesk-ticket-creation.onrender.com/api/create-ticket-from-bot",
            json={"question": question, "answer": answer, "group_name": group_name},
            timeout=30,
        )
        if resp.ok:
            ticket_id = resp.json().get('id')
            logger.info(f"[Freshdesk] 工單建立成功 ID={ticket_id} group={group_name}")
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(f"[Freshdesk] 建單失敗 {resp.status_code}: {resp.text[:500]}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Freshdesk] 建單例外: {e}")
    _send_notify_message(ticket_id, group_name, error_msg)
