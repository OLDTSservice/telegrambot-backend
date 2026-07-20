"""
後台白名單自動處理服務
使用同步 httpx.Client 直接呼叫後台 API，在 asyncio.to_thread 執行緒中執行。
"""
import re
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SITE_BASE = os.getenv("WHITELIST_SITE_BASE", "https://wb-api4.jlfafafa3.com")
SITE_USER = os.getenv("WHITELIST_SITE_USER", "TESTwhitelist")
SITE_PASS = os.getenv("WHITELIST_SITE_PASS", "Igs22995048")

_BO_KEYWORDS = [
    "whitelist bo ip", "bo ip", "backend ip", "whitelist bo",
    "加白后台ip", "加白后台", "後台ip",
    "加白後台", "whitelist backend",
    "backoffice ip whitelist", "backoffice ip",
]
_API_EXCLUDE = ["api ip", "api whitelist", "加白api", "api white", "apiip"]
_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def detect_whitelist_request(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in _API_EXCLUDE):
        return False
    return any(kw in lower for kw in _BO_KEYWORDS) and bool(_IP_RE.search(text))


def parse_whitelist_request(text: str) -> tuple[Optional[str], list[list[str]], list[str]]:
    """
    回傳 (vendor_code, list_of_username_parts, ip_list)
    list_of_username_parts 可能含多組（訊息內多個代理帳號）
    """
    _USERNAME_RE = re.compile(
        r'(?:Username|代理[帐账]号|User(?:name)?|后台帐号|帳號|后台账号|ID)\s*[：:]\s*([A-Za-z0-9_\-]+)',
        re.IGNORECASE
    )
    _TOKEN_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_\-]{3,}$')

    all_usernames: list[str] = []

    m = _USERNAME_RE.search(text)
    if m:
        all_usernames.append(m.group(1).strip())
        # 找 label 之後的行，若像帳號格式（英數底線）也納入
        rest = text[m.end():]
        for line in rest.splitlines():
            line = line.strip()
            if not line:
                continue
            # 遇到 IP 行或關鍵字行就停止
            if _IP_RE.search(line):
                break
            if _TOKEN_RE.match(line):
                all_usernames.append(line)

    all_parts = []
    for u in all_usernames:
        parts = [p for p in re.split(r'[_\-]', u) if p]
        if parts:
            all_parts.append(parts)

    vendor_code = all_parts[0][0].upper() if all_parts else None
    ips = _IP_RE.findall(text)
    return vendor_code, all_parts, ips


def run_whitelist_sync(username_parts: list[str], ips: list[str], allowed_vendor_prefixes: list[str] = None) -> tuple[bool, Optional[str], bool]:
    """同步 HTTP 流程，直接在 asyncio.to_thread 的執行緒中執行"""
    logger.info(f"[Whitelist] 開始（HTTP 模式）：username_parts={username_parts}, IPs={ips}")

    with httpx.Client(base_url=SITE_BASE, follow_redirects=True, timeout=60) as client:
        try:
            # ── Step 1：GET 登入頁取得 session cookie ─────────
            client.get("/login")
            logger.info(f"[Whitelist] 已取得 session，cookies={dict(client.cookies)}")

            # ── Step 2：POST /do-login（不需 reCAPTCHA）───────
            login_r = client.post("/do-login", data={
                "account": SITE_USER,
                "password": SITE_PASS,
                "rememberMe": "0",
            })
            login_json = login_r.json()
            logger.info(f"[Whitelist] 登入回應：{str(login_json)[:200]}")

            if login_json.get("response", {}).get("error", -1) != 0:
                logger.error(f"[Whitelist] 登入失敗：{login_json}")
                return False, None, False
            logger.info("[Whitelist] 登入成功")

            # ── Step 3：取廠商清單 ────────────────────────────
            init_r = client.post(
                "/admin/maintenance/controller/WhiteListController",
                data={"action": "init"},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{SITE_BASE}/admin/maintenance/white-list-ip-setting",
                },
            )
            logger.info(f"[Whitelist] WhiteListController status={init_r.status_code}, size={len(init_r.content)}")

            # 6MB+ JSON，用 regex 萃取廠商 id/name（外層 key == 內層 id 值）
            vendor_start_re = re.compile(r'"(\d+)":\{"id":\1[,}]')
            name_re_inner = re.compile(r'"name":"([^"]*)"')
            all_vendors = []
            text = init_r.text
            for mv in vendor_start_re.finditer(text):
                segment = text[mv.start(): mv.start() + 300]
                nm = name_re_inner.search(segment)
                if nm:
                    all_vendors.append((mv.group(1), nm.group(1)))
            logger.info(f"[Whitelist] 解析到廠商數：{len(all_vendors)}，前3筆：{all_vendors[:3]}")

            if not all_vendors:
                logger.error(f"[Whitelist] 廠商清單解析失敗，前300字：{init_r.text[:300]}")
                return False, None, False

            # ── Step 4：逐段比對廠商名稱 ──────────────────────
            matched_id = None
            matched_name = None
            full_username = '_'.join(username_parts).upper()
            prev_candidates = []

            for i in range(1, len(username_parts) + 1):
                prefix = '_'.join(username_parts[:i]).upper()
                candidates = [
                    (api_id, name)
                    for api_id, name in all_vendors
                    if name.upper() == prefix or name.upper().startswith(prefix + '_')
                ]
                logger.info(f"[Whitelist] 前綴 '{prefix}'：找到 {len(candidates)} 筆")

                if len(candidates) == 1:
                    matched_id, matched_name = candidates[0]
                    logger.info(f"[Whitelist] 唯一匹配：id={matched_id}, name={matched_name}")
                    break
                elif len(candidates) == 0:
                    # fallback：從上一輪候選中篩選完整帳號以該廠商名稱為前綴的
                    fallback = [
                        (api_id, name)
                        for api_id, name in prev_candidates
                        if full_username == name.upper() or full_username.startswith(name.upper() + '_')
                    ]
                    logger.info(f"[Whitelist] 前綴 '{prefix}' 無匹配，fallback 候選：{[(n) for _, n in fallback]}")
                    if len(fallback) == 1:
                        matched_id, matched_name = fallback[0]
                        logger.info(f"[Whitelist] Fallback 唯一匹配：id={matched_id}, name={matched_name}")
                    else:
                        logger.error(f"[Whitelist] Fallback 無法確定廠商（{len(fallback)} 筆），中止")
                    break
                prev_candidates = candidates

            # ── Step 4b：第二層 fallback — 廠商名稱為帳號第一段的前綴（取最長匹配）
            if not matched_id:
                first_segment = username_parts[0].upper()
                prefix_matches = [
                    (api_id, name)
                    for api_id, name in all_vendors
                    if first_segment.startswith(name.upper()) and len(name) > 1
                ]
                if prefix_matches:
                    # 取廠商名稱最長的那一筆（最精確）
                    best = max(prefix_matches, key=lambda x: len(x[1]))
                    # 確認沒有其他同長度的競爭者
                    best_len = len(best[1])
                    same_len = [x for x in prefix_matches if len(x[1]) == best_len]
                    logger.info(f"[Whitelist] 第二層 fallback：第一段='{first_segment}'，候選={[(n) for _, n in prefix_matches]}，最長={best[1]}")
                    if len(same_len) == 1:
                        matched_id, matched_name = best
                        logger.info(f"[Whitelist] 第二層 fallback 匹配：id={matched_id}, name={matched_name}")
                    else:
                        logger.error(f"[Whitelist] 第二層 fallback 最長匹配有歧義（{[n for _, n in same_len]}），中止")
                else:
                    logger.error(f"[Whitelist] 廠商無法確定，前10筆：{all_vendors[:10]}")

            # ── Step 4c：廠商名稱各段中是否有任一段等於帳號第一段 ──────────
            if not matched_id:
                first_seg = username_parts[0].upper()
                segment_matches = [
                    (api_id, name)
                    for api_id, name in all_vendors
                    if first_seg in [s.upper() for s in re.split(r'[_\-]', name)]
                ]
                logger.info(f"[Whitelist] Step4c 段落比對：first_seg='{first_seg}'，候選={[n for _, n in segment_matches]}")
                if len(segment_matches) == 1:
                    matched_id, matched_name = segment_matches[0]
                    logger.info(f"[Whitelist] Step4c 唯一匹配：id={matched_id}, name={matched_name}")
                elif len(segment_matches) > 1:
                    best = max(segment_matches, key=lambda x: len(x[1]))
                    same_len = [x for x in segment_matches if len(x[1]) == len(best[1])]
                    if len(same_len) == 1:
                        matched_id, matched_name = best
                        logger.info(f"[Whitelist] Step4c 最長匹配：id={matched_id}, name={matched_name}")
                    else:
                        logger.error(f"[Whitelist] Step4c 歧義（{[n for _, n in same_len]}），中止")

            if not matched_id:
                return False, None, False

            # ── Step 4d：群組廠商白名單驗證 ──────────────────────────────
            # 使用分隔符號感知比對：前綴 P 允許廠商名稱 == P、P_* 或 P-*
            # 避免 "ON9" 誤放行 "On9gaming"（沒有分隔符號，屬於不同廠商）
            def _vendor_matches(vendor_upper: str, prefix_upper: str) -> bool:
                return (
                    vendor_upper == prefix_upper
                    or vendor_upper.startswith(prefix_upper + '_')
                    or vendor_upper.startswith(prefix_upper + '-')
                )

            if allowed_vendor_prefixes:
                upper_name = matched_name.upper()
                if not any(_vendor_matches(upper_name, p.strip().upper()) for p in allowed_vendor_prefixes):
                    logger.warning(f"[Whitelist] 廠商 '{matched_name}' 不在群組允許清單 {allowed_vendor_prefixes}，拒絕")
                    return False, None, True
                logger.info(f"[Whitelist] 廠商驗證通過：'{matched_name}' 符合允許清單")

            # ── Step 5：新增白名單 ────────────────────────────
            import urllib.parse
            form_list = [("form[type][]", "10"), ("form[apiId][]", matched_id)]
            for ip in ips:
                form_list.append(("form[ip][]", ip))

            save_r = client.post(
                "/admin/maintenance/white-list-ip-settingForm",
                content=urllib.parse.urlencode(form_list).encode(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            save_json = save_r.json()
            logger.info(f"[Whitelist] 儲存回應：{str(save_json)[:300]}")

            error_code = save_json.get("response", {}).get("error", save_json.get("error", 1))
            if error_code != 0:
                msg = save_json.get("response", {}).get("message", save_json.get("msg", "unknown"))
                logger.error(f"[Whitelist] 新增失敗：{msg}")
                return False, None, False

            logger.info(f"[Whitelist] 新增成功：廠商={matched_name}, IPs={ips}")
            return True, matched_name, False

        except Exception as e:
            logger.error(f"[Whitelist] 例外：{e}", exc_info=True)
            return False, None, False
