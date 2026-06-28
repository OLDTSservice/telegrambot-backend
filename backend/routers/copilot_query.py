"""
Copilot Studio 整合端點
Copilot Studio 透過 HTTP 動作 POST 到此端點，取得回覆後傳送給 Teams 使用者
"""
import asyncio
import logging
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import models, schemas

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/copilot", tags=["Copilot查詢"])


def _record_stat(bot_id: int, conversation_id: str, conversation_name: str, db: Session):
    today = date.today().isoformat()
    stat = db.query(models.CopilotGroupStat).filter(
        models.CopilotGroupStat.bot_id == bot_id,
        models.CopilotGroupStat.conversation_id == conversation_id,
        models.CopilotGroupStat.date == today,
    ).first()
    if stat:
        stat.reply_count += 1
        stat.conversation_name = conversation_name
    else:
        stat = models.CopilotGroupStat(
            bot_id=bot_id, conversation_id=conversation_id,
            conversation_name=conversation_name, date=today, reply_count=1,
        )
        db.add(stat)
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Copilot 統計記錄失敗：{e}")
        db.rollback()


def _query_copilot_knowledge(bot_id: int, question: str) -> tuple | None:
    from services.ai_service import _score_chunks, _call_claude, _chunk_text
    from database import SessionLocal
    import models as m

    db = SessionLocal()
    try:
        docs = db.query(m.CopilotKnowledgeDoc).filter(
            m.CopilotKnowledgeDoc.bot_id == bot_id,
            m.CopilotKnowledgeDoc.is_enabled == True,
        ).all()
        if not docs:
            return None

        doc_ids = [d.id for d in docs]
        all_chunks = db.query(m.CopilotKnowledgeChunk).filter(
            m.CopilotKnowledgeChunk.doc_id.in_(doc_ids)
        ).all()
        if not all_chunks:
            return None

        top_chunks = _score_chunks(question, all_chunks)
        return _call_claude(question, top_chunks, bot_id)
    finally:
        db.close()


@router.post("/query")
async def copilot_query(payload: schemas.CopilotQueryRequest, db: Session = Depends(get_db)):
    bot = db.query(models.CopilotBot).filter(
        models.CopilotBot.id == payload.bot_id,
        models.CopilotBot.is_enabled == True,
    ).first()
    if not bot:
        return {"answer": "機器人不存在或未啟用"}

    question = payload.question.strip()
    conv_id = payload.conversation_id
    conv_name = payload.conversation_name

    # 1. 關鍵字規則
    rules = db.query(models.CopilotKeywordRule).filter(
        models.CopilotKeywordRule.bot_id == payload.bot_id,
        models.CopilotKeywordRule.is_enabled == True,
    ).all()
    for rule in rules:
        if rule.keyword.lower() in question.lower():
            _record_stat(payload.bot_id, conv_id, conv_name, db)
            logger.info(f"Copilot Bot {payload.bot_id} 命中關鍵字：{rule.keyword}")
            return {"answer": rule.reply_message}

    # 2. 知識庫 AI
    try:
        result = await asyncio.to_thread(_query_copilot_knowledge, payload.bot_id, question)
    except Exception as e:
        logger.error(f"Copilot Bot {payload.bot_id} 知識庫查詢失敗：{e}", exc_info=True)
        result = None

    _record_stat(payload.bot_id, conv_id, conv_name, db)
    if result:
        reply, _, _ = result
        return {"answer": reply}

    return {"answer": "您好，人員將會協助確認，請稍後"}
