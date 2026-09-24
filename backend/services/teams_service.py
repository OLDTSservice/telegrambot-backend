"""Teams 個人帳號機器人：輪詢群組訊息 → 後台白名單自動處理／查輸贏回覆 → 引用回覆。

原理（與 Teams 消費者版網頁用戶端同一條路，純 HTTP、無官方 API）：
  裝置代碼登入（一次）→ refresh token（存 DB，每次用都換新）
  refresh token → RPS access token（login.live.com）→ skypetoken（teams.live.com authz v1.0，約 1 天）
  skypetoken → chatsvc 讀訊息 / 發訊息

硬限制（實測）：
  * 整個帳號每分鐘 15 次呼叫，讀＋寫合計，超過回 429 → 這裡用令牌桶，沒額度就等，不會掉訊息只會慢
  * 每個請求都要帶 ms-ic3-product: tfl，否則舊 @thread.skype 群組回 404
  * 同一份 refresh token 只能有一個實例在用（滾動更新會互踢）

輪詢策略（省額度）：每輪 1 次 GET /conversations 拿每群 lastMessage.id，沒變的群跳過（0 次），
有變才 GET 該群最新 50 則，只處理 id 大於上次記錄的訊息（id 是毫秒時間戳）。
"""
import base64
import html
import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---- Teams 消費者版權杖鏈常數（實測可用，勿改）------------------------------------
MSA_CLIENT = "4b3e8f46-56d3-427f-b1e2-d239b2ea6bca"        # Teams 消費者網頁用戶端
MSA_SCOPE = "service::api.fl.spaces.skype.com::MBI_SSL openid profile offline_access"
DEVICECODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
DEVICECODE_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
RPS_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
AUTHZ_URL = "https://teams.live.com/api/auth/v1.0/authz/consumer"   # 一定要 v1.0，v2.0 回 401
CHATSVC_BASE = "https://teams.live.com/api/chatsvc/consumer/v1/users/ME"
SKYPETOKEN_TTL = 20 * 3600
RATE_PER_MIN = 15
MIN_POLL_INTERVAL = 10
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
IC3_HEADERS = {
    "ms-ic3-product": "tfl",
    "ms-ic3-additional-product": "Sfl",
    "x-ms-request-priority": "20",
    "clientinfo": ("os=windows; osVer=NT 10.0; proc=x86; lcid=zh-tw; deviceType=1; "
                   "country=tw; clientName=skypeteams; clientVer=1415/26080200346; "
                   "utcOffset=+08:00; timezone=Asia/Taipei"),
}
# 只處理人打的訊息；ThreadActivity/*（加成員、改群名…）也會出現在訊息清單裡，要濾掉
_HUMAN_MESSAGE_TYPES = ("RichText/Html", "RichText", "Text")
PENDING_WINDOW_SEC = 180 * 60          # 申請先來、IP 後補：多久內的補充訊息算同一筆


class TeamsAuthError(Exception):
    """refresh token 失效／被撤銷，需要重新登入"""


# ================================================================ 小工具
def _form_post(url: str, data: dict):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 method="POST", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        try:
            return None, json.loads(e.read() or "{}")
        except Exception:
            return None, {"error": f"http_{e.code}"}


def _jwt_payload(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def mri_from_skypetoken(skypetoken: str) -> Optional[str]:
    sid = _jwt_payload(skypetoken).get("skypeid")
    return f"8:{sid}" if sid else None


def clean_text(content: Optional[str]) -> str:
    """去掉「引用回覆」區塊與 HTML 標籤 → 純文字。
    引用區塊一定要去掉，否則原文的關鍵字會在每次被引用時重複命中。"""
    c = re.sub(r"<blockquote\b.*?</blockquote>", "", content or "", flags=re.S | re.I)
    # 表格／清單（廠商從 Excel、Word 貼上）的列與項目也要換行，否則整份申請會壓成一行，
    # 依行掃描的白名單帳號解析與查輸贏帳號擷取都會失準
    c = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", c, flags=re.I)
    c = re.sub(r"</t[dh]>", " ", c, flags=re.I)     # 同一列的儲存格之間留空白，避免黏成一個字
    c = re.sub(r"<[^>]+>", "", c)
    c = html.unescape(c).replace("\r", "")
    c = re.sub("[ \\t\\u00a0]+", " ", c)   # 含 &nbsp;
    return re.sub(r"\n\s*\n+", "\n", c).strip()


def _sender_of(msg: dict) -> tuple[str, str]:
    mri = (msg.get("from") or "").rsplit("/", 1)[-1]
    return mri, (msg.get("imdisplayname") or mri)


# ================================================================ 裝置代碼登入（供 router 使用）
_login_sessions: dict[str, dict] = {}
_login_lock = threading.Lock()


def start_device_login(name: str, bot_id: Optional[int] = None) -> dict:
    """開始裝置代碼流程。回傳給前端顯示的網址與代碼；之後前端輪詢 poll_device_login()。"""
    started, err = _form_post(DEVICECODE_URL, {"client_id": MSA_CLIENT, "scope": MSA_SCOPE})
    if err:
        raise RuntimeError(f"無法開始登入：{err.get('error_description', err)}")
    sid = secrets.token_urlsafe(16)
    with _login_lock:
        # 同時只保留最近幾個 session，過期的清掉
        now = time.time()
        for k in [k for k, s in _login_sessions.items() if s["expires_at"] < now]:
            _login_sessions.pop(k, None)
        _login_sessions[sid] = {
            "name": name, "bot_id": bot_id,
            "device_code": started["device_code"],
            "user_code": started["user_code"],
            "verification_uri": started["verification_uri"],
            "expires_at": now + started.get("expires_in", 900),
            "interval": started.get("interval", 5),
            "last_poll": 0.0,
            "status": "pending", "error": None, "result": None,
        }
    return {"session_id": sid, "user_code": started["user_code"],
            "verification_uri": started["verification_uri"],
            "expires_in": started.get("expires_in", 900)}


def poll_device_login(session_id: str) -> dict:
    """前端每幾秒呼叫一次。成功時 result 含 refresh_token / account 資訊，由 router 寫入 DB。"""
    with _login_lock:
        s = _login_sessions.get(session_id)
    if not s:
        return {"status": "error", "error": "登入工作階段不存在或已過期，請重新開始"}
    if s["status"] != "pending":
        # 已成功／失敗的 session 保留到過期，讓前端重複輪詢（或請求交錯）都拿到同一個結果
        return {"status": s["status"], "error": s["error"], "session": s}
    now = time.time()
    if now > s["expires_at"]:
        s["status"], s["error"] = "error", "代碼已過期，請重新開始登入"
        return {"status": "error", "error": s["error"]}
    if now - s["last_poll"] < s["interval"]:        # 微軟要求輪詢間隔 ≥ interval
        return {"status": "pending"}
    s["last_poll"] = now
    tok, err = _form_post(DEVICECODE_TOKEN_URL, {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": MSA_CLIENT, "device_code": s["device_code"]})
    if tok:
        claims = _jwt_payload(tok.get("id_token", ""))
        s["result"] = {
            "refresh_token": tok["refresh_token"],
            "account_name": claims.get("name"),
            "account_email": claims.get("preferred_username") or claims.get("email"),
        }
        s["status"] = "success"
        return {"status": "success", "session": s}
    code = (err or {}).get("error")
    if code == "authorization_pending":
        return {"status": "pending"}
    if code == "slow_down":
        s["interval"] += 5
        return {"status": "pending"}
    s["status"], s["error"] = "error", f"登入失敗（{code}）：{(err or {}).get('error_description', '')[:200]}"
    return {"status": "error", "error": s["error"]}


# ================================================================ 每個帳號一個 client：權杖＋速率桶＋HTTP
class TeamsAccountClient:
    """一個 Teams 個人帳號的所有 HTTP 呼叫都經過這裡：令牌桶 → 請求 → 401/403 換 token → 429 冷卻。
    refresh token 每次續期都會換新，透過 on_refresh_token 回呼寫回 DB。"""

    def __init__(self, bot_id: int, refresh_token: str, on_refresh_token):
        self.bot_id = bot_id
        self._refresh_token = refresh_token
        self._on_refresh_token = on_refresh_token
        self._skypetoken: Optional[str] = None
        self._skypetoken_at = 0.0
        self.mri: Optional[str] = None
        self._lock = threading.Lock()
        self._tokens = float(RATE_PER_MIN)
        self._tokens_at = time.time()

    # ---- 速率桶 ----
    def take_token(self):
        while True:
            with self._lock:
                now = time.time()
                self._tokens = min(RATE_PER_MIN, self._tokens + (now - self._tokens_at) * RATE_PER_MIN / 60.0)
                self._tokens_at = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) * 60.0 / RATE_PER_MIN
            time.sleep(min(wait, 5.0) + 0.05)

    def _drain_bucket(self):
        with self._lock:
            self._tokens, self._tokens_at = 0.0, time.time()

    # ---- 權杖鏈 ----
    def _mint(self) -> str:
        tok, err = _form_post(RPS_TOKEN_URL, {
            "grant_type": "refresh_token", "client_id": MSA_CLIENT,
            "refresh_token": self._refresh_token, "scope": MSA_SCOPE})
        if err:
            raise TeamsAuthError(f"refresh token 失效（可能被撤銷或閒置超過 90 天），請重新登入：{err.get('error_description', err)}")
        if tok.get("refresh_token"):                 # 滾動更新：一定要接住存回
            self._refresh_token = tok["refresh_token"]
            try:
                self._on_refresh_token(self.bot_id, tok["refresh_token"])
            except Exception as e:  # noqa: BLE001
                logger.error(f"[Teams {self.bot_id}] 寫回 refresh token 失敗：{e}")
        req = urllib.request.Request(AUTHZ_URL, data=b"", method="POST", headers={
            "Authorization": f"Bearer {tok['access_token']}",
            "Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            self._skypetoken = json.loads(r.read())["skypeToken"]["skypetoken"]
        self._skypetoken_at = time.time()
        self.mri = mri_from_skypetoken(self._skypetoken)
        return self._skypetoken

    def ensure_auth(self, force: bool = False) -> str:
        if not force and self._skypetoken and time.time() - self._skypetoken_at < SKYPETOKEN_TTL:
            return self._skypetoken
        return self._mint()

    # ---- HTTP ----
    def _request(self, url: str, method: str = "GET", body: Optional[dict] = None):
        self.take_token()
        skypetoken = self.ensure_auth()
        for attempt in range(3):
            headers = {"authentication": f"skypetoken={skypetoken}",
                       "behavioroverride": "redirectAs404", "User-Agent": UA, **IC3_HEADERS}
            data = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and attempt == 0:
                    skypetoken = self.ensure_auth(force=True)
                    continue
                if e.code == 429:
                    logger.warning(f"[Teams {self.bot_id}] 429 撞到伺服器上限，冷卻 60 秒")
                    self._drain_bucket()
                    time.sleep(60)
                    self.take_token()
                    continue
                raise
        raise RuntimeError(f"Teams 請求重試耗盡：{method} {url}")

    def fetch_conversations(self) -> list:
        """一次呼叫拿全部聊天，每個帶 lastMessage → 用來判斷哪個群組有新訊息。"""
        url = (f"{CHATSVC_BASE}/conversations?view=msnp24Equivalent|supportsMessageProperties"
               f"&pageSize=200&targetType=Passport|Skype|Lync|Thread")
        out, seen_link = [], None
        while url:
            data = self._request(url)
            out.extend(data.get("conversations", []))
            link = (data.get("_metadata") or {}).get("backwardLink")
            url = link if link and link != seen_link and data.get("conversations") else None
            seen_link = link
        return out

    def fetch_messages(self, chat_id: str, page_size: int = 50) -> list:
        """讀一個群組最新 page_size 則（回傳 新→舊）。"""
        url = (f"{CHATSVC_BASE}/conversations/{urllib.parse.quote(chat_id)}/messages"
               f"?pageSize={page_size}&view=msnp24Equivalent&startTime=0")
        return self._request(url).get("messages", [])

    def send_reply(self, chat_id: str, orig_msg: dict, reply_text: str) -> bool:
        """引用回覆某則訊息並 @ 原發送者（格式實測 HTTP 201）。"""
        msg_id = str(orig_msg["id"])
        sender_mri, sender_name = _sender_of(orig_msg)
        preview = clean_text(orig_msg.get("content"))[:200]
        esc = html.escape
        content = (
            f'<blockquote itemscope="" itemtype="http://schema.skype.com/Reply" itemid="{msg_id}">'
            f'<strong itemprop="mri" itemid="{sender_mri}">{esc(sender_name)}</strong>'
            f'<span itemprop="time" itemid="{msg_id}"></span>'
            f'<p itemprop="preview">{esc(preview)}</p></blockquote>'
            f'<p><span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="0">{esc(sender_name)}</span>'
            f'&nbsp;{esc(reply_text)}</p>'
        )
        body = {
            "content": content,
            "messagetype": "RichText/Html",
            "contenttype": "text",
            "clientmessageid": str(int(time.time() * 1000)),
            "properties": {
                "qtdMsgs": json.dumps([{"messageId": msg_id, "sender": sender_mri, "time": int(msg_id)}]),
                "mentions": json.dumps([{"@type": "http://schema.skype.com/Mention", "itemid": 0,
                                         "mri": sender_mri, "mentionType": "person",
                                         "displayName": sender_name}]),
            },
        }
        url = f"{CHATSVC_BASE}/conversations/{urllib.parse.quote(chat_id)}/messages"
        self._request(url, method="POST", body=body)
        return True


def group_chats(convs: list) -> dict:
    """濾出群組（19: 開頭、threadType=chat）。回 {chat_id: 名稱}。"""
    groups = {}
    for c in convs:
        cid = c.get("id", "")
        props = c.get("threadProperties") or {}
        if not cid.startswith("19:") or (props.get("threadType") or "").lower() != "chat":
            continue
        topic = html.unescape((props.get("topic") or "").strip())
        groups[cid] = topic if topic and not topic.startswith("19:") else cid
    return groups


# ================================================================ DB 小工具
def persist_refresh_token(bot_id: int, refresh_token: str):
    import models
    from database import SessionLocal
    db = SessionLocal()
    try:
        bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
        if bot:
            bot.refresh_token = refresh_token
            db.commit()
    finally:
        db.close()


def _record_teams_group_stat(bot_id: int, conversation_id: str, conv_name: str, db):
    import models as m
    from timezone_utils import taipei_today
    today = taipei_today().isoformat()
    stat = db.query(m.TeamsGroupStat).filter(
        m.TeamsGroupStat.bot_id == bot_id,
        m.TeamsGroupStat.conversation_id == conversation_id,
        m.TeamsGroupStat.date == today,
    ).first()
    if stat:
        stat.reply_count += 1
        stat.conversation_name = conv_name
    else:
        db.add(m.TeamsGroupStat(bot_id=bot_id, conversation_id=conversation_id,
                                conversation_name=conv_name, date=today, reply_count=1))
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error(f"記錄 Teams 群組統計失敗：{e}")
        db.rollback()


def _save_whitelist_log(db, bot_id, chat_id, chat_name, msg_id, sender, vendor_name, ips,
                        status, full_username=None, reply_sent=False):
    import models
    db.add(models.TeamsWhitelistLog(
        bot_id=bot_id, chat_id=chat_id, chat_name=chat_name, msg_id=str(msg_id), sender=sender,
        vendor_name=vendor_name, full_username=full_username, ip_list="\n".join(ips),
        status=status, reply_sent=reply_sent,
    ))
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error(f"儲存 Teams 白名單 log 失敗：{e}")
        db.rollback()


# ================================================================ Watcher
class TeamsWatcher(threading.Thread):
    """一個帳號一條 thread。每輪：讀 DB 拿最新開關與群組設定 → 1 次 /conversations → 有新訊息的群才讀。"""

    def __init__(self, bot_id: int, refresh_token: str):
        super().__init__(name=f"teams-watcher-{bot_id}", daemon=True)
        self.bot_id = bot_id
        self.client = TeamsAccountClient(bot_id, refresh_token, persist_refresh_token)
        self._stop = threading.Event()
        # 申請先來、IP 後補：{(chat_id, sender_mri): {"msg": 原訊息, "text": 純文字, "ts": 時間}}
        self._pending: dict[tuple, dict] = {}
        self._rounds = 0

    def stop(self):
        self._stop.set()

    # ---- 主迴圈 ----
    def run(self):
        logger.info(f"[Teams {self.bot_id}] watcher 啟動")
        while not self._stop.is_set():
            interval = 20
            try:
                interval = self._poll_once()
            except TeamsAuthError as e:
                logger.error(f"[Teams {self.bot_id}] 登入失效，watcher 停止：{e}")
                self._set_error(str(e))
                return
            except Exception as e:  # noqa: BLE001
                logger.error(f"[Teams {self.bot_id}] 這輪失敗：{type(e).__name__}: {str(e)[:200]}，下輪再試")
                self._set_error(f"{type(e).__name__}: {str(e)[:200]}")
            self._stop.wait(max(MIN_POLL_INTERVAL, interval))
        logger.info(f"[Teams {self.bot_id}] watcher 已停止")

    def _set_error(self, msg: Optional[str]):
        import models
        from database import SessionLocal
        db = SessionLocal()
        try:
            bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == self.bot_id).first()
            if bot:
                bot.last_error = msg
                if msg is None:
                    bot.last_poll_at = datetime.utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        finally:
            db.close()

    def _poll_once(self) -> int:
        import models
        from database import SessionLocal
        self._rounds += 1
        db = SessionLocal()
        try:
            bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == self.bot_id).first()
            if not bot or not bot.is_enabled:
                self.stop()
                return 0
            interval = bot.poll_interval_sec or 20
            settings = {s.chat_id: s for s in db.query(models.TeamsGroupSetting)
                        .filter(models.TeamsGroupSetting.bot_id == self.bot_id).all()}
            states = {s.chat_id: s for s in db.query(models.TeamsWatchState)
                      .filter(models.TeamsWatchState.bot_id == self.bot_id).all()}

            convs = self.client.fetch_conversations()
            groups = group_chats(convs)
            last_by_cid = {c["id"]: (c.get("lastMessage") or {}).get("id") for c in convs}
            # 群組設定裡有、但這次清單漏列的舊 @thread.skype 群，每 6 輪直接讀一次當保險
            for cid, s in settings.items():
                if cid not in groups and s.watch_enabled:
                    groups[cid] = s.chat_name or cid

            for cid, name in groups.items():
                setting = settings.get(cid)
                if setting and not setting.watch_enabled:
                    continue
                state = states.get(cid)
                if state is None:
                    # 第一次看到這群：以目前最後一則為基準，只處理之後的新訊息（不回溯）
                    state = models.TeamsWatchState(bot_id=self.bot_id, chat_id=cid, chat_name=name,
                                                   last_msg_id=str(last_by_cid.get(cid) or "0"))
                    db.add(state)
                    db.commit()
                    states[cid] = state
                    continue
                newest = last_by_cid.get(cid)
                if newest is None and self._rounds % 6 != 1:
                    continue
                if newest is not None and int(newest) <= int(state.last_msg_id or "0"):
                    continue

                msgs = self.client.fetch_messages(cid)
                last_seen = int(state.last_msg_id or "0")
                state.chat_name = name
                for m in sorted(msgs, key=lambda x: int(x["id"])):        # 舊 → 新
                    if int(m["id"]) <= last_seen:
                        continue
                    try:
                        self._process_message(db, bot, setting, cid, name, m)
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"[Teams {self.bot_id}] 處理訊息 {m.get('id')} 例外：{e}", exc_info=True)
                    # 每處理完一則就寫回進度：程式若在處理中被砍掉，重啟後最多只會重看「正在處理的那一則」，
                    # 而那一則還有 _handle_whitelist 的 msg_id 查重擋著
                    state.last_msg_id = str(m["id"])
                    db.commit()
                if msgs:
                    state.last_msg_id = str(max(int(state.last_msg_id or "0"), *(int(x["id"]) for x in msgs)))
                db.commit()

            self._expire_pending()
            self._set_error(None)
            return interval
        finally:
            db.close()

    # ---- 單則訊息 ----
    def _process_message(self, db, bot, setting, chat_id: str, chat_name: str, m: dict):
        if not (m.get("messagetype") or "").startswith(_HUMAN_MESSAGE_TYPES):
            return
        if (m.get("properties") or {}).get("deletetime"):
            return
        sender_mri, sender_name = _sender_of(m)
        if self.client.mri and sender_mri == self.client.mri:
            return
        if self._is_ignored(db, bot.id, sender_mri, sender_name):
            return
        text = clean_text(m.get("content"))
        if not text:
            return
        logger.info(f"[Teams {bot.id}] [{chat_name}] {sender_name}: {text[:80]!r}")

        # 順序同 Telegram：白名單優先，沒被白名單處理掉的訊息才判斷查輸贏
        if bot.whitelist_enabled and self._try_whitelist(db, bot, setting, chat_id, chat_name, m,
                                                         sender_mri, sender_name, text):
            return
        if bot.netwin_query_enabled and setting and setting.netwin_enabled:
            self._try_netwin(db, bot, setting, chat_id, chat_name, m, sender_name, text)

    @staticmethod
    def _is_ignored(db, bot_id: int, sender_mri: str, sender_name: str) -> bool:
        import models
        ignores = db.query(models.TeamsIgnore).filter(
            models.TeamsIgnore.bot_id == bot_id, models.TeamsIgnore.is_enabled == True).all()  # noqa: E712
        for ig in ignores:
            val = (ig.identifier or "").strip().lower()
            if val and val in (sender_mri.lower(), sender_name.lower()):
                return True
        return False

    # ---- 白名單 ----
    def _try_whitelist(self, db, bot, setting, chat_id, chat_name, m, sender_mri, sender_name, text) -> bool:
        """回傳 True＝這則已被白名單流程處理掉（不再往下判斷查輸贏）。"""
        from services.telegram_service import _is_application_form, _is_staging_environment_request
        from services.whitelist_service import (_IP_RE, _WHITELIST_WORDS, _has_backend_indicator,
                                                detect_whitelist_request)

        if _is_application_form(text) or _is_staging_environment_request(text):
            return False
        relaxed = bool(setting.relaxed_bo_detect if setting else False)
        key = (chat_id, sender_mri)

        if detect_whitelist_request(text, relaxed=relaxed):
            self._pending.pop(key, None)
            return self._handle_whitelist(db, bot, setting, chat_id, chat_name, m, sender_name, text)

        # 申請先來、IP 後補：有白名單＋後台字樣但沒 IP → 掛 pending；同人同群時窗內補 IP → 合併再判斷
        lower = text.lower()
        has_ip = bool(_IP_RE.search(text))
        looks_like_request = any(w in lower for w in _WHITELIST_WORDS) and _has_backend_indicator(text, lower)
        if looks_like_request and not has_ip:
            self._pending[key] = {"msg": m, "text": text, "ts": time.time()}
            logger.info(f"[Teams {bot.id}] 掛 pending（缺 IP）[{chat_name}] {sender_name}")
            return False
        p = self._pending.get(key)
        if p and has_ip and time.time() - p["ts"] <= PENDING_WINDOW_SEC:
            merged = p["text"] + "\n" + text
            if detect_whitelist_request(merged, relaxed=relaxed):
                self._pending.pop(key, None)
                logger.info(f"[Teams {bot.id}] pending 合併成功 [{chat_name}] {sender_name}")
                return self._handle_whitelist(db, bot, setting, chat_id, chat_name, m, sender_name, merged)
        return False

    def _expire_pending(self):
        now = time.time()
        for k in [k for k, p in self._pending.items() if now - p["ts"] > PENDING_WINDOW_SEC]:
            self._pending.pop(k, None)

    def _handle_whitelist(self, db, bot, setting, chat_id, chat_name, m, sender_name, text) -> bool:
        """回傳 False＝解析不出帳號/IP（同 Telegram，繼續往下判斷查輸贏）；其餘皆 True。"""
        import models
        from services.whitelist_service import parse_whitelist_request, run_whitelist_sync
        from services.telegram_service import _create_freshdesk_ticket_bg

        # 查重：同一則訊息只加白一次（防程式在寫回進度前被砍掉、重啟後重看同一則）
        if db.query(models.TeamsWhitelistLog).filter(
                models.TeamsWhitelistLog.bot_id == bot.id,
                models.TeamsWhitelistLog.msg_id == str(m["id"])).first():
            logger.info(f"[Teams {bot.id}] 訊息 {m['id']} 已處理過，略過")
            return True

        mode = bot.whitelist_mode or "full"
        vendor_code, all_parts, ips = parse_whitelist_request(text)
        allowed_vendors: list = []
        if setting and setting.whitelist_vendor_check and setting.whitelist_allowed_vendors:
            allowed_vendors = [v.strip() for v in setting.whitelist_allowed_vendors.split(",") if v.strip()]
        ticket_enabled = bool(setting.ticket_creation_enabled if setting else True)
        is_chinese = bool(re.search(r"[一-鿿㐀-䶿]", text))

        # 要跑哪些帳號：訊息有帳號 → 逐一；沒帳號但群組設了單一總代理 → 用總代理名稱
        jobs: list[tuple[list, Optional[str]]] = []
        if all_parts and ips:
            jobs = [(parts, None) for parts in all_parts]
        elif ips and setting and setting.single_vendor_mode and setting.single_vendor_name:
            jobs = [([], setting.single_vendor_name)]
        else:
            logger.warning(f"[Teams {bot.id}] 白名單請求解析失敗（無法取得帳號或 IP）")
            return False
        logger.info(f"[Teams {bot.id}] 偵測到白名單請求：帳號數={len(jobs)}, IPs={ips}, mode={mode}")

        if mode == "log_only":
            for parts, forced in jobs:
                _save_whitelist_log(db, bot.id, chat_id, chat_name, m["id"], sender_name,
                                    (parts[0] if parts else forced) or "unknown", ips, "log_only",
                                    full_username="_".join(parts) if parts else f"(單一總代理：{forced})")
            return True

        any_success = any_rejected = False
        for parts, forced in jobs:
            try:
                success, matched, rejected = run_whitelist_sync(parts, ips, allowed_vendors, forced_vendor_name=forced)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[Teams {bot.id}] 白名單自動化例外：{e}", exc_info=True)
                success, matched, rejected = False, None, False
            status = "success" if success else ("rejected" if rejected else "failed")
            _save_whitelist_log(db, bot.id, chat_id, chat_name, m["id"], sender_name,
                                matched or (parts[0] if parts else forced) or "unknown", ips, status,
                                full_username="_".join(parts) if parts else f"(單一總代理：{forced})",
                                reply_sent=(mode == "full" and (success or rejected)))
            any_success |= success
            any_rejected |= rejected

        if mode != "full":
            return True
        reply = None
        if any_success:
            reply = "Done"
        elif any_rejected:
            reply = "您好，人員將會協助確認，請稍後" if is_chinese else "Hello, our team will assist you shortly. Please wait."
        # 其他失敗（廠商無法解析、登入失敗等）靜默，不回覆
        if reply:
            try:
                self.client.send_reply(chat_id, m, reply)
                _record_teams_group_stat(bot.id, chat_id, chat_name, db)
                logger.info(f"[Teams {bot.id}] 已回覆：{reply}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"[Teams {bot.id}] 回覆失敗：{e}", exc_info=True)
        if any_success and ticket_enabled:
            threading.Thread(target=_create_freshdesk_ticket_bg,
                             args=(text, "Done", chat_name), daemon=True).start()
        return True


    # ---- 查輸贏回覆 ----
    def _try_netwin(self, db, bot, setting, chat_id, chat_name, m, sender_name, text):
        """觸發判斷與帳號擷取直接共用 Telegram 的 tjadmin_service（規則完全相同）；API 憑證、門檻、
        延遲秒數、回覆內容讀 netwin_source_bot_id 指定的 Telegram 機器人設定。
        與 Telegram 唯一的差別：只有查到結果、淨值與 RTP 都在門檻內才回覆，其餘情況一律靜默
        （這個帳號是同仁本人，不自動在廠商群發轉人工訊息），結果只寫紀錄供後台查看。"""
        import models
        from services.tjadmin_service import detect_netwin_query_request, extract_account

        if not detect_netwin_query_request(text):
            return
        msg_id = str(m["id"])
        if db.query(models.TeamsNetwinLog).filter(
                models.TeamsNetwinLog.bot_id == bot.id,
                models.TeamsNetwinLog.msg_id == msg_id).first():
            logger.info(f"[Teams {bot.id}] 查輸贏：訊息 {msg_id} 已處理過，略過")
            return

        mode = bot.netwin_mode or "full"
        account = extract_account(text)
        src = None
        if bot.netwin_source_bot_id:
            src = db.query(models.TelegramBot).filter(models.TelegramBot.id == bot.netwin_source_bot_id).first()

        log = models.TeamsNetwinLog(bot_id=bot.id, chat_id=chat_id, chat_name=chat_name, msg_id=msg_id,
                                    sender=sender_name, extracted_account=account, outcome="querying")
        if mode == "log_only":
            log.outcome = "log_only"
        elif not account:
            log.outcome = "no_account"
        elif not (src and src.netwin_key_id and src.netwin_api_key and src.netwin_api_base_url
                  and src.netwin_rtp_threshold is not None):
            # 同 Telegram：RTP 門檻或憑證沒設定齊全時兩個 API 都不呼叫，不自己猜門檻
            logger.warning(f"[Teams {bot.id}] 查輸贏已開啟但共用的 Telegram 機器人尚未設定 API 憑證或 RTP 門檻")
            log.outcome = "api_error"
        db.add(log)
        try:
            db.commit()
        except Exception as e:  # noqa: BLE001
            logger.error(f"[Teams {bot.id}] 儲存查輸贏 log 失敗：{e}")
            db.rollback()
            return
        logger.info(f"[Teams {bot.id}] 查輸贏 [{chat_name}] 帳號={account} 模式={mode} → {log.outcome}")
        if log.outcome != "querying":
            return

        cfg = {
            "base_url": src.netwin_api_base_url, "key_id": src.netwin_key_id, "api_key": src.netwin_api_key,
            "threshold": src.netwin_threshold if src.netwin_threshold is not None else 5000,
            "rtp_threshold": src.netwin_rtp_threshold,
            "delay": src.netwin_reply_delay_seconds if src.netwin_reply_delay_seconds is not None else 30,
            "reply_zh": src.netwin_reply_zh, "reply_en": src.netwin_reply_en,
        }
        threading.Thread(target=_netwin_worker, name=f"teams-netwin-{bot.id}-{msg_id}", daemon=True,
                         args=(bot.id, log.id, cfg, account, chat_id, chat_name, m, text)).start()


# ================================================================ Watcher 管理
_watchers: dict[int, TeamsWatcher] = {}
_watchers_lock = threading.Lock()


def start_watcher(bot_id: int, refresh_token: str):
    with _watchers_lock:
        w = _watchers.get(bot_id)
        if w and w.is_alive():
            return
        w = TeamsWatcher(bot_id, refresh_token)
        _watchers[bot_id] = w
        w.start()


def stop_watcher(bot_id: int):
    with _watchers_lock:
        w = _watchers.pop(bot_id, None)
    if w:
        w.stop()


def restart_watcher(bot_id: int, refresh_token: str):
    stop_watcher(bot_id)
    start_watcher(bot_id, refresh_token)


def is_watcher_running(bot_id: int) -> bool:
    w = _watchers.get(bot_id)
    return bool(w and w.is_alive())


# ================================================================ 查輸贏回覆（背景 worker）
def _evaluate_netwin(cfg: dict, account: str) -> tuple[str, dict]:
    """判斷樹與 Telegram 完全相同（outcome 值也相同，兩邊統計口徑一致）。回傳 (outcome, 要寫進 log 的欄位)。"""
    from services.tjadmin_service import query_player_by_name, query_player_rtp

    rows, err = query_player_by_name(cfg["base_url"], cfg["key_id"], cfg["api_key"], account)
    if err is not None:
        logger.error(f"[Teams] 查輸贏 API 呼叫失敗（帳號={account}）：{err}")
        return "api_error", {}
    if len(rows) == 0:
        return "zero_match", {"match_count": 0}
    if len(rows) > 1:
        return "multi_match", {"match_count": len(rows)}
    netwin = rows[0].get("netwin_2d_thb")
    fields = {"match_count": 1, "netwin_2d_thb": netwin}
    if netwin is None:
        return "null_netwin", fields
    if netwin == 0:                     # 近2日沒有遊玩紀錄，不代表輸贏正常
        return "zero_netwin", fields
    if netwin >= cfg["threshold"]:
        return "over_threshold", fields
    aid = rows[0].get("aid")
    if aid is None:
        logger.error(f"[Teams] 查輸贏：API 1 回應缺少 aid 欄位（帳號={account}）")
        return "rtp_error", fields
    summary, err = query_player_rtp(cfg["base_url"], cfg["key_id"], cfg["api_key"], aid)
    if err is not None:
        logger.error(f"[Teams] 查輸贏 RTP API 呼叫失敗（aid={aid}）：{err}")
        return "rtp_error", fields
    rtp = (summary or {}).get("rtp")
    fields["rtp"] = rtp
    if rtp is None:                     # 近7日無下注紀錄
        return "rtp_null", fields
    if rtp < cfg["rtp_threshold"]:
        return "auto_replied", fields
    return "over_rtp_threshold", fields


def _netwin_worker(bot_id: int, log_id: int, cfg: dict, account: str,
                   chat_id: str, chat_name: str, m: dict, text: str):
    """查 API（兩支各最多 30 秒）→ 判斷門檻 → 延遲回覆。獨立 thread 執行，不能放在輪詢 thread 裡，
    否則這個帳號所有群組的輪詢都會被卡住；多筆查輸贏各自倒數、互不影響。"""
    import models
    from database import SessionLocal
    from services.telegram_service import _create_freshdesk_ticket_bg

    try:
        outcome, fields = _evaluate_netwin(cfg, account)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[Teams {bot_id}] 查輸贏例外（帳號={account}）：{e}", exc_info=True)
        outcome, fields = "api_error", {}

    db = SessionLocal()
    try:
        log = db.query(models.TeamsNetwinLog).filter(models.TeamsNetwinLog.id == log_id).first()
        if not log:
            return
        log.outcome = outcome
        for k, v in fields.items():
            setattr(log, k, v)
        db.commit()
        logger.info(f"[Teams {bot_id}] 查輸贏 [{chat_name}] 帳號={account} → {outcome} {fields}")
        if outcome != "auto_replied":
            return                                  # 沒有結果或超過門檻：靜默，只留紀錄

        is_zh = bool(re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
        reply = cfg["reply_zh"] if is_zh else cfg["reply_en"]
        if not reply:
            logger.warning(f"[Teams {bot_id}] 查輸贏符合門檻，但共用的 Telegram 機器人未設定"
                           f"{'中文' if is_zh else '英文'}回覆內容，不回覆")
            return
        bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
        if not bot or (bot.netwin_mode or "full") != "full":
            return
    finally:
        db.close()

    # 刻意延遲再回覆，避免速度過快讓廠商懷疑沒有真的去查（秒數沿用 Telegram 機器人設定）
    if cfg["delay"] and cfg["delay"] > 0:
        time.sleep(cfg["delay"])

    db = SessionLocal()
    try:
        # 倒數期間設定可能被改：重新確認帳號、功能、模式、該群開關都還開著才送出
        bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
        setting = db.query(models.TeamsGroupSetting).filter(
            models.TeamsGroupSetting.bot_id == bot_id, models.TeamsGroupSetting.chat_id == chat_id).first()
        if not (bot and bot.is_enabled and bot.netwin_query_enabled and (bot.netwin_mode or "full") == "full"
                and setting and setting.netwin_enabled):
            logger.info(f"[Teams {bot_id}] 查輸贏：倒數期間功能已關閉，取消回覆（帳號={account}）")
            return
        # 用「目前正在跑的 watcher」的 client 發送：共用同一個速率桶，也避免 watcher 重啟後
        # 拿舊 client 的 refresh token 去續期（滾動更新會互踢）
        w = _watchers.get(bot_id)
        if not (w and w.is_alive()):
            logger.warning(f"[Teams {bot_id}] 查輸贏：watcher 未運行，取消回覆（帳號={account}）")
            return
        try:
            w.client.send_reply(chat_id, m, reply)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[Teams {bot_id}] 查輸贏回覆失敗：{e}", exc_info=True)
            return
        logger.info(f"[Teams {bot_id}] 查輸贏已回覆 [{chat_name}] 帳號={account}")
        log = db.query(models.TeamsNetwinLog).filter(models.TeamsNetwinLog.id == log_id).first()
        if log:
            log.reply_sent = True
            db.commit()
        _record_teams_group_stat(bot_id, chat_id, chat_name, db)
        if setting.ticket_creation_enabled is not False:
            threading.Thread(target=_create_freshdesk_ticket_bg,
                             args=(text, reply, chat_name), daemon=True).start()
    except Exception as e:  # noqa: BLE001
        logger.error(f"[Teams {bot_id}] 查輸贏回覆後續處理失敗：{e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def start_all_enabled_watchers():
    import models
    from database import SessionLocal
    db = SessionLocal()
    try:
        bots = db.query(models.TeamsBot).filter(models.TeamsBot.is_enabled == True).all()  # noqa: E712
        for bot in bots:
            if not bot.refresh_token:
                logger.info(f"[Teams {bot.id}] 尚未登入，略過")
                continue
            try:
                start_watcher(bot.id, bot.refresh_token)
            except Exception as e:  # noqa: BLE001
                logger.error(f"啟動 Teams watcher {bot.id} 失敗：{e}")
    finally:
        db.close()


def list_groups_live(bot) -> list:
    """給管理頁用：即時列出帳號所在的群組（吃 1 次額度）。watcher 在跑就借它的 client，否則臨時建一個。"""
    w = _watchers.get(bot.id)
    client = w.client if (w and w.is_alive()) else TeamsAccountClient(bot.id, bot.refresh_token, persist_refresh_token)
    convs = client.fetch_conversations()
    out = []
    for c in convs:
        cid = c.get("id", "")
        props = c.get("threadProperties") or {}
        if not cid.startswith("19:") or (props.get("threadType") or "").lower() != "chat":
            continue
        topic = html.unescape((props.get("topic") or "").strip())
        last = c.get("lastMessage") or {}
        out.append({
            "chat_id": cid,
            "chat_name": topic if topic and not topic.startswith("19:") else cid,
            "last_message_at": last.get("originalarrivaltime"),
            "last_message_preview": clean_text(last.get("content"))[:60],
        })
    return out
