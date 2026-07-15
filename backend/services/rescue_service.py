import asyncio
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _is_question(text: str) -> bool:
    """用 Claude Haiku 判斷訊息是否為需要回答的問題（排除問候/感謝等短語）"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            system="只回答 yes 或 no，不要其他內容。",
            messages=[{
                "role": "user",
                "content": (
                    "判斷以下訊息是否為需要人員或 AI 回答的問題。\n"
                    "如果是問題（包含詢問、請求協助、反映問題等）回答 yes。\n"
                    "如果是問候、感謝、簡短短句（謝謝、你好、OK、收到 等）回答 no。\n\n"
                    f"訊息：{text}"
                ),
            }],
        )
        return response.content[0].text.strip().lower().startswith("y")
    except Exception as e:
        logger.error(f"[Rescue] _is_question 失敗: {e}")
        return False


async def _run_rescue_check():
    """每次執行一輪救援掃描"""
    from database import SessionLocal
    import models
    from services.ai_service import query_knowledge, record_usage
    from services.telegram_service import bot_manager

    db = SessionLocal()
    try:
        settings = db.query(models.AIRescueSetting).filter(
            models.AIRescueSetting.enabled == True
        ).all()

        for setting in settings:
            bot = db.query(models.TelegramBot).filter(
                models.TelegramBot.id == setting.bot_id,
                models.TelegramBot.is_enabled == True,
            ).first()
            if not bot:
                continue

            cutoff = datetime.utcnow() - timedelta(minutes=setting.timeout_minutes)

            # 取得逾時未處理的候選訊息
            candidates = db.query(models.AIRescueCandidate).filter(
                models.AIRescueCandidate.bot_id == setting.bot_id,
                models.AIRescueCandidate.is_handled == False,
                models.AIRescueCandidate.created_at <= cutoff,
            ).all()

            # 每個群組只取最新一則
            chat_latest: dict[str, models.AIRescueCandidate] = {}
            for c in candidates:
                if c.chat_id not in chat_latest or c.created_at > chat_latest[c.chat_id].created_at:
                    chat_latest[c.chat_id] = c

            for chat_id, candidate in chat_latest.items():
                logger.info(f"[Rescue] Bot {setting.bot_id} 群組 {chat_id} 候選訊息逾時，開始救援")

                # 先標記同群組所有舊候選為 handled，避免重複處理
                db.query(models.AIRescueCandidate).filter(
                    models.AIRescueCandidate.bot_id == setting.bot_id,
                    models.AIRescueCandidate.chat_id == chat_id,
                    models.AIRescueCandidate.is_handled == False,
                ).update({"is_handled": True, "handled_at": datetime.utcnow()})
                db.commit()

                # 判斷是否為問題
                is_q = await asyncio.to_thread(_is_question, candidate.text)
                if not is_q:
                    logger.info(f"[Rescue] 訊息非問題，略過: {candidate.text[:50]}")
                    continue

                # 查詢知識庫
                import re
                result = await asyncio.to_thread(query_knowledge, setting.bot_id, candidate.text)
                reply = None
                in_tok = out_tok = cache_read = cache_write = 0

                if result:
                    reply, in_tok, out_tok, cache_read, cache_write = result

                if not reply:
                    # KB 無答案 → 發送語言對應的固定回覆
                    reply = (
                        "您好，人員將會協助確認，請稍後"
                        if re.search(r'[一-鿿㐀-䶿]', candidate.text)
                        else "Hello, our team will assist you shortly. Please wait."
                    )
                    logger.info(f"[Rescue] 知識庫無答案，改發固定回覆")

                # 發送回覆（引用原訊息）
                try:
                    bot_manager.send_message(
                        setting.bot_id, chat_id, reply,
                        reply_to_message_id=candidate.telegram_message_id,
                    )
                    if in_tok or cache_read:
                        record_usage(setting.bot_id, in_tok, out_tok, db,
                                     cache_read_tokens=cache_read, cache_write_tokens=cache_write)
                    logger.info(
                        f"[Rescue] Bot {setting.bot_id} 已救援群組 {chat_id}，"
                        f"引用訊息 {candidate.telegram_message_id}"
                    )
                except Exception as e:
                    logger.error(f"[Rescue] 發送回覆失敗: {e}")

    except Exception as e:
        logger.error(f"[Rescue] 掃描例外: {e}", exc_info=True)
    finally:
        db.close()


async def rescue_loop():
    """每分鐘執行一次救援掃描，掛載於 FastAPI lifespan"""
    logger.info("[Rescue] 背景救援排程已啟動")
    while True:
        await asyncio.sleep(60)
        try:
            await _run_rescue_check()
        except Exception as e:
            logger.error(f"[Rescue] loop 頂層例外: {e}")
