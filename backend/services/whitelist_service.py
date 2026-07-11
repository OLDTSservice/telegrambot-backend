"""
後台白名單自動處理服務
- 偵測 Telegram 群組訊息中的後台 IP 白名單請求
- 解析廠商代碼（Username 各段）與 IP 列表
- 直接呼叫後台 API（/do-login → /getNewAPISiteIdMapping → /white-list-ip-settingForm）
  完全不使用 Playwright，記憶體需求極低
"""
import re
import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SITE_BASE  = os.getenv("WHITELIST_SITE_BASE", "https://wb-api4.jlfafafa3.com")
SITE_USER  = os.getenv("WHITELIST_SITE_USER", "TESTwhitelist")
SITE_PASS  = os.getenv("WHITELIST_SITE_PASS", "Igs22995048")

_BO_KEYWORDS = [
    "whitelist bo ip", "bo ip", "backend ip", "whitelist bo",
    "加白后台ip", "加白后台", "白名单ip", "後台ip", "白名單ip",
    "加白後台", "whitelist backend",
]
_API_EXCLUDE = ["api ip", "api whitelist", "加白api", "api white", "apiip"]
_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def detect_whitelist_request(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in _API_EXCLUDE):
        return False
    return any(kw in lower for kw in _BO_KEYWORDS) and bool(_IP_RE.search(text))


def parse_whitelist_request(text: str) -> tuple[Optional[str], list[str], list[str]]:
    """回傳 (vendor_code, username_parts, ip_list)"""
    vendor_code = None
    username_parts: list[str] = []

    m = re.search(
        r'(?:Username|代理[帐账]号|User(?:name)?|后台帐号|帳號|后台账号|ID)\s*[：:]\s*([A-Za-z0-9_\-]+)',
        text, re.IGNORECASE
    )
    if m:
        username = m.group(1).strip()
        username_parts = [p for p in re.split(r'[_\-]', username) if p]
        if username_parts:
            vendor_code = username_parts[0].upper()

    ips = _IP_RE.findall(text)
    return vendor_code, username_parts, ips


def run_whitelist_sync(username_parts: list[str], ips: list[str]) -> tuple[bool, Optional[str]]:
    return asyncio.run(_do_add_whitelist(username_parts, ips))


async def _do_add_whitelist(username_parts: list[str], ips: list[str]) -> tuple[bool, Optional[str]]:
    """純 HTTP 流程（不開瀏覽器），回傳 (成功與否, 匹配到的廠商名稱)"""
    logger.info(f"[Whitelist] 開始（HTTP 模式）：username_parts={username_parts}, IPs={ips}")

    async with httpx.AsyncClient(base_url=SITE_BASE, follow_redirects=True, timeout=30) as client:

        # ── Step 1：先 GET 登入頁面取得 session cookie ────────
        await client.get("/login")
        logger.info(f"[Whitelist] 已取得 session，cookies={dict(client.cookies)}")

        # ── Step 2：登入（/do-login 不需要 reCAPTCHA）─────────
        login_r = await client.post("/do-login", data={
            "account": SITE_USER,
            "password": SITE_PASS,
            "rememberMe": "0",
        })
        login_json = login_r.json()
        logger.info(f"[Whitelist] 登入回應：{str(login_json)[:200]}")
        logger.info(f"[Whitelist] 登入後 cookies={dict(client.cookies)}")

        if login_json.get("response", {}).get("error", -1) != 0:
            logger.error(f"[Whitelist] 登入失敗：{login_json}")
            return False, None
        logger.info("[Whitelist] 登入成功")

        # ── Step 2：取廠商清單（WhiteListController init）────
        # POST /controller/WhiteListController action=init
        # 回傳 response.apiIds：{id: {name, ...}, ...}
        init_r = await client.post(
            "/controller/WhiteListController",
            data={"action": "init"},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{SITE_BASE}/admin/maintenance/white-list-ip-setting",
            },
        )
        init_json = init_r.json()
        api_ids = init_json.get("response", {}).get("apiIds", {})
        logger.info(f"[Whitelist] 廠商清單筆數：{len(api_ids)}，前3筆：{list(api_ids.items())[:3]}")

        if not api_ids:
            logger.error(f"[Whitelist] 廠商清單為空，回應：{str(init_json)[:300]}")
            return False, None

        # ── Step 3：逐段比對廠商名稱 ─────────────────────────
        # api_ids[id]["name"] = 廠商名稱（如 "eswn"、"TitanTR1_SCFLY"）
        matched_id = None
        matched_name = None

        for i in range(1, len(username_parts) + 1):
            prefix = '_'.join(username_parts[:i]).upper()
            candidates = [
                (api_id, info["name"])
                for api_id, info in api_ids.items()
                if isinstance(info, dict) and (
                    info.get("name", "").upper() == prefix
                    or info.get("name", "").upper().startswith(prefix + '_')
                )
            ]
            logger.info(f"[Whitelist] 前綴 '{prefix}'：找到 {len(candidates)} 筆")

            if len(candidates) == 1:
                matched_id, matched_name = candidates[0]
                logger.info(f"[Whitelist] 唯一匹配：id={matched_id}, name={matched_name}")
                break
            elif len(candidates) == 0:
                logger.error(f"[Whitelist] 前綴 '{prefix}' 無匹配，中止")
                break

        if not matched_id:
            sample = [(k, v.get("name","")) for k,v in list(api_ids.items())[:10] if isinstance(v,dict)]
            logger.error(f"[Whitelist] 廠商無法確定，前10筆：{sample}")
            return False, None

        # ── Step 4：新增白名單 ───────────────────────────────
        form_data = {
            "form[type][]": "10",       # 後台登入白名單IP
            "form[apiId][]": matched_id,
        }
        for ip in ips:
            form_data.setdefault("form[ip][]", [])
            if isinstance(form_data["form[ip][]"], list):
                form_data["form[ip][]"].append(ip)
            else:
                form_data["form[ip][]"] = [form_data["form[ip][]"], ip]

        # httpx 多值 form 用 list of tuples
        form_list = [("form[type][]", "10"), ("form[apiId][]", matched_id)]
        for ip in ips:
            form_list.append(("form[ip][]", ip))

        save_r = await client.post(
            "/admin/maintenance/white-list-ip-settingForm",
            data=form_list,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        save_json = save_r.json()
        logger.info(f"[Whitelist] 儲存回應：{str(save_json)[:300]}")

        error_code = save_json.get("response", {}).get("error", save_json.get("error", 1))
        if error_code != 0:
            msg = save_json.get("response", {}).get("message", save_json.get("msg", "unknown"))
            logger.error(f"[Whitelist] 新增失敗：{msg}")
            return False, None

        logger.info(f"[Whitelist] 新增成功：廠商={matched_name}, IPs={ips}")
        return True, matched_name
