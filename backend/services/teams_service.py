import json
import logging
import asyncio
from datetime import date

import httpx

logger = logging.getLogger(__name__)

# Microsoft Bot Framework token endpoint
_TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
# Microsoft Bot Framework OpenID config (for JWT validation)
_OPENID_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"

_jwks_cache: dict = {}  # 快取 JWKS 避免每次都請求


async def _get_access_token(app_id: str, app_password: str) -> str:
    """取得對外呼叫 Bot Service 的 Bearer Token"""
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(_TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": app_id,
            "client_secret": app_password,
            "scope": "https://api.botframework.com/.default",
        })
        res.raise_for_status()
        return res.json()["access_token"]


async def _send_reply(service_url: str, conversation_id: str, activity_id: str,
                      reply_text: str, app_id: str, app_password: str):
    """發送回覆到 Teams"""
    try:
        token = await _get_access_token(app_id, app_password)
        reply_url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(reply_url, json={
                "type": "message",
                "text": reply_text,
                "replyToId": activity_id,
            }, headers={"Authorization": f"Bearer {token}"})
            res.raise_for_status()
            logger.info(f"Teams 回覆成功，conversation={conversation_id}")
    except Exception as e:
        logger.error(f"Teams 回覆失敗：{e}", exc_info=True)


def _query_teams_knowledge(bot_id: int, question: str, db=None) -> tuple | None:
    from services.ai_service import query_teams_knowledge
    return query_teams_knowledge(bot_id, question)


def _record_teams_group_stat(bot_id: int, conversation_id: str, conv_name: str, db):
    import models as m
    from datetime import date
    today = date.today().isoformat()
    stat = db.query(m.TeamsGroupStat).filter(
        m.TeamsGroupStat.bot_id == bot_id,
        m.TeamsGroupStat.conversation_id == conversation_id,
        m.TeamsGroupStat.date == today,
    ).first()
    if stat:
        stat.reply_count += 1
        stat.conversation_name = conv_name
    else:
        stat = m.TeamsGroupStat(
            bot_id=bot_id, conversation_id=conversation_id,
            conversation_name=conv_name, date=today, reply_count=1,
        )
        db.add(stat)
    try:
        db.commit()
    except Exception as e:
        logger.error(f"記錄 Teams 群組統計失敗：{e}")
        db.rollback()


def _record_teams_usage(bot_id: int, input_tokens: int, output_tokens: int, db):
    import models as m
    today = date.today().isoformat()
    stat = db.query(m.TeamsUsageStat).filter(
        m.TeamsUsageStat.bot_id == bot_id,
        m.TeamsUsageStat.date == today
    ).first()
    if stat:
        stat.input_tokens += input_tokens
        stat.output_tokens += output_tokens
        stat.total_tokens += input_tokens + output_tokens
        stat.request_count += 1
    else:
        stat = m.TeamsUsageStat(
            bot_id=bot_id, date=today,
            input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens, request_count=1,
        )
        db.add(stat)
    db.commit()


async def process_teams_activity(bot, body: bytes, auth_header: str, db):
    """
    處理來自 Microsoft Bot Service 的 Activity Webhook。
    注意：生產環境建議加入 JWT 驗證（PyJWT + Microsoft JWKS）。
    """
    try:
        activity = json.loads(body)
    except Exception:
        logger.error("Teams Webhook：無法解析 JSON body")
        return

    activity_type = activity.get("type", "")
    if activity_type != "message":
        return

    text = (activity.get("text") or "").strip()
    if not text:
        return

    service_url = activity.get("serviceUrl", "")
    conversation_id = activity.get("conversation", {}).get("id", "")
    activity_id = activity.get("id", "")

    logger.info(f"Teams Bot {bot.id} 收到訊息：「{text[:60]}」")

    # 0. 忽略名單檢查
    sender = activity.get("from", {})
    sender_id = sender.get("aadObjectId", "") or sender.get("id", "")
    sender_email = (sender.get("email") or "").lower()
    sender_name = (sender.get("name") or "").lower()
    if sender_id or sender_email:
        import models as _m
        ignores = db.query(_m.TeamsIgnore).filter(
            _m.TeamsIgnore.bot_id == bot.id,
            _m.TeamsIgnore.is_enabled == True
        ).all()
        for ig in ignores:
            val = ig.identifier.lower()
            if val in (sender_id.lower(), sender_email, sender_name):
                logger.info(f"Teams Bot {bot.id} 忽略來自 {ig.identifier} 的訊息")
                return

    # 取得對話名稱
    conversation = activity.get("conversation", {})
    conv_name = conversation.get("name") or conversation.get("id", "")[:30] or "未知對話"

    # 1. 關鍵字規則
    import models as m
    rules = db.query(m.TeamsKeywordRule).filter(
        m.TeamsKeywordRule.bot_id == bot.id,
        m.TeamsKeywordRule.is_enabled == True
    ).all()

    for rule in rules:
        if rule.keyword.lower() in text.lower():
            await _send_reply(service_url, conversation_id, activity_id,
                              rule.reply_message, bot.app_id, bot.app_password)
            _record_teams_group_stat(bot.id, conversation_id, conv_name, db)
            return

    # 2. 知識庫 AI
    try:
        result = await asyncio.to_thread(_query_teams_knowledge, bot.id, text, db)
    except Exception as e:
        logger.error(f"Teams Bot {bot.id} 知識庫查詢失敗：{e}", exc_info=True)
        result = None

    if result:
        reply, in_tok, out_tok = result
        await _send_reply(service_url, conversation_id, activity_id,
                          reply, bot.app_id, bot.app_password)
        _record_teams_usage(bot.id, in_tok, out_tok, db)
        _record_teams_group_stat(bot.id, conversation_id, conv_name, db)
    else:
        await _send_reply(service_url, conversation_id, activity_id,
                          "您好，人員將會協助確認，請稍後",
                          bot.app_id, bot.app_password)
        _record_teams_group_stat(bot.id, conversation_id, conv_name, db)
