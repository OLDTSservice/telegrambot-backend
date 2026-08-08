"""
TADA Gamelist 進階查詢服務（熱門排行 / 單一遊戲欄位查詢 / 複合條件篩選）
資料來源：TaDa Game List 2026 Google Sheet（GameRank 分頁 + Game List 分頁），
每日快取一次。AI 只負責從訊息裡判斷「使用者問的是哪個市場/遊戲/欄位/篩選條件」，
實際查表、比對交給程式碼做，避免 AI 對結構化資料自行猜測答案。

注意：GameRank 分頁的區塊解析（get_top_games）是依規格文件描述（各大區域標題列 +
下方 Rank/Type/GameID/Name 資料列）推測寫成，尚未對照過實際 CSV 內容驗證，
之後需用真實資料重新確認解析邏輯是否正確。
"""
import csv
import io
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)

_SHEET_ID = "1YfVQqjWga0txvHm2oU_CGuLJLtXY1qmI2q3kAR0uDeU"
_GAMERANK_GID = "922979064"
_GAMELIST_GID = "2124566733"
GAMERANK_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{_SHEET_ID}/edit?gid={_GAMERANK_GID}"
GAMELIST_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{_SHEET_ID}/edit?gid={_GAMELIST_GID}"

_CACHE_TTL_SECONDS = 24 * 3600
_gamerank_cache = {"data": None, "fetched_at": 0.0}
_gamelist_cache = {"data": None, "fetched_at": 0.0}

_KNOWN_REGIONS = [
    "all markets", "eu", "latam", "cis", "africa", "west asia",
    "global", "north america", "oceania", "crypto",
]
# 國家/幣別 → GameRank 大區域，目前只涵蓋規格文件裡提到的市場，
# 之後遇到新市場詢問、找不到對照時直接視為「不確定」，交由轉人工，不亂猜。
_REGION_KEYWORDS = {
    "west asia": ["turkey", "土耳其", "uae", "阿聯酋", "阿联酋", "saudi", "沙烏地", "沙特", "沙地", "kuwait", "科威特"],
}


def _csv_export_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{_SHEET_ID}/export?format=csv&gid={gid}"


def _fetch_csv_rows(url: str, label: str) -> list:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        reader = csv.reader(io.StringIO(resp.text))
        return [row for row in reader]
    except Exception as e:
        logger.error(f"[{label}] 下載 CSV 失敗：{e}")
        return []


def resolve_region(text: str) -> str:
    """從文字中判斷指的是 GameRank 哪個大區域，找不到回傳空字串"""
    lower = text.lower()
    for region in _KNOWN_REGIONS:
        if region in lower:
            return region
    for region, keywords in _REGION_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return region
    return ""


# ── GameRank（類型 1：熱門遊戲排行） ──────────────────────────────────────────

def get_cached_gamerank_rows() -> list:
    now = time.time()
    if _gamerank_cache["data"] is None or (now - _gamerank_cache["fetched_at"]) > _CACHE_TTL_SECONDS:
        rows = _fetch_csv_rows(_csv_export_url(_GAMERANK_GID), "TADA-GameRank")
        if rows:
            _gamerank_cache["data"] = rows
            _gamerank_cache["fetched_at"] = now
            logger.info(f"[TADA-GameRank] 已更新，共 {len(rows)} 列")
        elif _gamerank_cache["data"] is None:
            return []
    return _gamerank_cache["data"] or []


def get_top_games(region: str, top_n: int = 10) -> list:
    """解析 GameRank 表某個大區域的「Overall」排行。

    實際版面已對照真實資料確認：整份表格每一列內容之間都夾了一列空白列（Google
    Sheets 匯出時常見的列高排版留白），區域標題單獨一列後依序是「空白、Overall
    群組標題列、空白、Rank/Type/GameID/Name 表頭列、空白、資料列...」，資料列
    彼此之間也都夾著空白列。因此不能用固定的列數位移，改成先過濾掉區域區塊裡的
    空白列，取得「內容列」序列後，第 0 列＝區域標題、第 1 列＝群組標題、
    第 2 列＝表頭、第 3 列起才是實際資料列（欄位索引 1~4 為 Rank/Type/GameID/
    Name，「Overall」固定是每個區域的第一組）。已用文件範例驗證 All Markets
    （Top1=Fortune Garuda 500, ID 696）與 West Asia（同上）皆比對正確。
    """
    rows = get_cached_gamerank_rows()
    region_lower = region.strip().lower()
    start = None
    for i, row in enumerate(rows):
        non_empty = [c.strip() for c in row if c.strip()]
        if len(non_empty) == 1 and non_empty[0].strip().lower() == region_lower:
            start = i
            break
    if start is None:
        return []

    content_rows = []
    for row in rows[start:start + 200]:
        if any(c.strip() for c in row):
            content_rows.append(row)
        if len(content_rows) >= 3 + top_n:
            break

    games = []
    for row in content_rows[3:3 + top_n]:
        if len(row) < 5:
            continue
        rank, type_, game_id, name = (row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip())
        if not rank or not game_id:
            break
        games.append({"rank": rank, "type": type_, "game_id": game_id, "name": name})
    return games


# ── Game List（類型 4a/4b：欄位查詢／複合篩選） ────────────────────────────────

_GAMELIST_FIELD_ALIASES = {
    "game type": "Game Type", "type": "Game Type",
    "localization based": "Localization Based", "localization": "Localization Based",
    "release date": "Release Date",
    "gameid": "GameID", "game id": "GameID",
    "name": "Name",
    "tag": "Tag",
    "jackpot": "Jackpot",
    "gameplay": "GamePlay", "game play": "GamePlay",
    "game demo": "Game Demo", "demo": "Game Demo",
    "icon": "Game ICON/Thumbnails", "thumbnail": "Game ICON/Thumbnails", "thumbnails": "Game ICON/Thumbnails",
    "material": "Game Materials", "materials": "Game Materials",
    "volatility": "Volatility",
    "default rtp": "Default RTP", "rtp": "Default RTP",
    "94 rtp": "94 RTP",
    "hit rate": "Hit Rate",
    "min bet": "Defalut Min Bet", "minimum bet": "Defalut Min Bet", "default min bet": "Defalut Min Bet",
    "max bet": "Defalut Max Bet", "maximum bet": "Defalut Max Bet", "default max bet": "Defalut Max Bet",
    "theoretical max multiplier": "Theoretical Max Multiplier", "max multiplier": "Theoretical Max Multiplier",
    "max exposure": "Default Max Exposure", "default max exposure": "Default Max Exposure",
    "freegame rate": "FreeGame Rate", "free game rate": "FreeGame Rate",
    "buy bonus": "Buy bonus",
    "must hit by": "Must Hit By",
    "linking jackpot": "Linking Jackpot",
    "freespin api": "Freespin API support", "freespin": "Freespin API support", "freespin api support": "Freespin API support",
    "screen orientation": "Screen Orientation", "orientation": "Screen Orientation",
}

_BOOL_FIELDS = {"Buy bonus", "Freespin API support", "Linking Jackpot"}

# Game List 原始欄位標題有些是內部命名習慣（如拼字誤植的 "Defalut Min Bet"），
# 回覆給廠商前轉換成正常顯示用字，避免看起來不專業
_FIELD_DISPLAY_NAMES = {
    "Defalut Min Bet": "Min Bet",
    "Defalut Max Bet": "Max Bet",
    "Default RTP": "RTP",
    "Default Max Exposure": "Max Exposure",
}


def display_field_name(field: str) -> str:
    return _FIELD_DISPLAY_NAMES.get(field, field)


def get_cached_gamelist_rows() -> list:
    """回傳 Game List 分頁解析後的結構化資料（每列一個 dict，key 為欄位標題原文）"""
    now = time.time()
    if _gamelist_cache["data"] is None or (now - _gamelist_cache["fetched_at"]) > _CACHE_TTL_SECONDS:
        rows = _fetch_csv_rows(_csv_export_url(_GAMELIST_GID), "TADA-GameList")
        if rows:
            # 實際欄位標題有些跨行換行（例如 "Defalut\nMin Bet"）、有些帶尾端空白
            # （"FreeGame Rate "），需正規化成單行、去除多餘空白才能跟別名字典比對上。
            import re as _re_norm
            header = [_re_norm.sub(r'\s+', ' ', h).strip() for h in rows[0]]
            parsed = []
            for row in rows[1:]:
                if not any(c.strip() for c in row):
                    continue
                item = {header[i]: (row[i].strip() if i < len(row) else "") for i in range(len(header))}
                parsed.append(item)
            _gamelist_cache["data"] = parsed
            _gamelist_cache["fetched_at"] = now
            logger.info(f"[TADA-GameList] 已更新，共 {len(parsed)} 款遊戲")
        elif _gamelist_cache["data"] is None:
            return []
    return _gamelist_cache["data"] or []


def find_game(identifier: str):
    """依遊戲名稱或 GameID 精確比對（不區分大小寫），找到就回傳該列資料，否則回傳 None"""
    games = get_cached_gamelist_rows()
    identifier_lower = identifier.strip().lower()
    for g in games:
        if g.get("GameID", "").strip().lower() == identifier_lower:
            return g
        if g.get("Name", "").strip().lower() == identifier_lower:
            return g
    return None


def resolve_field_names(keywords: list) -> list:
    """把使用者提到的欄位關鍵字（例如 'min bet'）對應到 Game List 實際欄位名稱"""
    resolved = []
    for kw in keywords:
        col = _GAMELIST_FIELD_ALIASES.get(kw.strip().lower())
        if col and col not in resolved:
            resolved.append(col)
    return resolved


def _bool_field_matches(value: str, cond) -> bool:
    """cond 可能是 AI 回傳的原生 JSON boolean（True/False），也可能是字串
    （'yes'/'有'/'支援' 等），兩種都要能處理，避免 bool 沒有 .strip() 導致例外。"""
    v = value.strip().lower()
    has = v in ("y", "yes", "true", "1", "✓", "有")
    if isinstance(cond, bool):
        want = cond
    else:
        want = str(cond).strip().lower() not in ("n", "no", "false", "0", "無", "没有", "沒有", "不支援", "不支持")
    return has == want


def filter_games(conditions: dict) -> list:
    """conditions: {Game List 欄位名: 條件值}，回傳同時符合所有條件的遊戲清單"""
    games = get_cached_gamelist_rows()
    result = []
    for g in games:
        ok = True
        for field, cond in conditions.items():
            value = g.get(field, "")
            if field in _BOOL_FIELDS:
                matched = _bool_field_matches(value, cond)
            else:
                # 用「完全相符」而非子字串比對：Volatility 等欄位有 "High" 與 "Med High"
                # 這種不同類別但互為子字串的情況，子字串比對會誤把 "High" 配到 "Med High"。
                # cond 也可能不是字串（AI 偶爾回傳數字/布林），統一轉字串再比對避免例外。
                matched = value.strip().lower() == str(cond).strip().lower()
            if not matched:
                ok = False
                break
        if ok:
            result.append(g)
    return result


# ── 關鍵字快篩（避免每則訊息都呼叫 AI 判斷意圖，先用便宜的關鍵字比對過濾） ───────────

_TOPIC_KEYWORDS = (
    "top game", "top 10", "best performing", "performing game", "熱門遊戲", "热门游戏", "熱銷遊戲", "热销游戏",
    "遊戲排行", "游戏排行", "遊戲排名", "游戏排名", "gamerank",
    "type of game", "波動度", "波动度", "波動性", "波动性", "gameid", "游戏id", "遊戲id",
    "which games", "有哪些", "哪些遊戲", "哪些游戏",
    # 所有 Game List 欄位別名（見 _GAMELIST_FIELD_ALIASES）都當作觸發詞，避免像
    # "type of game"（跟別名庫裡的 "game type" 順序相反）這種講法漏掉關鍵字快篩；
    # 之後在別名字典新增同義詞會自動一併納入快篩，不用兩邊分別維護。
) + tuple(_GAMELIST_FIELD_ALIASES.keys())
_TOPIC_TOP_N_RE = re.compile(r'\btop\s*\d+\b', re.IGNORECASE)


def detect_gamelist_query_request(text: str) -> bool:
    """訊息是否可能與 Gamelist 排行/欄位查詢/篩選相關（便宜的關鍵字快篩，決定要不要呼叫 AI 判斷意圖）"""
    lower = text.lower()
    if any(kw in lower for kw in _TOPIC_KEYWORDS):
        return True
    return bool(_TOPIC_TOP_N_RE.search(text))


# ── AI 意圖判斷（只做語言理解，不做資料查詢） ───────────────────────────────────

_INTENT_SYSTEM_PROMPT = """你是 TADA Gamelist 查詢的意圖解析助手，只負責判斷使用者訊息屬於哪一種查詢意圖，
不負責查資料、不負責算答案。請只回覆一個 JSON 物件（不要加任何其他文字、不要用 markdown code block），格式如下三選一：

1. 熱門遊戲排行：{"intent": "top_games", "region_text": "使用者提到的國家/市場/幣別原文，若沒指定則為空字串", "count": 數字（未指定則為10）}
2. 單一遊戲欄位查詢：{"intent": "single_field", "game": "遊戲名稱或GameID原文", "fields": ["欄位關鍵字1", "欄位關鍵字2"]}
   可用欄位關鍵字（英文小寫）：game type, volatility, rtp, min bet, max bet, buy bonus, freespin api,
   linking jackpot, screen orientation, release date, hit rate, theoretical max multiplier,
   max exposure, freegame rate, jackpot, tag, gameplay, game demo, icon, material, must hit by
3. 複合條件篩選：{"intent": "filter", "conditions": {"欄位關鍵字": "條件值"}}（欄位關鍵字清單同上）。
   條件值一律用字串，不要用 JSON boolean（true/false）：有/支援類條件填 "yes"，無/不支援類條件填 "no"。
4. 都不符合，或問題不完整（例如只有遊戲名稱沒有欄位、只有欄位沒有遊戲名稱、篩選條件不足兩個）：
   {"intent": "insufficient"}
5. 完全與 Gamelist 查詢無關：{"intent": "none"}

規則：
- 單一遊戲查詢必須同時有「遊戲識別」與「欄位關鍵字」才算 single_field，缺一律 insufficient。
- 複合篩選必須明確要求列出清單/有哪些遊戲，且至少有一個篩選條件；只有一個條件也算 filter。
- 不要猜測、不要自行補充訊息中沒有的資訊。
"""


def parse_gamelist_intent(text: str) -> dict:
    """回傳意圖 dict 與 token 用量：(intent_dict, in_tok, out_tok)。
    失敗或無法解析時 intent_dict = {"intent": "none"}"""
    from services.ai_service import get_anthropic_client
    import json

    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"訊息：{text}\n\nJSON："}],
        )
        raw = message.content[0].text.strip()
        in_tok, out_tok = message.usage.input_tokens, message.usage.output_tokens
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        intent = json.loads(raw)
        if not isinstance(intent, dict) or "intent" not in intent:
            return {"intent": "none"}, in_tok, out_tok
        return intent, in_tok, out_tok
    except Exception as e:
        logger.error(f"[TADA-Gamelist] 意圖解析失敗：{e}", exc_info=True)
        return {"intent": "none"}, 0, 0
