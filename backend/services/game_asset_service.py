"""
JILI 遊戲素材查詢服務
串接同事提供的 JILI Game Search API：
- GET /gamelist：取得完整遊戲清單（每日快取一次）
- GET /search?q=xxx：用遊戲名稱或 GameID 查詢 Icon / Material 連結
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GAMELIST_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/gamelist"
SEARCH_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/search"

_GAME_ASSET_KEYWORDS = ["素材", "material", "asset", "icon", "圖示", "圖標", "入口圖"]

_game_list_cache = {"data": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 24 * 3600  # 對方每日 09:36 GMT+8 更新資料，快取 24 小時即可


def detect_game_asset_request(text: str) -> bool:
    """訊息是否含遊戲素材查詢相關關鍵字"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _GAME_ASSET_KEYWORDS)


def get_cached_game_list() -> list:
    """取得遊戲清單，24 小時內重複呼叫走記憶體快取。失敗時若有舊快取則沿用，否則回傳空清單。"""
    now = time.time()
    if _game_list_cache["data"] is None or (now - _game_list_cache["fetched_at"]) > _CACHE_TTL_SECONDS:
        try:
            resp = requests.get(GAMELIST_API, timeout=20)
            resp.raise_for_status()
            _game_list_cache["data"] = resp.json()
            _game_list_cache["fetched_at"] = now
            logger.info(f"[GameAsset] gamelist 已更新，共 {len(_game_list_cache['data'])} 筆")
        except Exception as e:
            logger.error(f"[GameAsset] 取得 gamelist 失敗：{e}")
            if _game_list_cache["data"] is None:
                return []
    return _game_list_cache["data"] or []


def match_game_name(text: str, game_list: list) -> tuple[Optional[str], int, int, int, int]:
    """用 Claude 對照遊戲清單，從訊息中擷取遊戲名稱。
    回傳 (遊戲名稱或 None, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)。"""
    from services.ai_service import get_anthropic_client

    if not game_list:
        return None, 0, 0, 0, 0

    compact_list = "\n".join(
        f"{g.get('game_id')}: {g.get('name')} / {g.get('name_zh') or ''} / {g.get('name_sc') or ''}"
        for g in game_list
    )
    system_prompt = (
        "你是一個遊戲名稱比對助手。以下是完整的遊戲清單（格式：GameID: 英文名稱 / 繁中名稱 / 簡中名稱）。\n"
        "請判斷使用者訊息中是否提到清單裡的某一款遊戲，若有，只回覆清單中該遊戲的英文名稱（name 欄位），"
        "必須完全比照清單裡的寫法，不可自行創造、翻譯或修改名稱。\n"
        "若訊息中沒有提到清單裡任何一款遊戲，請只回覆固定字串：NONE，不要加任何其他文字。"
    )
    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=[
                {"type": "text", "text": system_prompt},
                {
                    "type": "text",
                    "text": f"遊戲清單：\n{compact_list}",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": f"訊息：{text}\n\n遊戲名稱："}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )
        name = message.content[0].text.strip()
        cache_read = getattr(message.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(message.usage, "cache_creation_input_tokens", 0) or 0
        in_tok, out_tok = message.usage.input_tokens, message.usage.output_tokens
        if not name or name.upper() == "NONE":
            return None, in_tok, out_tok, cache_read, cache_write
        return name, in_tok, out_tok, cache_read, cache_write
    except Exception as e:
        logger.error(f"[GameAsset] 比對遊戲名稱失敗：{e}", exc_info=True)
        return None, 0, 0, 0, 0


def search_game(query: str) -> dict:
    """呼叫 search API，失敗時回傳 found=False"""
    try:
        resp = requests.get(SEARCH_API, params={"q": query}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[GameAsset] 搜尋遊戲失敗：{e}")
        return {"found": False, "query": query}
