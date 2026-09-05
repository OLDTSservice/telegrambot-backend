"""
tjadmin 外部客服 API 串接（查輸贏回覆功能專用）。

依據平台人員提供的《tjadmin 外部客服 API 文件》：
- 1.2 節 HMAC-SHA256 簽章規則
- 3. API 1：玩家帳號查詢（GET /api/external/v1/player-account）

目前只用得到 API 1，查詢參數固定用 `name`（廠商在訊息裡提供的通常是玩家名/帳號代碼，
不會知道內部的純數字 aid，也不會給完整帳號），文件裡的 API 2（修改後台密碼）與 `account`／
`aid` 兩種查詢方式都不在這個功能的範圍內。
"""
import hashlib
import hmac
import logging
import re
import time
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_PLAYER_ACCOUNT_PATH = "/api/external/v1/player-account"


def _sign(method: str, path: str, raw_query: str, api_key: str):
    """依文件 1.2 節規則計算 (hash, timeslot)：
    timeslot = floor(unix秒/300)；message = method\\npath\\nrawQuery\\ntimeslot；
    hash = lowercase_hex(HMAC-SHA256(key=完整64字元金鑰, message))。"""
    timeslot = str(int(time.time() // 300))
    message = f"{method}\n{path}\n{raw_query}\n{timeslot}"
    hash_hex = hmac.new(api_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hash_hex, timeslot


def query_player_by_name(base_url: str, key_id: str, api_key: str, name: str, timeout: int = 30):
    """呼叫 API 1（玩家帳號查詢），查詢參數固定用 name（前綴模糊比對）。
    回傳 (rows, error)：成功時 error 為 None，rows 是回應的 rows 陣列（可能是空清單，代表查無此人）；
    請求失敗（例外、非 200、或伺服器回傳的 error 訊息）時 rows 為 None，error 是簡短錯誤說明。"""
    raw_query = f"name={quote(name, safe='')}"
    hash_hex, _ = _sign("GET", _PLAYER_ACCOUNT_PATH, raw_query, api_key)
    url = f"{base_url.rstrip('/')}{_PLAYER_ACCOUNT_PATH}?{raw_query}"
    try:
        resp = requests.get(
            url, headers={"X-Key-Id": key_id, "X-Hash": hash_hex}, timeout=timeout
        )
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        data = resp.json()
        return data.get("rows", []), None
    except Exception as e:
        logger.error(f"[tjadmin] 查詢玩家帳號失敗 name={name}: {e}")
        return None, str(e)


# ── 觸發判斷與帳號擷取（純文字規則，不用 AI，比較穩定可預期）────────────────────

# 這批關鍵字取自廠商實際回報的多種「查輸贏/查是否正常」問法（中英文混雜），
# 只要訊息命中任一個，就會嘗試往下擷取玩家帳號、呼叫 API 查詢；擷取不到帳號時
# 直接轉人工（不會因為誤觸發而查錯資料，頂多是白白略過這次自動判斷機會）。
_NETWIN_TRIGGER_WORDS = (
    "abnormal", "fraud", "fraudulent", "normal or not", "log normal", "win normal",
    "normal kah", "winning is valid", "winnings are valid", "winning valid",
    "正常嗎", "正常吗", "是否正常", "下注是否正常", "投注是否正常",
)


def detect_netwin_query_request(text: str) -> bool:
    """訊息是否可能是在問「這個玩家/這筆下注/這筆贏分正不正常」，決定要不要往下擷取帳號、查API。"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _NETWIN_TRIGGER_WORDS)


# 具體欄位標籤（依優先順序）：Player ID / Member username / Player
_LABELED_PATTERNS = (
    re.compile(r'player\s*id\s*[:：]\s*([A-Za-z0-9_]+)', re.IGNORECASE),
    re.compile(r'member\s*username\s*[:：]\s*([A-Za-z0-9_]+)', re.IGNORECASE),
    re.compile(r'\bplayer\s*[:：]\s*([A-Za-z0-9_]+)', re.IGNORECASE),
)
# 泛用「ID：」標籤（比對到單獨的 ID 欄位，例如「ID : QOGABAE011O2」），但要排除掉
# Kiosk ID／理帳號這種代理帳號欄位——那不是玩家帳號。
_GENERIC_ID_RE = re.compile(r'(?<!kiosk )(?<!agent )\bid\s*[:：]\s*([A-Za-z0-9_]+)', re.IGNORECASE)
# 整行就是一個獨立代碼：6-20 碼英數字（含底線少見但保留彈性），且訊息本身沒有明確欄位標籤時的保底規則。
_BARE_LINE_RE = re.compile(r'^[A-Za-z0-9]{6,20}$')

_KIOSK_LINE_MARKERS = ("kiosk", "理账号", "理帳號")


def extract_account(text: str):
    """從訊息裡擷取玩家帳號候選字串（給 API 的 name 參數用）。
    依序嘗試：1. 具體欄位標籤（Player ID / Member username / Player）
             2. 泛用 ID 標籤（排除 Kiosk/理帳號那一行）
             3. 整行只有一個 6-20 碼英數字代碼、且不是純數字（純數字通常是注單編號/Ticket，不是帳號）
    找不到時回傳 None，呼叫端應視為「偵測到查詢意圖但擷取不到帳號」，直接轉人工。"""
    for pat in _LABELED_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    for line in text.splitlines():
        low = line.lower()
        if any(marker in low or marker in line for marker in _KIOSK_LINE_MARKERS):
            continue
        m = _GENERIC_ID_RE.search(line)
        if m:
            return m.group(1)
    for line in text.splitlines():
        candidate = line.strip().strip(",.;:")
        if _BARE_LINE_RE.match(candidate) and not candidate.isdigit():
            return candidate
    return None
