import asyncio
import ipaddress
import json
import re
import threading
import logging
import time
import requests
from typing import Dict
from telegram import ForceReply, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

# ── 每人冷卻記錄（bot_id + user_id → 上次「無匹配」回應的時間戳）──────────
_no_match_ts: Dict[str, float] = {}
_COOLDOWN_SECS = 10       # 無匹配冷卻秒數
_MIN_TEXT_LEN  = 10       # 無匹配時最短回應字元數

# 收回指令（回覆機器人自己的訊息 + 打出以下任一詞，且發送者在管理員名單內才會生效）
_UNDO_COMMANDS = {"收回", "撤回", "undo", "recall"}

_SUPPORT_TICKET_MARKERS = (
    "please provide the list below",
    "可以提供以下资料以便查询",
    "可以提供以下資料以便查詢",
)

# 客服工單常見的「遊戲」欄位標籤（如「游戏名称/Game：JILI」）
_TICKET_GAME_FIELD_RE = re.compile(r'(游戏名称|游戏|game)\s*[/／]?\s*\w*\s*[：:]', re.IGNORECASE)
# 客服工單常見的「帳號」欄位標籤（如「代理账号/Username：xxx」）
_TICKET_ACCOUNT_FIELD_RE = re.compile(
    r'(代理账号|代理帳號|账号|帳號|username|kiosk\s*id|player\s*id)\s*[/／]?\s*\w*\s*[：:]',
    re.IGNORECASE,
)
# 白名單請求一定會附上要加白的 IP，用來把白名單請求排除在「遊戲+帳號欄位＝工單」規則之外
_TICKET_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

# 不含數字編號的「標籤：值」欄位行（規則四用），例如 "Brand Name: PP80"、"Callback URL : "
# 開頭用負向前瞻排除單獨一行的網址（如 "https://xxx.com/admin"）：網址本身帶協定冒號
# （"https:"）會被誤判成「標籤：值」格式（標籤=https），實際上只是單純貼出連結、不是
# 欄位標籤，需排除才不會把「網址+USER+PW+IP」這種訊息誤判成 4 行結構化表單。
# 若標籤本身包含網址（如 "Website URL: https://xxx"），標籤不是從 http 開頭，不受影響。
_FORM_FIELD_LINE_RE = re.compile(r'^\s*(?!https?://)[^\s：:].{0,38}?[：:]\s*.*$', re.IGNORECASE)
# 出現這些字樣即視為白名單相關訊息，排除規則四，避免誤擋真正的白名單請求
_WHITELIST_SAFETY_WORDS = ("白名单", "白名單", "whitelist", "加白")

# 一定不會有知識庫答案的主題（例如詢問處理進度、要求重置密碼），
# 出現關鍵字即跳過知識庫查詢，直接 fallback 轉人工
_NO_KB_TOPIC_KEYWORDS = (
    "任何更新", "any update",
    # 詢問處理進度/處理結果：屬於個案即時狀態，知識庫是靜態文件不會有答案
    "处理结果", "處理結果", "处理进度", "處理進度", "進度", "进度",
    "重置密碼", "密碼重置", "重置密码", "密码重置",
    "reset password", "reset pw", "reset pass",
    "can't login", "cant login", "can not login", "cannot login", "can login",
    "still same", "still the same", "still cannot",
    "any abnormal betting", "suspicious bet", "any abnormalities",
    "help add",
    "無法登入", "无法登入", "還是一樣", "还是一样", "异常投注", "異常投注",
    # 引用附加圖片，AI 無法比對圖片內容
    "图中", "圖中", "截图", "截圖",
    # 活動/優惠/收費/條款：屬於即時異動內容，知識庫是靜態文件，不會反映當下狀態
    "活动", "活動", "event", "events", "t&c",
    # 維護：是否維護中/維護時間屬於即時狀態，知識庫是靜態文件，不會反映當下狀態
    "維護", "维护", "maintenance",
    # 遊戲是否下架屬於即時狀態，知識庫是靜態文件，不會反映當下狀態
    "下架",
    "please try", "do you mean", "do you means", "存在差异",
    # 引用附加圖片（圖一/圖1 等編號稱呼），AI 無法比對圖片內容
    "图一", "圖一", "图1", "圖1",
    # 賠付率/中獎頻率等玩家個案質疑，屬於即時運算結果，知識庫是靜態文件不會有答案
    "winning frequency", "win frequency", "payout rate", "payout valid", "lower down", "so high", "rate continues",
    "調整", "调整", "already used", "how can use",
    "要這個", "要这个", "是這個", "是这个", "還有這個", "还有这个", "check不到", "什麼情況", "什么情况",
    "cannot access", "can't access",
    # 需人工核實特定會員/玩家/用戶身分的個案，知識庫不會有答案
    "协助确认会员", "協助確認會員", "协助确认玩家", "協助確認玩家", "协助确认用户", "協助確認用戶",
    "玩家重新",
    # 其他機器人的自我介紹訊息，非廠商實際提問
    "this is one of our support robots", "dapat buka",
    "any abnormal bet", "member feedback",
    # 新遊戲上線時間/新帳號/白名單申請等，屬於個案即時狀態，知識庫不會有答案
    "上线新游戏", "上線新遊戲", "新遊戲上線", "normal bet", "has been enabled", "log normal",
    "新账号", "新帳號", "please whitelist", "please help whitelist",
    "这个呢", "這個呢", "bet id :", "如何查詢", "怎么算",
    "game log", "tak dapat login",
    # 個案帳號狀態/白名單協助/系統操作異常，屬於即時個案，知識庫不會有答案
    "顺便帮我", "順便幫我", "没有记录", "沒有記錄", "一直卡",
    "目前这款", "目前這款", "已停用",
    "whitelist bo", "帮忙加白", "幫忙加白", "进去查", "進去查",
    "assist to disable", "wrong wallet", "total bet是多少", "please add",
    "改代理", "有新消息", "有消息",
    "投注是否正常", "对下情况", "對下情況", "玩了多少", "assist to check",
    "记录有问题", "記錄有問題",
    "connection error", "for your assistance", "this whitelisted ip", "get big wins", "ratio",
    "创建总代理", "創建總代理", "建立一个", "建立一個", "之前对接", "之前對接",
    "下面创建", "下面創建", "帮忙创建", "幫忙創建", "帮忙建立", "幫忙建立",
)


def _is_no_kb_topic(text: str) -> bool:
    """訊息內容屬於一定查不到知識庫答案的主題（進度詢問、密碼重置等），命中關鍵字即可（不需整句相符）"""
    lower = text.lower()
    return any(kw.lower() in lower for kw in _NO_KB_TOPIC_KEYWORDS)


# 玩家問題回報／投訴（例如「95A8656 玩家提出的问题」「玩家 95A8656 发过来的视频请检查」）
# 玩家帳號格式不固定（純英文、純數字、混合、可能含底線皆有可能），無法用格式判斷，
# 改用「提及玩家」+「需人工檢查/處理類字樣」兩組關鍵字同時出現來判斷，這類訊息本質是
# 要人工核實特定玩家的個案，知識庫不會有答案。
_PLAYER_REF_WORDS = ("玩家", "player", "顾客", "客户", "customer")
_PLAYER_CHECK_WORDS = (
    "提出", "反映", "反饋", "反馈", "請檢查", "请检查", "麻煩檢查", "麻烦检查",
    "幫忙看一下", "帮忙看一下", "視頻", "视频", "投訴", "投诉", "舉報", "举报",
    "正常嗎", "正常吗", "够力", "吐分", "賠付", "赔付", "機率", "几率",
    "reported", "complain", "complaint", "please check", "kindly check", "video", "report",
    "没有那个", "什么都没有",
)


def _is_player_report(text: str) -> bool:
    """訊息同時提及玩家與需人工檢查/處理的字樣（玩家個案問題/投訴），跳過知識庫直接轉人工。

    英文關鍵字（如 report、video）改用「獨立單字」詞界比對，不用子字串比對：
    後台帳號常見「TitanTR43_Report」這種以底線接尾綴的命名習慣（類似 _MYR 這種寫法），
    純子字串比對會誤把帳號名稱裡的 "Report" 當成「回報投訴」關鍵字，導致一般業務流程
    問題（例如問重送時間間隔）被誤判成玩家個案投訴而跳過知識庫。中文關鍵字沒有詞界
    概念，維持子字串比對。"""
    lower = text.lower()
    has_player_ref = any(
        re.search(r'\b' + re.escape(w.lower()) + r'\b', lower) if w.isascii() else w in text
        for w in _PLAYER_REF_WORDS
    )
    has_check_word = any(
        re.search(r'\b' + re.escape(w.lower()) + r'\b', lower) if w.isascii() else w in text
        for w in _PLAYER_CHECK_WORDS
    )
    return has_player_ref and has_check_word


# RTP／返獎率異常投訴（例如「近一个月该游戏返奖率有点高」）：RTP數值本身是靜態資料，
# 但「異常波動」是玩家/代理對即時狀況的質疑，屬於需人工查核的個案，知識庫不會有答案。
# 用「RTP相關詞」+「異常波動詞」同時出現才判定，不用單一關鍵字命中就攔截——避免誤擋
# 「RTP是多少」「返奖率怎麼查」這種只有RTP相關詞、沒有異常波動詞的正常知識性問題
# （這類問題需要能正常查知識庫，見先前 icon/material/rtp 改走知識庫的修正）。
_RTP_REF_WORDS = (
    "返奖率", "返獎率", "派彩率", "中奖率", "中獎率", "赢率", "贏率", "回报率", "回報率", "賠率", "赔率",
    "殺率", "杀率", "玩家贏", "玩家赢", "用戶贏", "用户赢", "代理輸", "代理输", "波動率", "波动率",
    "商戶輸", "商户输", "杀数", "殺數",
    "rtp", "payout rate", "payout", "winning rate", "win rate", "return rate",
)
_RTP_ANOMALY_WORDS = (
    "偏高", "偏低", "太高", "太低", "很高", "有點高", "有点高", "有點低", "有点低", "變高", "变高", "變低", "变低",
    "異常", "异常", "不對", "不对", "有問題", "有问题", "一直", "持續", "持续", "下降", "變差", "变差",
    "波動", "波动", "正常",
    "so high", "too high", "too low", "lower down", "rate continues", "keeps dropping", "dropping", "fluctuating",
    "normal",
)


def _is_rtp_anomaly_complaint(text: str) -> bool:
    """訊息同時提及 RTP/返獎率相關詞與異常波動詞（例如「返奖率有点高」「RTP一直很低」），
    是玩家/代理對即時波動的質疑投訴，跳過知識庫直接轉人工。只有 RTP 相關詞、沒有異常波動詞
    （例如單純問「RTP是多少」）不受影響，仍正常走知識庫查詢。"""
    lower = text.lower()
    has_rtp_ref = any(w.lower() in lower for w in _RTP_REF_WORDS)
    has_anomaly = any(w.lower() in lower for w in _RTP_ANOMALY_WORDS)
    return has_rtp_ref and has_anomaly


def _is_bare_ip_message(text: str) -> bool:
    """訊息整段內容就是單一個 IP 位址（IPv4 或 IPv6），沒有其他文字說明——
    常見於白名單流程中單獨貼出位址、沒有搭配問題描述的情況，本質不是一個提問，
    知識庫不會有答案，跳過知識庫直接 fallback。用標準庫 ipaddress 判斷，
    比自寫 regex 更能正確涵蓋各種 IPv6 縮寫格式，避免誤判或漏判。"""
    try:
        ipaddress.ip_address(text.strip())
        return True
    except ValueError:
        return False


_BARE_CODE_RE = re.compile(r'^[A-Za-z0-9]{8,}$')


def _is_bare_code_message(text: str) -> bool:
    """訊息整段內容就是單一個英數混合的代碼/單號（例如「27063759W1X8」「ACNM27063759W1X8」），
    沒有其他文字說明——常見於廠商單獨貼出訂單號/交易編號、沒有搭配問題描述的情況，
    本質不是一個提問，知識庫不會有答案，跳過知識庫直接 fallback。
    要求同時包含英文字母與數字（純英文單字或純數字不算，避免誤判成一般英文詞彙或
    純數字訊息），且長度至少 8 碼（短訊息已由既有的 10 字元門檻略過，這裡的門檻
    只是額外保險，避免誤判太短的英數縮寫）。"""
    stripped = text.strip()
    if not _BARE_CODE_RE.match(stripped):
        return False
    has_letter = any(c.isalpha() for c in stripped)
    has_digit = any(c.isdigit() for c in stripped)
    return has_letter and has_digit


# 涵蓋常見的日期/時間格式：日期部分分隔符可為 -／/／.，年月日順序不拘；
# 時間部分可有可無、可含秒數與毫秒；結尾可有 Z 或時區偏移（如 +08:00）。
_BARE_TIMESTAMP_RE = re.compile(
    r'^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}([ T]\d{1,2}:\d{2}(:\d{2})?(\.\d{1,6})?)?'
    r'|\d{1,2}:\d{2}(:\d{2})?(\.\d{1,6})?)'
    r'\s*(Z|UTC|GMT|[+-]\d{2}:?\d{2})?$'
)


def _is_bare_timestamp_message(text: str) -> bool:
    """訊息整段內容就是單一個時間戳記（例如「2026-08-12 12:14:52」「2026/08/12」「12:14:52」），
    沒有其他文字說明——常見於廠商單獨貼出時間點、沒有搭配問題描述的情況，本質不是一個提問，
    知識庫不會有答案，跳過知識庫直接 fallback。用正則涵蓋常見日期/時間格式的組合，只有訊息
    整段（去除頭尾空白後）完全符合格式才判定，避免誤擋「2026-08-12發生異常」這種還有其他
    文字說明的訊息。"""
    return bool(_BARE_TIMESTAMP_RE.match(text.strip()))


# 這幾個帳號通常是內部客服／機器人自己的帳號，訊息「整段只是tag這些帳號」時不是提問，
# 知識庫不會有答案；但廠商也可能在正常問題訊息裡「順帶」tag這些帳號（例如「@OLDTS_service
# 請問這個問題...」），這種訊息還有實際內容，應該正常走知識庫——所以不能用單一關鍵字命中
# 就攔截，只有整段訊息「只有」這些tag、沒有其他文字時才判定。
_BARE_MENTION_HANDLES = {"@oldts_service", "@jiliserivceprodbot"}


def _is_bare_mention_message(text: str) -> bool:
    """訊息整段內容只是單獨tag一個或多個指定帳號（例如「@OLDTS_service」），沒有其他文字，
    本質不是一個提問，跳過知識庫直接 fallback。"""
    tokens = text.strip().split()
    if not tokens:
        return False
    return all(tok.lower() in _BARE_MENTION_HANDLES for tok in tokens)


def _is_application_form(text: str) -> bool:
    """
    偵測結構化申請表單/客服工單，符合任一即視為表單：
    1. 多行含「數字編號 + 冒號欄位」格式，例：1. 商戶名字：xxx / 2. Domain URL：xxx
       條件：至少 3 行符合「編號. 內容：值」或「編號.內容：值」格式
    2. 固定的客服工單範本開頭（如「Please provide the list below」/「可以提供以下资料以便查询」），
       這類範本欄位（游戏/Game、代理账号/Kiosk ID、玩家账号/Player ID、问题）不一定有數字編號，
       但開頭語句是系統固定產生的文字，比對到即可高信心判定為表單。
    3. 同時含「遊戲」欄位標籤（游戏名称/Game：）與「帳號」欄位標籤（代理账号/Username：等）、
       且訊息中「沒有」IP 位址：這是另一種客服工單常見格式，欄位可能只有 2 行、沒有固定開頭語句，
       後面接的是自由文字的具體請求（例如重設密碼），應交由人員處理，不應讓 AI 自行回答（例如編造
       重設密碼流程）。
       白名單請求也常同時出現「游戏/Game：」「代理账号/Username：」欄位（例如「游戏名称/Game：JILI
       代理账号/Username：xxx 加白后台IP：1.2.3.4」），但一定會附上要加白的 IP，因此额外要求訊息中
       沒有 IP 位址才視為工單，避免把真正的白名單請求誤判成表單而跳過白名單處理。
    4. 多行「標籤：值」格式但沒有數字編號（例如 API 串接申請單常見的 Brand Name / Website URL /
       Callback URL / Prod API IP Address 等欄位）：至少 4 行才視為表單，且訊息中不能含白名單相關
       字樣，避免誤擋真正的白名單請求（白名單請求欄位通常也是「標籤：值」格式，但行數較少，
       且一定會出現白名單關鍵字，用關鍵字排除即可安全區分）。
    """
    lower = text.lower()
    if any(marker in lower for marker in _SUPPORT_TICKET_MARKERS):
        return True
    if (
        _TICKET_GAME_FIELD_RE.search(text)
        and _TICKET_ACCOUNT_FIELD_RE.search(text)
        and not _TICKET_IP_RE.search(text)
    ):
        return True
    lines = text.splitlines()
    # 符合「數字. 任意內容 ：或: 任意內容」的行
    field_line = re.compile(r'^\s*\d+[\.\、]\s*.+[：:].+')
    matched = sum(1 for line in lines if field_line.match(line))
    if matched >= 3:
        return True
    if not any(w in lower for w in _WHITELIST_SAFETY_WORDS):
        matched_lenient = sum(1 for line in lines if _FORM_FIELD_LINE_RE.match(line))
        if matched_lenient >= 4:
            return True
    return False


# 純問候／感謝／道別語（不含實際問題內容）；正規化後需與整句「完全相符」才算命中，
# 避免「Hi Team, would like to ask...」這類「開頭是問候語但後面有實際問題」的訊息被誤擋
_GREETING_PHRASES = {
    # 英文問候/感謝/道別
    "hi", "hello", "hey", "yo", "hiya",
    "hi team", "hello team", "hey team", "hi all", "hello all", "hi guys", "hello guys",
    "ok", "okay", "ok thanks", "okay thanks", "got it", "noted", "understood", "roger", "received",
    "thanks", "thank you", "thank", "thanks team", "thank you team", "thank team", "thx", "ty",
    "cheers", "appreciate it", "no problem", "np", "you're welcome", "youre welcome", "welcome",
    "bye", "goodbye", "see you", "good morning", "good afternoon", "good evening", "good night",
    "great thanks", "perfect thanks", "many thanks", "thanks a lot", "thank you so much", "thank you very much",
    "noted thanks", "noted with thanks", "understood thanks", "noted thank you",
    # 英文取消/忽略前訊息（不含實際問題內容）
    "ignore", "please ignore", "kindly ignore", "ignore this", "ignore that",
    "ignore above", "ignore the above", "please disregard", "disregard", "disregard that",
    "never mind", "nevermind", "nvm", "cancel that", "cancel this",
    "hold on", "hold up", "wait", "one moment", "one sec", "give me a sec", "give me a moment",
    "let me check", "checking", "please hold", "please wait",
    "ignore thanks", "please ignore thanks", "kindly ignore thanks", "kindy ignore thanks",
    "ignore this thanks", "please disregard thanks", "never mind thanks",
    "sorry please ignore", "sorry team please ignore", "sorry ignore this", "oops please ignore",
    "sorry for the mistake", "double confirm",
    "pls ignore", "pls ignore thanks", "sorry for the mistake pls ignore thanks",
    "sorry for the mistake please ignore", "sorry for the mistake please ignore thanks",
    "may ignore", "may ignore this", "may ignore team", "may ignore thanks", "may ignore team thanks",
    # 中文問候/感謝/道別
    "好的", "收到", "明白了", "明白", "了解", "知道了", "辛苦了",
    "請忽略", "請忽略上面", "請忽略以上", "忽略上面", "忽略以上", "不用理會", "當我沒說", "取消",
    "謝謝", "谢谢", "多謝", "多谢", "感謝", "感谢", "謝謝晒", "谢谢晒", "唔該", "唔该",
    "你好", "您好", "嗨", "哈囉", "哈罗", "早安", "午安", "晚安", "再見", "再见", "拜拜",
}
# 常見道別/感謝短語常會加上 "team" 尾綴稱呼群組（如 "ok thanks team"），
# 與其窮舉所有排列組合，改為自動衍生 "{短語} team" 版本一併納入完全比對清單。
_GREETING_TEAM_SUFFIXABLE = {
    "ok", "okay", "ok thanks", "okay thanks", "thanks", "thank you",
    "got it", "noted", "understood", "roger", "received", "cheers",
    "great thanks", "perfect thanks", "many thanks", "thanks a lot",
    "bye", "goodbye", "good morning", "good afternoon", "good evening", "good night",
    "ignore", "please ignore", "kindly ignore", "disregard", "please disregard", "never mind",
    "hold on", "hold up", "wait", "one moment", "one sec",
}
_GREETING_PHRASES |= {f"{p} team" for p in _GREETING_TEAM_SUFFIXABLE}
_GREETING_NORMALIZE_RE = None


def _is_greeting_or_thanks(text: str) -> bool:
    """純問候/感謝/道別語（去除標點與大小寫後，整句需與清單完全相符才算命中）"""
    global _GREETING_NORMALIZE_RE
    import re
    if _GREETING_NORMALIZE_RE is None:
        _GREETING_NORMALIZE_RE = re.compile(r'[!！.。,，~～、?？\s]+')
    normalized = _GREETING_NORMALIZE_RE.sub(' ', text.strip().lower()).strip()
    return normalized in _GREETING_PHRASES


def _contains_ignore_keyword(text: str) -> bool:
    """訊息中只要出現「ignore」這個字（不限完整一句、不分大小寫、不需整句相符），就視為要忽略、
    不需處理，直接略過（不回覆、不記錄）。跟純問候/感謝語一樣是完全靜默的處理方式——這類訊息
    幾乎都是「請忽略我剛才那則」的意思，即使還夾雜其他文字，通常也不是真正需要回答的問題。"""
    return "ignore" in text.lower()


async def _try_game_asset_reply(bot_id: int, text: str, db, get_list_fn, search_fn, label: str):
    """遊戲素材查詢共用邏輯（JILI/TADA 皆呼叫此函式，僅資料來源不同）。
    偵測到關鍵字才會查詢；一則訊息可能同時問多款遊戲，逐一查詢後整合成一則回覆；
    查不到的靜默略過。回傳組好的回覆文字，若完全比對不到任何遊戲則回傳 None（呼叫端應改走知識庫查詢）。"""
    from services.game_asset_service import (
        detect_game_asset_request, find_games_by_id, find_games_by_exact_name, match_game_names,
    )
    if not detect_game_asset_request(text):
        return None

    game_list = await asyncio.to_thread(get_list_fn)
    # 獨立出現的純數字先用本地清單精確比對 Game ID（不經 AI，避免猜成相似的其他遊戲）。
    id_queries = find_games_by_id(text, game_list)
    # 訊息文字裡若直接完整出現某款遊戲的全名，用確定性的文字比對找出來，優先於 AI 語意比對——
    # 開頭相同、後面多字的相似名稱（Devil Fire / Devil Fire Twins / Devil Fire Bonu$ Coin）
    # 光靠 AI 判斷，不同措辭下仍會不穩定誤選成其他變體，純文字比對才能穩定解決。找不到完全相符
    # 的名稱才呼叫 AI，處理改述、縮寫等純文字比對抓不到的情況。
    matched_names = find_games_by_exact_name(text, game_list)
    if not matched_names:
        matched_names, ga_in_tok, ga_out_tok, ga_cache_read, ga_cache_write = (
            await asyncio.to_thread(match_game_names, text, game_list)
        )
        if ga_in_tok or ga_cache_read:
            from services.ai_service import record_usage
            record_usage(bot_id, ga_in_tok, ga_out_tok, db,
                        cache_read_tokens=ga_cache_read, cache_write_tokens=ga_cache_write)
    # 若某個文字比對到的遊戲名稱，剛好就是「已經用 Game ID 精確比對到」的同一款遊戲，
    # 不要再額外用名稱查一次，避免同一則訊息（例如「請提供 GameID 193 的素材」）答出兩款遊戲。
    id_query_names = {
        str(g.get("game_id")): (g.get("name") or "").strip().lower()
        for g in game_list
    }
    resolved_names = {id_query_names.get(q, "") for q in id_queries}
    matched_names = [n for n in matched_names if n.strip().lower() not in resolved_names]
    # 若某個獨立數字剛好是「文字比對到的遊戲名稱」結尾的數字（例如遊戲本身就叫
    # "Coin of Lightning 2"），代表這個數字其實是名稱的一部分，而非另一款遊戲的獨立 ID，
    # 避免同一句話被誤判成同時查詢兩款不同的遊戲。
    id_queries = [
        q for q in id_queries
        if not any(name.split()[-1] == q for name in matched_names)
    ]
    # 文字比對到的遊戲名稱，優先在本地清單換成 Game ID 再查（精確比對），不要直接把名稱字串
    # 丟給外部 search API 做模糊比對——外部 API 是同事提供的第三方服務，它自己的名稱模糊比對
    # 不可靠，即使 AI 已經完全正確地從清單裡複製出正確名稱，search API 仍可能配到名稱相似的
    # 其他遊戲（實測發生過 "Devil Fire" 被配到 "Devil Fire Bonu$ Coin"、"Charge Buffalo" 被
    # 配到 "3 Charge Buffalo"）。本地清單找不到完全相符名稱時（理論上少見，AI已被要求需完全
    # 比照清單寫法），才退回用名稱字串查 search API 當保底。
    name_to_id = {
        (g.get("name") or "").strip().lower(): str(g.get("game_id"))
        for g in game_list
    }
    leftover_names = []
    for n in matched_names:
        gid = name_to_id.get(n.strip().lower())
        if gid:
            if gid not in id_queries:
                id_queries.append(gid)
        else:
            leftover_names.append(n)
    all_queries = id_queries + leftover_names

    found_blocks = []
    seen_game_ids = set()
    no_asset_found = False  # 遊戲存在，但 Icon 和 Material 皆查無連結
    for query in all_queries:
        game_result = await asyncio.to_thread(search_fn, query)
        if game_result.get("found") and game_result.get("game_id") not in seen_game_ids:
            seen_game_ids.add(game_result.get("game_id"))
            # icon_url/material_url 為陣列（同一款遊戲可能有多個 Drive 資料夾），無資料夾時是 null
            icon_urls = game_result.get("icon_url") or []
            material_urls = game_result.get("material_url") or []
            if not icon_urls and not material_urls:
                # 兩者皆無：不確定是真的沒有素材還是資料來源缺漏，不由 AI/程式直接斷定「無」，
                # 交由人員確認（多款遊戲同時詢問時，這款先略過不列出，其他有素材的照常列出）。
                no_asset_found = True
                continue
            icon_text = "\n".join(icon_urls) if icon_urls else "（無）"
            material_text = "\n".join(material_urls) if material_urls else "（無）"
            found_blocks.append(
                f"🎮 {game_result['name']} (ID: {game_result['game_id']})\n"
                f"🖼 Icon：\n{icon_text}\n"
                f"📦 Material：\n{material_text}"
            )
    if found_blocks:
        logger.info(f"Bot {bot_id} {label}遊戲素材查詢成功：{len(found_blocks)}/{len(all_queries)} 款")
        return "\n\n".join(found_blocks)
    if no_asset_found:
        logger.info(f"Bot {bot_id} {label}遊戲素材查詢：遊戲存在但無素材連結，回覆固定訊息轉人工")
        return (
            "您好，人員將會協助確認，請稍後"
            if re.search(r'[一-鿿㐀-䶿]', text)
            else "Hello, our team will assist you shortly. Please wait."
        )
    logger.info(f"Bot {bot_id} {label}遊戲素材查詢未比對到任何遊戲，改走知識庫查詢")
    return None


_FALLBACK_TRANSFER_MSG_ZH = "您好，人員將會協助確認，請稍後"
_FALLBACK_TRANSFER_MSG_EN = "Hello, our team will assist you shortly. Please wait."


async def _try_tada_gamelist_reply(bot_id: int, text: str, db):
    """TADA Gamelist 進階查詢（熱門排行/單一遊戲欄位查詢/複合條件篩選）共用邏輯。
    回傳 (handled, reply)：
    - (False, None)：訊息與 Gamelist 查詢無關，呼叫端應改走知識庫查詢
    - (True, None)：確定是 Gamelist 查詢但條件不充分（規格要求不猜、不追問），
      呼叫端應跳過知識庫直接 fallback 轉人工
    - (True, "回覆文字")：查詢成功，直接回覆
    """
    from services.tada_gamelist_service import (
        detect_gamelist_query_request, parse_gamelist_intent, resolve_region_and_subgroup,
        get_top_games, find_game, resolve_field_names, filter_games,
    )
    if not detect_gamelist_query_request(text):
        return False, None

    intent, in_tok, out_tok = await asyncio.to_thread(parse_gamelist_intent, text)
    if in_tok:
        from services.ai_service import record_usage
        record_usage(bot_id, in_tok, out_tok, db)

    kind = intent.get("intent")
    is_zh = bool(re.search(r'[一-鿿㐀-䶿]', text))

    if kind == "none":
        return False, None

    if kind == "insufficient":
        if len(text.strip()) < _MIN_TEXT_LEN:
            # 訊息太短（例如「RTP 是多少？」），跟其他功能一樣視為雜訊直接忽略，
            # 不主動觸發轉人工回覆／記 log，交由既有的短訊息略過規則統一處理。
            logger.info(f"Bot {bot_id} TADA Gamelist 查詢：問題不完整且訊息過短，視為無關略過")
            return False, None
        # icon/material/rtp 沒指定遊戲時例外：這幾個欄位廠商在知識庫另外設有「沒有指定遊戲時」
        # 的通用問答（不像 min bet、volatility 等欄位，沒有指定遊戲就完全沒有意義的答案），
        # 所以不要在這裡直接攔截轉人工，讓它改走知識庫查詢，才能查到那份通用問答的內容。
        _KB_FALLBACK_FIELDS = {"icon", "material", "rtp"}
        insufficient_fields = {str(f).strip().lower() for f in (intent.get("fields") or [])}
        if insufficient_fields and insufficient_fields <= _KB_FALLBACK_FIELDS:
            logger.info(f"Bot {bot_id} TADA Gamelist 查詢：僅提及{insufficient_fields}且無指定遊戲，改走知識庫查詢")
            return False, None
        logger.info(f"Bot {bot_id} TADA Gamelist 查詢：問題不完整，跳過知識庫直接轉人工")
        return True, None

    if kind == "top_games":
        from services.tada_gamelist_service import GAMERANK_SHEET_URL
        region_text = intent.get("region_text") or ""
        count = intent.get("count") or 10
        if not region_text.strip():
            # 情境A（未指定地區）：規格要求給整份總表連結，不主動列出排行
            return True, (
                f"您好~這邊幫您整理了熱門遊戲的排行總表，每月會更新，歡迎參考：\n{GAMERANK_SHEET_URL}"
                if is_zh else
                f"Hi, here's our top games ranking sheet (updated monthly), please have a look:\n{GAMERANK_SHEET_URL}"
            )
        region, subgroup = resolve_region_and_subgroup(region_text)
        if not region:
            logger.info(f"Bot {bot_id} TADA Gamelist 熱門排行：無法辨識地區「{region_text}」，轉人工")
            return True, None
        games = await asyncio.to_thread(get_top_games, region, count, subgroup)
        if not games:
            logger.info(f"Bot {bot_id} TADA Gamelist 熱門排行：查無資料（region={region}, subgroup={subgroup}），轉人工")
            return True, None
        lines = [f"{g['rank']}. {g['name']} (ID: {g['game_id']})" for g in games]
        if subgroup:
            # 有比對到具體幣別的獨立排行，直接就是該幣別的資料，不需要「合併地區」的揭露文字
            if is_zh:
                header = f"目前 {region_text} 的熱門遊戲排行大概是這幾款："
                footer = f"\n\n如果需要看其他地區或幣別的排行，這邊有總表可以參考：{GAMERANK_SHEET_URL}"
            else:
                header = f"Here are the current top performing games specifically for {region_text}:"
                footer = f"\n\nIf you need other regions or currencies, here's the full ranking sheet: {GAMERANK_SHEET_URL}"
        else:
            # 只辨識到國家/大區域、沒有指定到具體幣別分組，規格要求誠實說明這是「合併整個地區」的數據
            if is_zh:
                header = f"目前 {region_text} 地區賣得比較好的遊戲大概是這幾款："
                footer = f"\n\n這是合併整個地區的數據，如果需要看其他地區或完整名單，這邊有總表可以參考：{GAMERANK_SHEET_URL}"
            else:
                header = f"Here are the current top performing games in the {region_text} region:"
                footer = f"\n\nThis is combined data for the whole region, here's the full ranking sheet if you need other regions or the complete list: {GAMERANK_SHEET_URL}"
        return True, header + "\n" + "\n".join(lines) + footer

    if kind == "single_field":
        game_text = (intent.get("game") or "").strip()
        field_kws = intent.get("fields") or []
        if not game_text or not field_kws:
            return True, None
        game = await asyncio.to_thread(find_game, game_text)
        if not game:
            logger.info(f"Bot {bot_id} TADA Gamelist 欄位查詢：找不到遊戲「{game_text}」，轉人工")
            return True, None
        fields = resolve_field_names(field_kws)
        if not fields:
            return True, None
        from services.tada_gamelist_service import display_field_name
        parts = [f"{display_field_name(f)}：{game.get(f) or '（無資料）'}" for f in fields]
        return True, "\n".join(parts)

    if kind == "filter":
        from services.tada_gamelist_service import GAMELIST_SHEET_URL
        conditions = intent.get("conditions") or {}
        if not conditions:
            return True, None
        resolved_conditions = {}
        for kw, val in conditions.items():
            cols = resolve_field_names([kw])
            if cols:
                resolved_conditions[cols[0]] = val
        if not resolved_conditions:
            return True, None
        matches = await asyncio.to_thread(filter_games, resolved_conditions)
        if not matches:
            return True, (
                f"目前查詢不到符合條件的遊戲，建議您參考總表確認最新清單：{GAMELIST_SHEET_URL}"
                if is_zh else
                f"No games found matching those conditions, please check the full list here: {GAMELIST_SHEET_URL}"
            )
        # 比照規格文件範例：只示意列出幾筆，完整清單附總表連結，不把符合的全部條列出來
        shown = matches[:5]
        names = "、".join(f"{g.get('Name')}" for g in shown) if is_zh else ", ".join(f"{g.get('Name')}" for g in shown)
        if is_zh:
            reply = f"符合的遊戲有：{names}（示意，完整需查總表：{GAMELIST_SHEET_URL}）。"
        else:
            reply = f"Matching games include: {names} (for reference only, full list: {GAMELIST_SHEET_URL})."
        return True, reply

    return False, None


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

    def send_message(self, bot_id: int, chat_id: str, text: str, reply_to_message_id: int = None, reply_markup=None):
        """從後台主動向指定聊天室發送訊息（同步呼叫），可帶 reply_to_message_id 引用原訊息、
        reply_markup 附加鍵盤（例如 ForceReply）。回傳送出的 Message 物件，方便呼叫端取得 message_id。"""
        if bot_id not in self._apps or bot_id not in self._loops:
            raise ValueError(f"Bot {bot_id} 未在運行中")
        loop = self._loops[bot_id]
        app = self._apps[bot_id]
        kwargs = {"chat_id": int(chat_id), "text": text}
        if reply_to_message_id:
            kwargs["reply_to_message_id"] = reply_to_message_id
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        future = asyncio.run_coroutine_threadsafe(
            app.bot.send_message(**kwargs),
            loop
        )
        return future.result(timeout=10)

    async def _run_bot(self, bot_id: int, token: str):
        from database import SessionLocal
        try:
            app = Application.builder().token(token).build()
        except Exception as e:
            logger.error(f"Bot {bot_id} 建立失敗（Token 可能無效）：{e}")
            return

        self._apps[bot_id] = app

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            # 純文字訊息用 text；圖片/檔案等帶圖說的訊息用 caption（圖片本身不處理）
            raw_text = update.message.text or update.message.caption
            if not raw_text:
                return
            text = raw_text.strip()
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

        app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))

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
                    # 例外關鍵字（逗號分隔）：訊息含其中任一關鍵字時，此則訊息不忽略、照常處理
                    if ig.exception_keyword:
                        keywords = [k.strip() for k in ig.exception_keyword.split(',') if k.strip()]
                        if any(k.lower() in text.lower() for k in keywords):
                            logger.info(f"Bot {bot_id} 來自 {ig.identifier} 的訊息命中例外關鍵字，照常處理")
                            break
                    logger.info(f"Bot {bot_id} 忽略來自 {ig.identifier} 的訊息")
                    return

        # 取得聊天室資訊（供統計使用）
        chat = update.message.chat
        chat_id = str(chat.id)
        chat_name = chat.title or chat.full_name or chat.username or f"Chat {chat.id}"
        chat_type = chat.type or "unknown"
        sender_name = update.message.from_user.full_name if update.message.from_user else None

        # 0.2 收回指令：回覆機器人自己發送的訊息 + 特定關鍵字，且發送者在「機器人管理員名單」內，
        # 才會真的刪除該則訊息（deleteMessage）。非管理員或未回覆機器人訊息時完全不處理，
        # 不影響後續一般流程。
        if text.strip().lower() in _UNDO_COMMANDS and update.message.reply_to_message:
            replied = update.message.reply_to_message
            bot_user = update.get_bot()
            replied_is_self = bool(replied.from_user) and replied.from_user.id == bot_user.id
            if replied_is_self:
                is_admin = False
                if sender_id or sender_username:
                    admins = db.query(models.TelegramBotAdmin).filter(
                        models.TelegramBotAdmin.bot_id == bot_id,
                        models.TelegramBotAdmin.is_enabled == True
                    ).all()
                    for ad in admins:
                        val = ad.identifier.lstrip("@").lower()
                        if sender_id == val or sender_username == val:
                            is_admin = True
                            break
                if is_admin:
                    # 完全靜默：成功或失敗都不回覆任何訊息，避免在群組留下多餘通知
                    try:
                        await replied.delete()
                        logger.info(f"Bot {bot_id} 管理員（{sender_id or sender_username}）收回訊息 msg_id={replied.message_id}")
                    except Exception as e:
                        logger.error(f"Bot {bot_id} 收回訊息失敗：{e}", exc_info=True)
                else:
                    logger.info(f"Bot {bot_id} 非管理員（{sender_id or sender_username}）嘗試收回訊息，已忽略")
                return

        # 每次收到訊息都更新群組名稱（確保改名後能同步）
        _refresh_chat_name(bot_id, chat_id, chat_name, db)

        # 0.3 TADA 認證文件查詢的追問回覆比對（需開啟開關；訊息必須是「回覆」機器人先前
        # 發出的追問訊息，用 reply_to_message_id 精準比對，不受中間插入其他訊息影響）
        if bot_record.tada_certification_query_enabled and sender_id and update.message.reply_to_message:
            from services.tada_certification_service import (
                get_pending, clear_pending, resolve_market_reply, extract_game_identifier,
                save_pending, build_final_reply, game_question, market_mismatch_message,
            )
            _cert_pending = get_pending(db, bot_id, chat_id, sender_id)
            if _cert_pending and update.message.reply_to_message.message_id == _cert_pending.prompt_message_id:
                _cert_zh = _cert_pending.is_chinese
                if _cert_pending.missing == "market":
                    _cert_candidates = json.loads(_cert_pending.candidate_markets or "[]")
                    _cert_market = resolve_market_reply(text, _cert_candidates)
                    if not _cert_market:
                        _cert_sent = await update.message.reply_text(
                            market_mismatch_message(_cert_candidates, _cert_zh),
                            reply_markup=ForceReply(selective=True),
                        )
                        _cert_pending.prompt_message_id = _cert_sent.message_id
                        db.commit()
                        return
                    if _cert_pending.doc_type == "game":
                        _cert_sent = await update.message.reply_text(
                            game_question(_cert_zh), reply_markup=ForceReply(selective=True)
                        )
                        save_pending(db, bot_id, chat_id, sender_id, _cert_sent.message_id, "game",
                                     _cert_pending.doc_keyword, _cert_pending.doc_type, _cert_zh,
                                     resolved_market=_cert_market, original_text=_cert_pending.original_text)
                    else:
                        _cert_reply = await asyncio.to_thread(
                            build_final_reply, _cert_market, _cert_pending.doc_keyword, _cert_pending.doc_type, _cert_zh
                        )
                        await update.message.reply_text(_cert_reply)
                        clear_pending(db, _cert_pending)
                        _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                else:
                    _cert_game_id = extract_game_identifier(text)
                    _cert_reply = await asyncio.to_thread(
                        build_final_reply, _cert_pending.resolved_market, _cert_pending.doc_keyword,
                        _cert_pending.doc_type, _cert_zh, _cert_game_id
                    )
                    await update.message.reply_text(_cert_reply)
                    clear_pending(db, _cert_pending)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                return

        # 0.5. 後台白名單自動處理（優先於關鍵字/KB，管控模式下仍執行）
        # 預先讀取群組設定（廠商驗證 + 群組層級管控模式皆從此讀取）
        _group_setting = db.query(models.TelegramGroupSetting).filter(
            models.TelegramGroupSetting.bot_id == bot_id,
            models.TelegramGroupSetting.chat_id == chat_id,
        ).first()

        # 管控模式：Bot 層級（全域主開關）OR 群組層級（個別群組）
        is_managed = bool(bot_record.is_managed) or bool(_group_setting.is_managed if _group_setting else False)

        # 自動建立工單開關（群組層級，預設開啟）；關閉時完全不建單，Notify 通知也連帶不會觸發
        _ticket_creation_enabled = bool(_group_setting.ticket_creation_enabled if _group_setting else True)

        allowed_vendors: list = []
        if (_group_setting and _group_setting.whitelist_vendor_check
                and _group_setting.whitelist_allowed_vendors):
            allowed_vendors = [
                v.strip() for v in _group_setting.whitelist_allowed_vendors.split(',')
                if v.strip()
            ]

        if bot_record.whitelist_enabled and not _is_application_form(text):
            from services.whitelist_service import detect_whitelist_request, parse_whitelist_request, run_whitelist_sync
            _relaxed_bo = bool(_group_setting.relaxed_bo_detect if _group_setting else False)
            if detect_whitelist_request(text, relaxed=_relaxed_bo):
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
                                            "success" if success else "failed", db,
                                            full_username="_".join(username_parts))
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
                        if _ticket_creation_enabled:
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
                elif ips and _group_setting and _group_setting.single_vendor_mode and _group_setting.single_vendor_name:
                    # 單一總代理模式：訊息只有 IP + 關鍵字、沒有帳號，直接用此群組設定的總代理名稱加白
                    logger.info(f"Bot {bot_id} 偵測到白名單請求（無帳號），使用單一總代理模式：{_group_setting.single_vendor_name}")
                    import re as _re_wl2
                    _wl_is_chinese2 = bool(_re_wl2.search(r'[一-鿿㐀-䶿]', text))
                    try:
                        success, matched_vendor, vendor_rejected = await asyncio.to_thread(
                            run_whitelist_sync, [], ips, allowed_vendors,
                            forced_vendor_name=_group_setting.single_vendor_name,
                        )
                    except Exception as e:
                        logger.error(f"Bot {bot_id} 白名單自動化例外（單一總代理模式）：{e}", exc_info=True)
                        success, matched_vendor, vendor_rejected = False, None, False
                    _save_whitelist_log(bot_id, chat_id, chat_name,
                                        matched_vendor or _group_setting.single_vendor_name, "\n".join(ips),
                                        "success" if success else "failed", db,
                                        full_username=f"(單一總代理：{_group_setting.single_vendor_name})")
                    if success:
                        try:
                            await update.message.reply_text("Done")
                            logger.info(f"Bot {bot_id} 已回覆 Done（單一總代理模式）")
                        except Exception as e:
                            logger.error(f"Bot {bot_id} 回覆 Done 失敗（單一總代理模式）：{e}", exc_info=True)
                        if _ticket_creation_enabled:
                            threading.Thread(
                                target=_create_freshdesk_ticket_bg,
                                args=(text, "Done", chat_name), daemon=True
                            ).start()
                    elif vendor_rejected:
                        _wl_reject_reply2 = (
                            "您好，人員將會協助確認，請稍後"
                            if _wl_is_chinese2
                            else "Hello, our team will assist you shortly. Please wait."
                        )
                        try:
                            await update.message.reply_text(_wl_reject_reply2)
                            logger.info(f"Bot {bot_id} 廠商驗證拒絕（單一總代理模式），已回覆固定訊息")
                        except Exception as e:
                            logger.error(f"Bot {bot_id} 回覆廠商拒絕訊息失敗（單一總代理模式）：{e}", exc_info=True)
                    # 其他失敗（廠商名稱找不到、登入失敗等）靜默，不回覆
                    return
                else:
                    logger.warning(f"Bot {bot_id} 白名單請求解析失敗（無法取得廠商或IP）")

        # 0.6 JILI 遊戲素材查詢（僅該機器人開啟此功能時執行，優先於關鍵字/知識庫）
        if bot_record.game_asset_enabled:
            from services.game_asset_service import get_cached_game_list, search_game
            reply_text = await _try_game_asset_reply(bot_id, text, db, get_cached_game_list, search_game, "JILI")
            if reply_text:
                await update.message.reply_text(reply_text)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                if _ticket_creation_enabled:
                    threading.Thread(
                        target=_create_freshdesk_ticket_bg,
                        args=(text, reply_text, chat_name), daemon=True
                    ).start()
                return
            # 完全比對不到遊戲或全部查無資料：不中止，改走知識庫查詢，找不到答案再走統一 fallback

        # 0.7 TADA 遊戲素材查詢（僅該機器人開啟此功能時執行，與 JILI 為獨立開關，一個機器人通常只會開其中一種）
        if bot_record.tada_asset_enabled:
            from services.game_asset_service import get_cached_tada_game_list, search_tada_game
            reply_text = await _try_game_asset_reply(bot_id, text, db, get_cached_tada_game_list, search_tada_game, "TADA")
            if reply_text:
                await update.message.reply_text(reply_text)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                if _ticket_creation_enabled:
                    threading.Thread(
                        target=_create_freshdesk_ticket_bg,
                        args=(text, reply_text, chat_name), daemon=True
                    ).start()
                return
            # 完全比對不到遊戲或全部查無資料：不中止，改走知識庫查詢，找不到答案再走統一 fallback

        # 0.8 TADA Gamelist 進階查詢（熱門排行/欄位查詢/複合篩選，獨立開關，預設關閉，僅該機器人開啟時執行）
        if bot_record.tada_gamelist_query_enabled:
            gl_handled, gl_reply = await _try_tada_gamelist_reply(bot_id, text, db)
            if gl_handled:
                if gl_reply:
                    await update.message.reply_text(gl_reply)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    if _ticket_creation_enabled:
                        threading.Thread(
                            target=_create_freshdesk_ticket_bg,
                            args=(text, gl_reply, chat_name), daemon=True
                        ).start()
                else:
                    # 判定為 Gamelist 查詢但條件不充分/查無資料：不猜、不追問，直接轉人工
                    # 注意：這個函式內其他地方有區域性 `import re`，會讓 re 變成整個函式的區域變數，
                    # 因此這裡改用別名 import，避免用到還沒賦值的區域變數（UnboundLocalError）。
                    import re as _re_gl
                    _wl_is_chinese_gl = bool(_re_gl.search(r'[一-鿿㐀-䶿]', text))
                    fallback_gl = _FALLBACK_TRANSFER_MSG_ZH if _wl_is_chinese_gl else _FALLBACK_TRANSFER_MSG_EN
                    await update.message.reply_text(fallback_gl)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    _save_no_answer_log(bot_id, chat_id, chat_name, text, db)
                return
            # 與 Gamelist 查詢無關：不中止，改走知識庫查詢

        # 0.85 TADA 認證文件查詢（獨立開關，偵測到文件類型關鍵字才觸發；
        # 缺市場/缺遊戲時用 ForceReply 追問，見 services/tada_certification_service.py）
        if bot_record.tada_certification_query_enabled and sender_id:
            from services.tada_certification_service import (
                detect_doc_query, detect_market_in_text, save_pending, build_final_reply, build_market_question,
                game_question, is_chinese_text, no_data_message, vendor_escalate_message,
                is_whole_market_request, whole_market_reply,
            )
            _cert_hit = detect_doc_query(text)
            if _cert_hit:
                _doc_keyword, _cert_markets, _doc_type = _cert_hit
                _is_zh_cert = is_chinese_text(text)
                if _doc_type == "no_data":
                    await update.message.reply_text(no_data_message(_is_zh_cert))
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    _save_no_answer_log(bot_id, chat_id, chat_name, text, db)
                    return
                if _doc_type == "vendor_escalate":
                    await update.message.reply_text(vendor_escalate_message(_is_zh_cert))
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    _save_no_answer_log(bot_id, chat_id, chat_name, text, db)
                    return
                if len(_cert_markets) == 1:
                    _cert_market = _cert_markets[0]
                else:
                    _mentioned = [m for m in detect_market_in_text(text) if m in _cert_markets]
                    _cert_market = _mentioned[0] if len(_mentioned) == 1 else None
                if not _cert_market:
                    _cert_sent = await update.message.reply_text(
                        build_market_question(_doc_keyword, _cert_markets, _is_zh_cert),
                        reply_markup=ForceReply(selective=True),
                    )
                    save_pending(db, bot_id, chat_id, sender_id, _cert_sent.message_id, "market",
                                 _doc_keyword, _doc_type, _is_zh_cert, candidate_markets=_cert_markets, original_text=text)
                    return
                if _doc_type == "game":
                    # 廠商已明確表示要「整個市場」而非單一遊戲：不追問遊戲，直接給市場層級連結（文件 5a）
                    if is_whole_market_request(text):
                        await update.message.reply_text(whole_market_reply(_cert_market, _is_zh_cert))
                        _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                        return
                    _cert_sent = await update.message.reply_text(
                        game_question(_is_zh_cert), reply_markup=ForceReply(selective=True)
                    )
                    save_pending(db, bot_id, chat_id, sender_id, _cert_sent.message_id, "game",
                                 _doc_keyword, _doc_type, _is_zh_cert, resolved_market=_cert_market, original_text=text)
                    return
                # doc_type == "platform"：市場唯一且不分遊戲，直接查表回覆（不需要追問）
                _cert_reply = await asyncio.to_thread(build_final_reply, _cert_market, _doc_keyword, _doc_type, _is_zh_cert)
                await update.message.reply_text(_cert_reply)
                _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                return

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
                    _save_pending_reply(bot_id, chat_id, msg.id, reply_text, db, source="keyword")
                else:
                    await update.message.reply_text(reply_text)
                    _record_group_stat(bot_id, chat_id, chat_name, chat_type, db)
                    if _ticket_creation_enabled:
                        threading.Thread(target=_create_freshdesk_ticket_bg, args=(text, reply_text, chat_name), daemon=True).start()
                return

        # 功能一：訊息少於 10 字元且關鍵字無匹配 → 跳過
        if len(text.strip()) < _MIN_TEXT_LEN:
            logger.debug(f"Bot {bot_id} 訊息長度 {len(text.strip())} < {_MIN_TEXT_LEN}，略過")
            return

        # 功能一-a：純問候/感謝/道別語，或訊息含「ignore」字樣 → 跳過，不回覆不記錄
        if _is_greeting_or_thanks(text) or _contains_ignore_keyword(text):
            logger.debug(f"Bot {bot_id} 偵測到純問候/感謝語或ignore關鍵字，略過：「{text[:30]}」")
            return

        # 功能一-b：申請表單格式偵測 / 一定查不到答案的主題（進度詢問、重置密碼、玩家個案投訴、單獨貼IP等）→ 跳過知識庫，直接 fallback
        if (_is_application_form(text) or _is_no_kb_topic(text) or _is_player_report(text)
                or _is_bare_ip_message(text) or _is_bare_code_message(text) or _is_rtp_anomaly_complaint(text)
                or _is_bare_mention_message(text) or _is_bare_timestamp_message(text)):
            logger.info(f"Bot {bot_id} 偵測到申請表單格式或無解答主題，跳過知識庫直接 fallback")
            if bool(_group_setting.silent_no_answer if _group_setting else False):
                _save_no_answer_log(bot_id, chat_id, chat_name, text, db)
                return
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
                if _ticket_creation_enabled:
                    threading.Thread(target=_create_freshdesk_ticket_bg, args=(text, reply, chat_name), daemon=True).start()
            else:
                # 沒有關鍵字規則也沒有知識庫結果 → fallback
                if bool(_group_setting.silent_no_answer if _group_setting else False):
                    # 靜默模式：不回覆、不受冷卻限制，仍記錄無解答 log
                    _save_no_answer_log(bot_id, chat_id, chat_name, text, db,
                                        input_tokens=input_tokens, output_tokens=output_tokens,
                                        cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens)
                    return
                # 一般模式（含冷卻）
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


def _save_pending_reply(bot_id, chat_id, message_id, reply_text, db, source="knowledge_base"):
    import models
    pending = models.TelegramPendingReply(
        bot_id=bot_id, chat_id=chat_id, message_id=message_id,
        reply_text=reply_text, status="pending", source=source,
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
    from timezone_utils import taipei_today
    import models
    today = taipei_today().isoformat()
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


def _save_whitelist_log(bot_id, chat_id, chat_name, vendor_name, ip_list, status, db, full_username=None):
    import models
    log = models.WhitelistLog(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name,
        vendor_name=vendor_name, full_username=full_username, ip_list=ip_list, status=status,
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


def _send_notify_message(ticket_id, group_name: str, question: str, error_msg: str = None, answer: str = None):
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
                f"問題訊息：{question}",
                f"回覆內容：{answer or ''}",
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
            timeout=90,
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
    _send_notify_message(ticket_id, group_name, question, error_msg, answer=answer)
