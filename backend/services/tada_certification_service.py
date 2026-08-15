"""
TADA 認證文件查詢的多輪追問機制（依據《TADA客服機器人_認證問題集_20260810.xlsx》規則設計）。

範圍說明：這裡只實作「偵測文件類型關鍵字 → 判斷缺市場/缺遊戲 → 用 ForceReply 追問 →
比對回覆 → 逾時換句話重問 → 二次逾時轉人工」這一整套多輪對話機制，並用文件裡「附錄：
文件類型關鍵字索引」的完整資料做為可測試的真實情境。

語言：追問/回覆的語言在第一次偵測到關鍵字的當下就依原始問句判斷一次（中文字元 vs. 純英文），
並存進 pending 狀態的 is_chinese 欄位，後續整段追問（包含逾時重問）都沿用同一個語言，
不會因為使用者回覆的內容（例如純市場英文名稱、純數字 GameID）而中途變成另一種語言。

資料來源：各市場的 Game List Google 試算表網址由使用者提供，實際分頁名稱/gid/欄位配置
已逐一開啟核對過，跟文件《附錄A》描述的欄位配置一致。Brazil 是唯一例外，資料不在
「Brazils Certification List」分頁（該分頁另有其他用途），而是使用者另外指出的分頁
（gid=1216924874），結構也跟其他市場不同：前幾列是不分遊戲的 RGS/RNG 平台認證，
其餘列才是逐遊戲的認證資料。

`build_final_reply()` 現在會直接讀取對應市場的 Game List 試算表查表（24 小時快取，
與 tada_gamelist_service.py 相同做法），找不到遊戲/該欄位沒有資料時，如實回覆查無資料
並轉人工，不會用猜的。
"""
import asyncio
import csv
import io
import json
import logging
import re
import time
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

PENDING_TTL_MINUTES = 30
_TABLE_CACHE_TTL_SECONDS = 24 * 3600

_ZH_RE = re.compile(r'[一-鿿㐀-䶿]')

# 文件類型關鍵字 → (對應市場清單, 文件性質)
# 文件性質："game"=需指定遊戲才能查、"platform"=平台層級不分遊戲、"vendor_escalate"=依廠商各自產生，不追問直接轉人工
_DOC_KEYWORD_RULES = (
    (("certificate file", "certification authority"),
     ["Greece", "Italy", "Malta", "Netherlands", "Portugal", "Romania", "South Africa", "Spain", "Sweden", "UK", "Brazil"],
     "game"),
    (("hgc approval letter",), ["Greece"], "game"),
    (("symbol mapping",), ["Portugal"], "game"),
    (("help files",), ["Romania", "South Africa", "Spain"], "game"),
    (("dgoj approval", "homologation report", "homologation"), ["Spain"], "game"),
    (("ukgc registration",), ["UK"], "game"),
    (("rgs certificate", "rng certificate"), ["Brazil"], "platform"),
    (("branded report",), ["Brazil", "Italy"], "vendor_escalate"),
)

# 5d：關鍵字命中後市場已固定，但實際核對過資料來源整份表格皆為空，直接轉人工、不追問
_NO_DATA_KEYWORDS = (
    "malta license", "gli 19", "colombia certificate", "ukgc certificate", "malta certificate",
)

_MARKET_ALIASES = {
    "Greece": ["greece", "希臘", "希腊"],
    "Italy": ["italy", "義大利", "意大利"],
    "Malta": ["malta", "馬爾他", "马耳他"],
    "Netherlands": ["netherlands", "荷蘭", "荷兰"],
    "Portugal": ["portugal", "葡萄牙"],
    "Romania": ["romania", "羅馬尼亞", "罗马尼亚"],
    "South Africa": ["south africa", "南非"],
    "Spain": ["spain", "西班牙"],
    "Sweden": ["sweden", "瑞典"],
    "UK": ["uk", "united kingdom", "英國", "英国"],
    "Brazil": ["brazil", "巴西"],
}

# 各市場 Game List 試算表：sheet_id/gid 已逐一開啟核對過分頁名稱與欄位配置。
# folder_link 對應文件《附錄A》的「備用資料夾連結」，沒有的市場填 None，
# 廠商要求「整個市場」資料時改給 gamelist_link（該市場整份 Game List 連結）。
_MARKET_DATA_SOURCES = {
    "Greece": {
        "sheet_id": "1GBX3rh9M6DCAoQkdNrF-eshvZUnkyXw4aMie4ocwwm0", "gid": "628814297",
        "folder_link": "https://drive.google.com/drive/folders/1AR44ecaIuhUKeNUT39wjO0vxWkD39OX0",
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1GBX3rh9M6DCAoQkdNrF-eshvZUnkyXw4aMie4ocwwm0/edit",
    },
    "Italy": {
        "sheet_id": "1ASA1I9XXWMRtzcaj9Kzp-OS8p6BCgszexKa94Upj8sQ", "gid": "131560561",
        "folder_link": None,
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1ASA1I9XXWMRtzcaj9Kzp-OS8p6BCgszexKa94Upj8sQ/edit",
    },
    "Malta": {
        "sheet_id": "1Sx5iinHhCej46Q1QzkN9RIIzFK9cnlCub-BhSpScw5A", "gid": "1839087692",
        "folder_link": None,
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1Sx5iinHhCej46Q1QzkN9RIIzFK9cnlCub-BhSpScw5A/edit",
    },
    "Netherlands": {
        "sheet_id": "1cQ-orv4yekG86BxkJ8bV3y_1I-E2ism68UEXMkEPYS8", "gid": "0",
        "folder_link": None,
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1cQ-orv4yekG86BxkJ8bV3y_1I-E2ism68UEXMkEPYS8/edit",
    },
    "Portugal": {
        "sheet_id": "1gYTzt-SdxYaQQPLmQqNHCsZxolBark1-r54GftuNluc", "gid": "1839087692",
        "folder_link": "https://drive.google.com/drive/folders/1zUiJhX5EURm59k5X_BW1kHWbvYFpuciH",
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1gYTzt-SdxYaQQPLmQqNHCsZxolBark1-r54GftuNluc/edit",
    },
    "Romania": {
        "sheet_id": "1-2WlyJ-jx-u8_7GYNQpkLMXHsJYiWTsJF0gju-A58hc", "gid": "1839087692",
        "folder_link": "https://drive.google.com/drive/folders/1gHo0-0JOtmMpcuLZqYQZQ3NZN2kTPbz5",
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1-2WlyJ-jx-u8_7GYNQpkLMXHsJYiWTsJF0gju-A58hc/edit",
    },
    "South Africa": {
        "sheet_id": "1jQXPhOMbXWtCUn7mSXhJvk3lGR69y6cZfBIZVixPVMc", "gid": "628814297",
        "folder_link": "https://drive.google.com/drive/folders/1WMWxYxVudXEI5YXlBFzP3t55BDebz6cq",
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1jQXPhOMbXWtCUn7mSXhJvk3lGR69y6cZfBIZVixPVMc/edit",
    },
    "Spain": {
        "sheet_id": "1Z9IAC2EMo3lWW83itWLxs57ujt1NjlWQkVZLkZ1kRUM", "gid": "1839087692",
        "folder_link": "https://drive.google.com/drive/folders/1AzowiyfAJ1GjSYwI6Fz1eUGsEy5Bi5ow",
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1Z9IAC2EMo3lWW83itWLxs57ujt1NjlWQkVZLkZ1kRUM/edit",
    },
    "Sweden": {
        "sheet_id": "1GNYw0L4bJVFjGs9qHHyOWUt4kk-s2nw2F9EU9ynKTBY", "gid": "677919004",
        "folder_link": None,
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1GNYw0L4bJVFjGs9qHHyOWUt4kk-s2nw2F9EU9ynKTBY/edit",
    },
    "UK": {
        "sheet_id": "1GndNGTYY1igep34458SMZ5_1Ox_65e99MHgr4Wq-kCs", "gid": "1839087692",
        "folder_link": None,
        "gamelist_link": "https://docs.google.com/spreadsheets/d/1GndNGTYY1igep34458SMZ5_1Ox_65e99MHgr4Wq-kCs/edit",
    },
}

_BRAZIL_SHEET_ID = "1XgsIpYWwAZTHfdX7cS-_SPoas876s4YIl4brMMD8ZrE"
_BRAZIL_GID = "1216924874"

# 命中的文件關鍵字 → 要在 Game List 分頁裡找哪一欄（比對 normalize 過的表頭子字串）
_KEYWORD_TO_COLUMN_HINT = {
    "certificate file": "certificate file",
    "certification authority": "certificate file",  # 通用詞：直接給 certificate file（+一併附上 authority）
    "hgc approval letter": "hgc approval letter",
    "symbol mapping": "symbol mapping",
    "help files": "help files",
    "dgoj approval": "dgoj",
    "homologation report": "dgoj",
    "homologation": "dgoj",
    "ukgc registration": "ukgc registration",
}

# 「要整個市場資料，不是單一遊戲」的措辭 → 命中時直接給市場層級連結，不追問遊戲（見文件 5a）
_WHOLE_MARKET_PHRASES = (
    "whole market", "entire market", "full list", "total list", "not just one game", "not just a single game",
    "整個市場", "整个市场", "全部遊戲", "全部游戏", "總表", "总表",
)

_market_table_cache = {}
_brazil_table_cache = {"fetched_at": 0.0}


def _normalize_header(h: str) -> str:
    return re.sub(r'\s+', ' ', h or "").strip().lower()


def _find_col(headers: list, substr: str):
    for i, h in enumerate(headers):
        if substr in h:
            return i
    return None


def _find_row(rows: list, id_col, name_col, identifier: str):
    """先用 GameID（純數字比對）找，找不到再用遊戲名稱（先完全相符，再退而找子字串）。"""
    ident = identifier.strip()
    digits = re.sub(r'\D', '', ident)
    if id_col is not None and digits:
        for row in rows:
            if id_col < len(row) and row[id_col].strip() == digits:
                return row
    if name_col is not None:
        lower_ident = ident.lower()
        for row in rows:
            if name_col < len(row) and row[name_col].strip().lower() == lower_ident:
                return row
        for row in rows:
            if name_col < len(row) and lower_ident and lower_ident in row[name_col].strip().lower():
                return row
    return None


def _fetch_market_table(market: str):
    """抓取並快取（24 小時）指定市場的 Game List 分頁，回傳 (normalize 過的表頭, 資料列)。"""
    now = time.time()
    cached = _market_table_cache.get(market)
    if cached and now - cached["fetched_at"] < _TABLE_CACHE_TTL_SECONDS:
        return cached["headers"], cached["rows"]
    cfg = _MARKET_DATA_SOURCES[market]
    url = f"https://docs.google.com/spreadsheets/d/{cfg['sheet_id']}/export?format=csv&gid={cfg['gid']}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    all_rows = list(csv.reader(io.StringIO(resp.text)))
    headers = [_normalize_header(h) for h in all_rows[0]]
    data_rows = all_rows[1:]
    _market_table_cache[market] = {"headers": headers, "rows": data_rows, "fetched_at": now}
    return headers, data_rows


def _fetch_brazil_table():
    """Brazil 結構特殊：header 列不是第一列，前面還有幾列不分遊戲的 RGS/RNG 平台認證。
    回傳 (表頭, 逐遊戲資料列, 平台層級列)。"""
    now = time.time()
    cached = _brazil_table_cache.get("headers")
    if cached and now - _brazil_table_cache["fetched_at"] < _TABLE_CACHE_TTL_SECONDS:
        return _brazil_table_cache["headers"], _brazil_table_cache["rows"], _brazil_table_cache["platform_rows"]
    url = f"https://docs.google.com/spreadsheets/d/{_BRAZIL_SHEET_ID}/export?format=csv&gid={_BRAZIL_GID}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    all_rows = list(csv.reader(io.StringIO(resp.text)))
    header_idx = None
    for i, row in enumerate(all_rows):
        if "game id" in [_normalize_header(c) for c in row]:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Brazil Game List 找不到表頭列（Game ID 欄位）")
    headers = [_normalize_header(c) for c in all_rows[header_idx]]
    platform_rows = all_rows[:header_idx]
    data_rows = all_rows[header_idx + 1:]
    _brazil_table_cache.update(
        headers=headers, rows=data_rows, platform_rows=platform_rows, fetched_at=now
    )
    return headers, data_rows, platform_rows


def _resolve_brazil(doc_keyword: str, game_identifier: str = None):
    headers, rows, platform_rows = _fetch_brazil_table()
    lab_col = _find_col(headers, "lab")
    cert_col = _find_col(headers, "certification")
    if doc_keyword in ("rgs certificate", "rng certificate"):
        want = "rgs" if "rgs" in doc_keyword else "rng"
        for row in platform_rows:
            if lab_col is not None and lab_col < len(row) and row[lab_col].strip().lower() == want:
                val = row[cert_col].strip() if cert_col is not None and cert_col < len(row) else ""
                if val:
                    return True, f"{doc_keyword.upper()}: {val}"
        return False, None
    if not game_identifier:
        return False, None
    id_col = _find_col(headers, "game id")
    name_col = _find_col(headers, "game name")
    row = _find_row(rows, id_col, name_col, game_identifier)
    if row is None:
        return False, None
    val = row[cert_col].strip() if cert_col is not None and cert_col < len(row) else ""
    if not val:
        return False, None
    parts = [f"Certificate: {val}"]
    if lab_col is not None and lab_col < len(row) and row[lab_col].strip():
        parts.append(f"Lab: {row[lab_col].strip()}")
    return True, "\n".join(parts)


def resolve_document(market: str, doc_keyword: str, game_identifier: str = None):
    """查表找出對應的認證文件資料。回傳 (found, text)：
    found=True 時 text 是要回覆的內容；found=False 時 text 一律是 None（查無資料，呼叫端自行決定轉人工文案）。"""
    try:
        if market == "Brazil":
            return _resolve_brazil(doc_keyword, game_identifier)
        if not game_identifier:
            return False, None
        headers, rows = _fetch_market_table(market)
        id_col = _find_col(headers, "gameid") or _find_col(headers, "game id")
        name_col = _find_col(headers, "name")
        cert_col = _find_col(headers, "certificate file")
        auth_col = _find_col(headers, "certification authority")
        hint = _KEYWORD_TO_COLUMN_HINT.get(doc_keyword, "certificate file")
        target_col = _find_col(headers, hint)
        row = _find_row(rows, id_col, name_col, game_identifier)
        if row is None or target_col is None:
            return False, None
        value = row[target_col].strip() if target_col < len(row) else ""
        if not value:
            return False, None
        parts = [f"{doc_keyword}: {value}"]
        if target_col == cert_col and auth_col is not None and auth_col < len(row) and row[auth_col].strip():
            parts.append(f"Certification Authority: {row[auth_col].strip()}")
        return True, "\n".join(parts)
    except Exception as e:
        logger.error(f"[TadaCert] 查表失敗 market={market} keyword={doc_keyword}: {e}")
        return False, None


def is_whole_market_request(text: str) -> bool:
    lower = text.lower()
    return any(p.lower() in lower for p in _WHOLE_MARKET_PHRASES)


def market_reference_link(market: str) -> str:
    cfg = _MARKET_DATA_SOURCES.get(market)
    if cfg:
        return cfg["folder_link"] or cfg["gamelist_link"]
    return ""


def whole_market_reply(market: str, is_chinese: bool) -> str:
    link = market_reference_link(market)
    if is_chinese:
        return f"請參考 {market} 認證文件總資料夾：\n{link}" if link else f"目前查詢不到 {market} 的相關資料，已為您轉接專人確認。"
    return f"Please refer to the {market} certification reference:\n{link}" if link else f"This certification data is currently unavailable for {market}, our team will assist you shortly."


def is_chinese_text(text: str) -> bool:
    """判斷訊息語言（含中文字元即視為中文），用來決定追問/回覆要用中文還是英文。"""
    return bool(_ZH_RE.search(text))


def detect_doc_query(text: str):
    """偵測訊息是否命中認證文件關鍵字。回傳 (doc_keyword, markets, doc_type) 或 None。
    doc_type 為 "no_data" 時 markets 固定回傳空清單（5d 情境不需要市場清單，直接轉人工）。"""
    lower = text.lower()
    for kw in _NO_DATA_KEYWORDS:
        if kw in lower:
            return (kw, [], "no_data")
    for keywords, markets, doc_type in _DOC_KEYWORD_RULES:
        for kw in keywords:
            if kw in lower:
                return (kw, markets, doc_type)
    return None


def detect_market_in_text(text: str) -> list:
    """從訊息裡找出有沒有明確提到市場名稱，回傳命中的市場清單。"""
    lower = text.lower()
    hits = []
    for market, aliases in _MARKET_ALIASES.items():
        if any(alias.lower() in lower for alias in aliases):
            hits.append(market)
    return hits


def resolve_market_reply(text: str, candidates: list):
    """用使用者對追問的回覆文字，比對候選市場清單，回傳唯一命中的市場名稱；
    找不到或同時命中多個候選市場則回傳 None（維持追問狀態，讓呼叫端再問一次）。"""
    hits = [m for m in detect_market_in_text(text) if m in candidates]
    if len(hits) == 1:
        return hits[0]
    return None


def extract_game_identifier(text: str) -> str:
    """從追問回覆裡取出遊戲識別（GameID 或名稱）。廠商常直接打遊戲名稱而非純數字，
    所以不強制要求格式，直接回傳去除頭尾空白的原文。"""
    return text.strip()


# ── 訊息文案（依 is_chinese 決定中/英文版本）────────────────────────────────

def game_question(is_chinese: bool) -> str:
    return "請問是哪一款遊戲（GameID或遊戲名稱）？" if is_chinese else "Which game is this regarding? (GameID or game name)"


def build_market_question(doc_keyword: str, candidates: list, is_chinese: bool) -> str:
    options = " / ".join(candidates)
    if is_chinese:
        return f"請問是哪個市場的 {doc_keyword}？（{options}）"
    return f"Which market's {doc_keyword} are you asking about? ({options})"


def market_mismatch_message(candidates: list, is_chinese: bool) -> str:
    options = " / ".join(candidates)
    if is_chinese:
        return f"沒有辨識到您指的市場，請從以下其中一個回覆：{options}"
    return f"We couldn't identify the market from your reply, please reply with one of: {options}"


def no_data_message(is_chinese: bool) -> str:
    return ("目前查詢不到相關認證資料，已為您轉接專人確認。" if is_chinese
            else "This certification data is currently unavailable, our team will assist you shortly.")


def vendor_escalate_message(is_chinese: bool) -> str:
    return ("這份文件依廠商各自產生，無法自動提供通用版本，已為您轉接專人確認。" if is_chinese
            else "This document is generated per vendor and has no generic version, our team will assist you shortly.")


def build_final_reply(market: str, doc_keyword: str, doc_type: str, is_chinese: bool, game_identifier: str = None) -> str:
    """market+doc_type（+game）都確定後：實際查表，找得到就回文件內容，找不到就誠實告知查無資料並轉人工。
    這裡會做網路請求（讀 Google Sheet CSV），呼叫端須用 asyncio.to_thread 包起來，不要在事件迴圈裡直接呼叫。"""
    found, content = resolve_document(market, doc_keyword, game_identifier)
    if found:
        return content
    return no_data_message(is_chinese)


def _timeout_reask_question(p) -> str:
    if p.missing == "market":
        candidates = json.loads(p.candidate_markets or "[]")
        options = " / ".join(candidates)
        if p.is_chinese:
            return f"請問您方才詢問的「{p.doc_keyword}」，是要查哪個市場的資料呢？（{options}）"
        return f"Regarding your earlier question about \"{p.doc_keyword}\", which market is this for? ({options})"
    if p.is_chinese:
        return f"請問您方才詢問的「{p.doc_keyword}」，是要查哪一款遊戲的資料呢？（GameID或遊戲名稱）"
    return f"Regarding your earlier question about \"{p.doc_keyword}\", which game is this for? (GameID or game name)"


# ── 追問待答狀態的資料庫存取 ──────────────────────────────────────────────

def get_pending(db, bot_id: int, chat_id: str, user_id: str):
    import models
    return db.query(models.TadaCertPending).filter(
        models.TadaCertPending.bot_id == bot_id,
        models.TadaCertPending.chat_id == chat_id,
        models.TadaCertPending.user_id == user_id,
    ).first()


def clear_pending(db, pending):
    db.delete(pending)
    db.commit()


def save_pending(db, bot_id: int, chat_id: str, user_id: str, prompt_message_id: int, missing: str,
                  doc_keyword: str, doc_type: str, is_chinese: bool, candidate_markets: list = None,
                  resolved_market: str = None, original_text: str = ""):
    """建立（或取代既有的）一筆待答狀態；每人同一時間只保留一筆，不做對話樹。"""
    import models
    existing = get_pending(db, bot_id, chat_id, user_id)
    if existing:
        db.delete(existing)
        db.flush()
    pending = models.TadaCertPending(
        bot_id=bot_id, chat_id=chat_id, user_id=user_id,
        prompt_message_id=prompt_message_id, missing=missing,
        doc_keyword=doc_keyword, doc_type=doc_type, is_chinese=is_chinese,
        candidate_markets=json.dumps(candidate_markets or []),
        resolved_market=resolved_market,
        original_text=original_text,
        expires_at=datetime.utcnow() + timedelta(minutes=PENDING_TTL_MINUTES),
    )
    db.add(pending)
    db.commit()
    return pending


# ── 逾時背景排程：每分鐘掃描一次，第一次逾時換句話重問，二次逾時轉人工並清除 ──────

async def cert_followup_timeout_loop():
    logger.info("[TadaCert] 追問逾時排程已啟動")
    while True:
        await asyncio.sleep(60)
        try:
            await _sweep_expired()
        except Exception as e:
            logger.error(f"[TadaCert] 逾時掃描例外: {e}")


async def _sweep_expired():
    import models
    from database import SessionLocal
    from services.telegram_service import bot_manager

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        expired = db.query(models.TadaCertPending).filter(
            models.TadaCertPending.expires_at <= now
        ).all()
        for p in expired:
            try:
                await _handle_expired(db, bot_manager, p)
            except Exception as e:
                logger.error(f"[TadaCert] 處理 pending id={p.id} 逾時失敗: {e}")
    finally:
        db.close()


async def _handle_expired(db, bot_manager, p):
    from telegram import ForceReply

    if not p.reasked:
        question = _timeout_reask_question(p)
        sent = await asyncio.to_thread(
            bot_manager.send_message, p.bot_id, p.chat_id, question,
            reply_markup=ForceReply(selective=True),
        )
        p.reasked = True
        if sent is not None:
            p.prompt_message_id = sent.message_id
        p.expires_at = datetime.utcnow() + timedelta(minutes=PENDING_TTL_MINUTES)
        db.commit()
        logger.info(f"[TadaCert] pending id={p.id} 逾時，已重新追問一次")
    else:
        fallback = ("您好，人員將會協助確認，請稍後" if p.is_chinese
                    else "Hello, our team will assist you shortly. Please wait.")
        await asyncio.to_thread(bot_manager.send_message, p.bot_id, p.chat_id, fallback)
        db.delete(p)
        db.commit()
        logger.info(f"[TadaCert] pending id={p.id} 二次逾時，已轉人工並清除待答狀態")
