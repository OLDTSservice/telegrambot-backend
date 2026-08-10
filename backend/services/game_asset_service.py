"""
遊戲素材查詢服務（JILI / TADA）
串接同事提供的 Game Search API：
- GET /gamelist、/tada-gamelist：取得完整遊戲清單（每日快取一次）
- GET /search、/tada-search：用遊戲名稱或 GameID 查詢 Icon / Material 連結
兩個廠商的 API 結構相同，只有網址與是否有中文名稱不同，共用底層邏輯。
"""
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

GAMELIST_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/gamelist"
SEARCH_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/search"
TADA_GAMELIST_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/tada-gamelist"
TADA_SEARCH_API = "https://jili-game-icon-material.netlify.app/.netlify/functions/tada-search"

_GAME_ASSET_KEYWORDS = ["素材", "material", "asset", "icon", "圖示", "圖標", "入口圖"]

_game_list_cache = {"data": None, "fetched_at": 0.0}
_tada_game_list_cache = {"data": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 24 * 3600  # 對方每日 09:36 GMT+8 更新資料，快取 24 小時即可

# 獨立成一個詞的純數字（前後不緊連其他數字），視為 Game ID 候選
_GAME_ID_TOKEN_RE = re.compile(r'(?<!\d)\d{1,6}(?!\d)')


def detect_game_asset_request(text: str) -> bool:
    """訊息是否含遊戲素材查詢相關關鍵字"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _GAME_ASSET_KEYWORDS)


def find_games_by_id(text: str, game_list: list) -> list[str]:
    """從訊息中擷取獨立的純數字 token，在本地遊戲清單中做『精確』GameID 比對（不經 AI 猜測，避免誤判成其他相似遊戲）。
    回傳比對到的 **Game ID 字串**清單（不是名稱！刻意保留數字，之後直接用 ID 查詢 search API 才是精確比對；
    若轉換成名稱再查詢，對方 API 的名稱模糊比對可能誤配到名稱相似的其他遊戲，例如 "Charge Buffalo" 被誤配到
    "3 Charge Buffalo"）。JILI/TADA 通用。"""
    if not game_list:
        return []
    valid_ids = {str(g.get("game_id")) for g in game_list if g.get("game_id") is not None}
    ids = []
    for tok in _GAME_ID_TOKEN_RE.findall(text):
        if tok in valid_ids and tok not in ids:
            ids.append(tok)
    return ids


def _fetch_cached_game_list(cache: dict, api_url: str, label: str) -> list:
    now = time.time()
    if cache["data"] is None or (now - cache["fetched_at"]) > _CACHE_TTL_SECONDS:
        try:
            resp = requests.get(api_url, timeout=20)
            resp.raise_for_status()
            cache["data"] = resp.json()
            cache["fetched_at"] = now
            logger.info(f"[{label}] gamelist 已更新，共 {len(cache['data'])} 筆")
        except Exception as e:
            logger.error(f"[{label}] 取得 gamelist 失敗：{e}")
            if cache["data"] is None:
                return []
    return cache["data"] or []


def get_cached_game_list() -> list:
    """取得 JILI 遊戲清單，24 小時內重複呼叫走記憶體快取。"""
    return _fetch_cached_game_list(_game_list_cache, GAMELIST_API, "GameAsset-JILI")


def get_cached_tada_game_list() -> list:
    """取得 TADA 遊戲清單，24 小時內重複呼叫走記憶體快取。"""
    return _fetch_cached_game_list(_tada_game_list_cache, TADA_GAMELIST_API, "GameAsset-TADA")


def _format_game_list(game_list: list) -> str:
    """組成給 AI 比對用的清單文字。有中文名稱（JILI）就附上，只有英文（TADA）就省略欄位，避免多餘的空斜線。"""
    lines = []
    for g in game_list:
        extras = [g.get("name_zh"), g.get("name_sc")]
        extras = [e for e in extras if e]
        if extras:
            lines.append(f"{g.get('game_id')}: {g.get('name')} / " + " / ".join(extras))
        else:
            lines.append(f"{g.get('game_id')}: {g.get('name')}")
    return "\n".join(lines)


def match_game_names(text: str, game_list: list) -> tuple[list[str], int, int, int, int]:
    """用 Claude 對照遊戲清單，從訊息中擷取『所有』被提到的遊戲名稱（一則訊息可能同時問多款遊戲）。
    JILI/TADA 通用，清單格式自動依是否有中文名稱調整。
    回傳 (遊戲名稱清單, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)。"""
    from services.ai_service import get_anthropic_client

    if not game_list:
        return [], 0, 0, 0, 0

    compact_list = _format_game_list(game_list)
    system_prompt = (
        "你是一個遊戲名稱比對助手。以下是完整的遊戲清單（每行格式：GameID: 名稱，若有多語系名稱會以 / 分隔）。\n"
        "請找出使用者訊息中『以文字表示』提到的所有遊戲（訊息可能同時問到不只一款），"
        "只回覆清單中對應遊戲的英文名稱，必須完全比照清單裡的寫法，不可自行創造、翻譯、修改或猜測名稱；"
        "如果不確定訊息指的是清單中哪一款遊戲，寧可不列出，不要憑感覺猜測相近的遊戲名稱。"
        "若有多款遊戲，請用半形逗號分隔列出，例如：Fortune Gems 500,Royal Fishing。\n"
        "若使用者訊息中的遊戲名稱文字『完全等於』（不分大小寫）清單中某一款遊戲的完整名稱，"
        "必須優先回傳那個完全相符的名稱；即使清單裡還有其他開頭相同、但後面多了字的相似名稱"
        "（例如同時有 Golden Tiger、Golden Tiger II、Golden Tiger Deluxe），"
        "只要使用者訊息裡沒有額外提到那些區分字樣（如 II、Deluxe），就不要一併回傳或誤回傳那些相似"
        "名稱——例如使用者說「please provide Golden Tiger material」，應只回覆「Golden Tiger」，"
        "不可回覆「Golden Tiger II」或「Golden Tiger Deluxe」（以上僅為示範規則的假設範例，"
        "不是真實清單內容，請勿把範例裡的名稱當成清單中真的存在的遊戲）。\n"
        "訊息中若有『獨立出現的純數字』（例如單獨的 109、540），一律忽略、不要處理，"
        "那些已經由其他邏輯以 Game ID 精確比對處理，不需要你猜測對應到哪個名稱，"
        "即使那個數字剛好等於某款遊戲的 GameID，也不要因此聯想或回傳該遊戲的名稱。\n"
        "若訊息中沒有以文字提到清單裡任何一款遊戲，請只回覆固定字串：NONE，不要加任何其他文字。"
    )
    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
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
        name_str = message.content[0].text.strip()
        cache_read = getattr(message.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(message.usage, "cache_creation_input_tokens", 0) or 0
        in_tok, out_tok = message.usage.input_tokens, message.usage.output_tokens
        if not name_str or name_str.upper() == "NONE":
            return [], in_tok, out_tok, cache_read, cache_write
        names = [n.strip() for n in name_str.split(",") if n.strip()]
        return names, in_tok, out_tok, cache_read, cache_write
    except Exception as e:
        logger.error(f"[GameAsset] 比對遊戲名稱失敗：{e}", exc_info=True)
        return [], 0, 0, 0, 0


def _search(query: str, api_url: str, label: str) -> dict:
    try:
        resp = requests.get(api_url, params={"q": query}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[{label}] 搜尋遊戲失敗：{e}")
        return {"found": False, "query": query}


def search_game(query: str) -> dict:
    """呼叫 JILI search API，失敗時回傳 found=False"""
    return _search(query, SEARCH_API, "GameAsset-JILI")


def search_tada_game(query: str) -> dict:
    """呼叫 TADA search API，失敗時回傳 found=False"""
    return _search(query, TADA_SEARCH_API, "GameAsset-TADA")
