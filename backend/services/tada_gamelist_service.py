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

def _word_in(phrase: str, lower_text: str) -> bool:
    """判斷 phrase（英文用詞界比對，避免像 "uk" 是 "ukrainian" 子字串這種誤配；
    中文沒有詞界概念，維持子字串比對）是否出現在 lower_text 中。"""
    if phrase.isascii():
        return bool(re.search(r'\b' + re.escape(phrase) + r'\b', lower_text))
    return phrase in lower_text


_KNOWN_REGIONS = [
    "all markets", "eu", "latam", "cis", "africa", "west asia",
    "global", "north america", "oceania", "crypto",
]
# 國家/幣別 → GameRank 大區域。只填入地理/政治分類明確、不會有爭議的國家；
# 遇到新市場詢問、找不到對照時直接視為「不確定」，交由轉人工，不亂猜。
_REGION_KEYWORDS = {
    "west asia": ["turkey", "土耳其", "uae", "阿聯酋", "阿联酋", "saudi", "沙烏地", "沙特", "沙地", "kuwait", "科威特"],
    "latam": [
        "brazil", "巴西", "mexico", "墨西哥", "argentina", "阿根廷", "colombia", "哥倫比亞", "哥伦比亚",
        "peru", "秘魯", "秘鲁", "chile", "智利", "paraguay", "巴拉圭",
    ],
    "eu": [
        "belgium", "比利時", "比利时", "greece", "希臘", "希腊", "italy", "義大利", "意大利",
        "malta", "馬爾他", "马耳他", "netherlands", "荷蘭", "荷兰", "portugal", "葡萄牙",
        "romania", "羅馬尼亞", "罗马尼亚", "spain", "西班牙", "sweden", "瑞典",
    ],
    "africa": ["south africa", "南非", "kenya", "肯亞", "肯亚", "nigeria", "奈及利亞", "尼日利亚"],
    "cis": ["belarus", "白俄羅斯", "白俄罗斯", "ukraine", "烏克蘭", "乌克兰", "russia", "俄羅斯", "俄罗斯", "kazakhstan", "哈薩克", "哈萨克"],
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
        if _word_in(region, lower):
            return region
    for region, keywords in _REGION_KEYWORDS.items():
        if any(_word_in(kw, lower) for kw in keywords):
            return region
    return ""


def _parse_region_groups() -> dict:
    """掃描整份 GameRank 資料，取得各區域裡所有分組（Overall + 各幣別獨立排行）的欄位起始位置。
    實際版面是每個區域橫向並排多組「Rank/Type/GameID/Name」表格（Overall 一組、之後每個幣別各
    一組），分組標題（例如「EU / Romanian Leu」）就寫在區域標題下一列，各組固定間隔 5 欄
    （4 欄資料 + 1 欄空白）。回傳 {區域小寫: {分組名稱小寫: 起始欄位索引}}。"""
    rows = get_cached_gamerank_rows()
    result = {}
    i = 0
    while i < len(rows):
        row = rows[i]
        non_empty = [c.strip() for c in row if c.strip()]
        if len(non_empty) == 1 and non_empty[0].strip().lower() in _KNOWN_REGIONS:
            region_lower = non_empty[0].strip().lower()
            j = i + 1
            while j < len(rows) and not any(c.strip() for c in rows[j]):
                j += 1
            if j < len(rows):
                region_prefix = f"{region_lower} / "
                groups = {}
                for col_idx, cell in enumerate(rows[j]):
                    label = cell.strip().lower()
                    if label.startswith(region_prefix):
                        groups[label[len(region_prefix):].strip()] = col_idx
                result[region_lower] = groups
            i = j
        else:
            i += 1
    return result


# 國家名稱 → 幣別分組名稱：訊息通常會講「國家」（如 "Romania"），但 GameRank 的
# 幣別分組標題寫的是「幣別」（如 "Romanian Leu"），兩者字面上對不起來，子字串比對
# 抓不到，需要額外的國家→幣別對照表才能把 "Romania" 正確對應到 "romanian leu" 分組。
# 只收錄「一國對一幣別」明確不會有爭議的國家；多國共用同一貨幣（如歐元區、CFA法郎區）
# 不列入，避免誤把詢問「某國」誤導成看似該區域另一個國家的獨立排行。
_COUNTRY_TO_SUBGROUP = {
    "uk": "british pound sterling", "united kingdom": "british pound sterling", "britain": "british pound sterling",
    "england": "british pound sterling",
    "poland": "polish zloty",
    "romania": "romanian leu",
    "hungary": "hungarian forint",
    "switzerland": "swiss franc",
    "norway": "norwegian krone",
    "czech republic": "czech koruna", "czechia": "czech koruna", "czech": "czech koruna",
    "denmark": "danish krone",
    "sweden": "swedish krona",
    "serbia": "serbian dinar",
    "macedonia": "macedonian denar", "north macedonia": "macedonian denar",
    "brazil": "brazilian real",
    "mexico": "mexican peso",
    "venezuela": "venezuelan bolivar",
    "colombia": "colombian peso",
    "chile": "chilean peso",
    "peru": "peruvian sol",
    "argentina": "argentine peso",
    "bolivia": "bolivian boliviano",
    "paraguay": "paraguayan guarani",
    "costa rica": "costa rican colon",
    "guatemala": "guatemalan quetzal",
    "uruguay": "uruguayan peso",
    "russia": "russian ruble",
    "uzbekistan": "uzbekistani som",
    "ukraine": "ukrainian hryvnia",
    "kazakhstan": "kazakhstani tenge",
    "belarus": "belarusian ruble",
    "azerbaijan": "azerbaijani manat",
    "armenia": "armenian dram",
    "moldova": "moldovan leu",
    "nigeria": "nigerian naira",
    "south africa": "south african rand",
    "egypt": "egyptian pound",
    "tanzania": "tanzanian shilling",
    "zambia": "zambian kwacha",
    "uganda": "ugandan shilling",
    "kenya": "kenyan shilling",
    "ethiopia": "ethiopian birr",
    "ghana": "ghanaian cedi",
    "malawi": "malawian kwacha",
    "angola": "angolan kwanza",
    "lesotho": "lesotho loti",
    "namibia": "namibian dollar",
    "mozambique": "mozambican metical",
    "tunisia": "tunisian dinar",
    "sierra leone": "sierra leonean leone",
    "liberia": "liberian dollar",
    "gambia": "gambian dalasi",
    "turkey": "turkish lira",
    "uae": "uae dirham", "united arab emirates": "uae dirham",
    "saudi arabia": "saudi riyal", "saudi": "saudi riyal",
    "kyrgyzstan": "kyrgyz som",
    "kuwait": "kuwaiti dinar",
    "iraq": "iraqi dinar",
    "georgia": "georgian lari",
    "iran": "iranian rial",
    "canada": "canadian dollar",
    "honduras": "honduran lempira",
    "cuba": "cuban peso",
    "nicaragua": "nicaraguan cordoba",
    "australia": "australian dollar",
    "new zealand": "new zealand dollar",
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "litecoin": "litecoin", "ltc": "litecoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "dogecoin": "dogecoin",
    "tether": "us dollar tether", "usdt": "us dollar tether",
    # 上面用的是「國名」當 key，但很多國家的形容詞/demonym 講法（例如 "Hungarian
    # top games"）字面上不是國名的子字串（"hungary" 不是 "hungarian" 的子字串），
    # 會漏掉；下面補上這類「國名對不上、需要另外列 demonym」的情況（demonym 本身
    # 是國名子字串的則不用重複列，例如 "brazil" 已經是 "brazilian" 的子字串）。
    "british": "british pound sterling",
    "hungarian": "hungarian forint",
    "swiss": "swiss franc",
    "norwegian": "norwegian krone",
    "danish": "danish krone",
    "swedish": "swedish krona",
    "mexican": "mexican peso",
    "argentine": "argentine peso", "argentinian": "argentine peso",
    "ukrainian": "ukrainian hryvnia",
    "mozambican": "mozambican metical",
    "turkish": "turkish lira",
    "emirati": "uae dirham", "emirates": "uae dirham",
    "honduran": "honduran lempira",
    # 詞界比對下，"romania" 這種國名不再算是 "romanian" 的子字串命中（因為
    # \b 要求比對結尾剛好在單字邊界，"romania" 後面接的 "n" 還是字母，不算邊界），
    # 之前「demonym 剛好是國名子字串」的假設在詞界比對下不成立，這裡把所有
    # demonym 講法都明確補上，不再依賴子字串巧合。
    "romanian": "romanian leu",
    "serbian": "serbian dinar",
    "macedonian": "macedonian denar",
    "brazilian": "brazilian real",
    "venezuelan": "venezuelan bolivar",
    "colombian": "colombian peso",
    "chilean": "chilean peso",
    "peruvian": "peruvian sol",
    "bolivian": "bolivian boliviano",
    "paraguayan": "paraguayan guarani",
    "costa rican": "costa rican colon",
    "guatemalan": "guatemalan quetzal",
    "uruguayan": "uruguayan peso",
    "russian": "russian ruble",
    "uzbekistani": "uzbekistani som",
    "kazakhstani": "kazakhstani tenge",
    "belarusian": "belarusian ruble",
    "azerbaijani": "azerbaijani manat",
    "armenian": "armenian dram",
    "moldovan": "moldovan leu",
    "nigerian": "nigerian naira",
    "south african": "south african rand",
    "egyptian": "egyptian pound",
    "tanzanian": "tanzanian shilling",
    "zambian": "zambian kwacha",
    "ugandan": "ugandan shilling",
    "kenyan": "kenyan shilling",
    "ethiopian": "ethiopian birr",
    "ghanaian": "ghanaian cedi",
    "malawian": "malawian kwacha",
    "angolan": "angolan kwanza",
    "namibian": "namibian dollar",
    "tunisian": "tunisian dinar",
    "sierra leonean": "sierra leonean leone",
    "liberian": "liberian dollar",
    "gambian": "gambian dalasi",
    "kuwaiti": "kuwaiti dinar",
    "iraqi": "iraqi dinar",
    "georgian": "georgian lari",
    "iranian": "iranian rial",
    "canadian": "canadian dollar",
    "cuban": "cuban peso",
    "nicaraguan": "nicaraguan cordoba",
    "australian": "australian dollar",
}


def resolve_region_and_subgroup(text: str) -> tuple:
    """從文字中判斷指的是哪個大區域，以及是否有指定具體幣別的獨立排行分組。
    回傳 (區域小寫, 分組名稱小寫)：
    - 文字提到具體幣別（例如 "Romanian Leu"）且該區域確實有該幣別的獨立分組 → (區域, 幣別)
    - 文字提到國家名稱（例如 "Romania"）且能對應到明確的幣別分組 → (區域, 幣別)
    - 只提到區域名稱（如 "EU"），沒有指定到具體幣別/國家 → (區域, "")，呼叫端應使用 Overall
    - 完全無法辨識地區 → ("", "")
    幣別分組是直接掃描實際 GameRank 資料動態比對（而非寫死清單），之後幣別分組異動不需要改程式碼；
    國家→幣別對照表才是寫死清單，因為 GameRank 表格本身只有幣別名稱、沒有國家名稱可供動態掃描。
    """
    lower = text.lower()
    groups_by_region = _parse_region_groups()
    for region, groups in groups_by_region.items():
        for subgroup in groups:
            if subgroup == "overall":
                continue
            if _word_in(subgroup, lower):
                return region, subgroup
    for country, subgroup in _COUNTRY_TO_SUBGROUP.items():
        if _word_in(country, lower):
            for region, groups in groups_by_region.items():
                if subgroup in groups:
                    return region, subgroup
    return resolve_region(text), ""


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


def get_top_games(region: str, top_n: int = 10, subgroup: str = "") -> list:
    """解析 GameRank 表某個大區域的排行。

    實際版面已對照真實資料與使用者截圖確認：每個區域是橫向並排多組「Rank/Type/
    GameID/Name」表格（Overall 一組＋各幣別各一組獨立排行，例如「EU / Romanian
    Leu」），並非只有單一 Overall 排行；各組標題寫在區域標題下一列（分組標題列），
    固定間隔 5 欄（4 欄資料＋1 欄空白分隔）。表格每一列內容之間都夾了一列空白列
    （Google Sheets 匯出常見的列高排版留白），先過濾掉區域區塊裡的空白列取得「內容
    列」序列，第 0 列＝區域標題、第 1 列＝分組標題列、第 2 列＝欄位表頭列、第 3 列
    起才是實際資料列。

    subgroup 為空時使用「Overall」（整個區域合併排行）；subgroup 非空時（例如
    "romanian leu"）改用該幣別的獨立排行——找不到對應分組時回傳空清單，不會偷偷
    退回 Overall，避免把幣別問題誤答成整個地區的合併數據。
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
    for row in rows[start:start + 300]:
        if any(c.strip() for c in row):
            content_rows.append(row)
        if len(content_rows) >= 3 + top_n:
            break
    if len(content_rows) < 3:
        return []

    group_header_row = content_rows[1]
    region_prefix = f"{region_lower} / "
    group_cols = {}
    for col_idx, cell in enumerate(group_header_row):
        label = cell.strip().lower()
        if label.startswith(region_prefix):
            group_cols[label[len(region_prefix):].strip()] = col_idx

    wanted_group = subgroup.strip().lower() or "overall"
    start_col = group_cols.get(wanted_group)
    if start_col is None:
        return []

    games = []
    for row in content_rows[3:3 + top_n]:
        if len(row) < start_col + 4:
            continue
        rank, type_, game_id, name = (
            row[start_col].strip(), row[start_col + 1].strip(),
            row[start_col + 2].strip(), row[start_col + 3].strip(),
        )
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
    "fs api": "Freespin API support",
    "screen orientation": "Screen Orientation", "orientation": "Screen Orientation",
}

_BOOL_FIELDS = {"Buy bonus", "Freespin API support", "Linking Jackpot"}
# 這些欄位不是 Y/N 布林值，而是「有填內容代表支援、空白代表不支援」（例如 94 RTP 欄位有填
# 百分比數字如 "94.00%" 代表支援 94% RTP 選項，空白代表不支援），意圖解析仍會依規則把
# 「哪些遊戲支援94 RTP」問成 yes/no 條件，但欄位本身內容不是 Y/N 字樣，不能套用 _BOOL_FIELDS
# 的判斷方式，也不能直接拿字串完全比對（否則永遠比對不到，會誤答「查無符合條件」）。
_PRESENCE_FIELDS = {"94 RTP"}

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


def _want_flag(cond) -> bool:
    """把 AI 回傳的條件值（原生 JSON boolean，或 'yes'/'有'/'支援' 等字串）統一轉成 True/False。"""
    if isinstance(cond, bool):
        return cond
    return str(cond).strip().lower() not in ("n", "no", "false", "0", "無", "没有", "沒有", "不支援", "不支持")


def _bool_field_matches(value: str, cond) -> bool:
    """cond 可能是 AI 回傳的原生 JSON boolean（True/False），也可能是字串
    （'yes'/'有'/'支援' 等），兩種都要能處理，避免 bool 沒有 .strip() 導致例外。"""
    v = value.strip().lower()
    has = v in ("y", "yes", "true", "1", "✓", "有")
    return has == _want_flag(cond)


def _presence_field_matches(value: str, cond) -> bool:
    """cond 語意同 _bool_field_matches（有/無），但欄位本身不是 Y/N 字樣，而是「有填內容代表
    支援、空白代表不支援」（例如 94 RTP 欄位是百分比數字或空白）。"""
    has = bool(value.strip())
    return has == _want_flag(cond)


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
            elif field in _PRESENCE_FIELDS:
                matched = _presence_field_matches(value, cond)
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
   可用欄位關鍵字（英文小寫）：game type, volatility, rtp, 94 rtp, min bet, max bet, buy bonus, freespin api,
   fs api, linking jackpot, screen orientation, release date, hit rate, theoretical max multiplier,
   max exposure, freegame rate, jackpot, tag, gameplay, game demo, icon, material, must hit by
   注意：rtp 與 94 rtp 是兩個不同欄位。rtp 是一般的 Default RTP 數值；94 rtp 是「該遊戲是否
   額外支援 94% RTP 版本選項」的是/否類欄位。使用者問「支援94 RTP的遊戲」「which games
   provide 94 RTP」這類問法時，欄位關鍵字要用 94 rtp，不要把 94 當成 rtp 欄位的條件值。
   fs api 是 freespin api 的縮寫講法，兩者是同一個欄位，使用者問「FS API」時直接用 fs api
   即可（或視為與 freespin api 相同欄位處理）。
3. 複合條件篩選：{"intent": "filter", "conditions": {"欄位關鍵字": "條件值"}}（欄位關鍵字清單同上）。
   條件值一律用字串，不要用 JSON boolean（true/false）：有/支援類條件填 "yes"，無/不支援類條件填 "no"
   （94 rtp 這類是/否欄位務必如此；只有 rtp 這種真正的數值欄位才會需要填實際數字當條件值）。
4. 都不符合，或問題不完整（例如只有遊戲名稱沒有欄位、只有欄位沒有遊戲名稱、篩選條件不足兩個）：
   {"intent": "insufficient", "fields": ["有辨識到的欄位關鍵字，沒有就是空陣列"]}
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
