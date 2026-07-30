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

# 內部後台系統網址（逗號分隔，可設定多個），訊息中出現即視為強烈的「後台白名單」信號。
# 未設定（空字串）時規則三完全不啟用，不影響既有規則一/規則二的判斷。
_ADMIN_DOMAINS = [
    d.strip().lower() for d in os.getenv("WHITELIST_ADMIN_DOMAINS", "").split(",") if d.strip()
]

_BO_KEYWORDS = [
    "whitelist bo ip", "bo ip", "backend ip", "whitelist bo",
    "加白后台ip", "加白后台", "後台ip",
    "加白後台", "whitelist backend",
    "backoffice ip whitelist", "backoffice ip", "backoffice whitelist",
    "后台過白", "后台过白", "後台白名單",
]
_API_EXCLUDE = ["api ip", "api whitelist", "加白api", "api white", "apiip"]
_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

# 寬鬆規則：白名單 + 後台 + IP 三個概念各自出現（不需相鄰／連續字串），繁簡中文＋英文皆適用
_WHITELIST_WORDS = ["白名單", "白名单", "whitelist"]
_BACKEND_WORDS = ["後台", "后台", "backend", "backoffice", "kiosk"]
# "bo" 為 backoffice 常見縮寫，僅 2 個字母不能用一般子字串比對（會誤判 about/box/labor 等字），
# 改用單字邊界比對，確保只匹配獨立出現的 "bo"（前後為空白/標點或字串起訖）
_BO_ABBR_RE = re.compile(r'\bbo\b', re.IGNORECASE)


def _has_backend_indicator(text: str, lower: str) -> bool:
    return any(w in lower for w in _BACKEND_WORDS) or bool(_BO_ABBR_RE.search(text))

# 疑問句型態排除：避免「單純在詢問流程/現況」的訊息被寬鬆規則誤判為提交申請
_QUESTION_MARKERS_CJK = [
    "？", "怎麼", "怎么", "如何", "流程", "查一下", "查下", "查詢一下", "查询一下",
    "能否", "可以嗎", "可以吗", "是不是", "有沒有", "有没有", "請問", "请问",
    "麻煩問", "麻烦问", "幫忙查", "帮忙查",
]
_QUESTION_MARKERS_EN = [
    "?", "how to", "how do i", "how can i", "could you check", "can you check",
    "please check", "would like to know",
]


def _looks_like_question(text: str) -> bool:
    lower = text.lower()
    if any(m in text for m in _QUESTION_MARKERS_CJK):
        return True
    if any(m in lower for m in _QUESTION_MARKERS_EN):
        return True
    return False


def detect_whitelist_request(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in _API_EXCLUDE):
        return False

    has_ip = bool(_IP_RE.search(text))
    if not has_ip:
        return False

    # 規則一：既有的連續詞組比對（優先，較嚴謹）
    if any(kw in lower for kw in _BO_KEYWORDS):
        return True

    # 規則二：白名單 + 後台 三個概念各自出現即可（不需相鄰），但排除疑問句型態
    if (any(w in lower for w in _WHITELIST_WORDS)
            and _has_backend_indicator(text, lower)
            and not _looks_like_question(text)):
        return True

    # 規則三：訊息含內部後台系統網址（環境變數 WHITELIST_ADMIN_DOMAINS 設定時才啟用）。
    # 網址本身辨識度已足夠高，不需再額外要求「白名單」字樣同時出現；仍排除疑問句型態。
    if _ADMIN_DOMAINS and any(d in lower for d in _ADMIN_DOMAINS) and not _looks_like_question(text):
        return True

    return False


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
    else:
        # 無法辨識的標籤格式：逐行掃描
        # 1. 「任意標籤 : 帳號」格式（標籤打錯字，如 USWER、Usre 等，仍容錯解析冒號後的值）
        # 2. 單獨一行、看起來像帳號的行（純英數字加底線/破折號，不含空白）
        _skip_phrases = set(_BO_KEYWORDS) | set(_API_EXCLUDE) | set(_WHITELIST_WORDS) | set(_BACKEND_WORDS)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if _IP_RE.search(line):
                break
            if line.lower() in _skip_phrases:
                continue
            if _TOKEN_RE.match(line):
                all_usernames.append(line)
                continue
            if "：" in line or ":" in line:
                value = re.split(r'[：:]', line, maxsplit=1)[1].strip()
                if _TOKEN_RE.match(value):
                    all_usernames.append(value)

    all_parts = []
    for u in all_usernames:
        parts = [p for p in re.split(r'[_\-]', u) if p]
        if parts:
            all_parts.append(parts)

    vendor_code = all_parts[0][0].upper() if all_parts else None
    ips = _IP_RE.findall(text)
    return vendor_code, all_parts, ips


def run_whitelist_sync(username_parts: list[str], ips: list[str], allowed_vendor_prefixes: list[str] = None,
                       forced_vendor_name: str = None) -> tuple[bool, Optional[str], bool]:
    """同步 HTTP 流程，直接在 asyncio.to_thread 的執行緒中執行

    forced_vendor_name：指定時代表「單一總代理」群組模式（訊息沒有帳號，只有 IP+關鍵字），
    跳過帳號比對邏輯，直接以此名稱精確比對（忽略大小寫）廠商清單。
    """
    logger.info(f"[Whitelist] 開始（HTTP 模式）：username_parts={username_parts}, IPs={ips}, forced_vendor_name={forced_vendor_name}")

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

            matched_id = None
            matched_name = None

            if forced_vendor_name:
                # ── 單一總代理模式：跳過帳號比對，直接精確比對廠商名稱（忽略大小寫）──
                exact_matches = [
                    (api_id, name) for api_id, name in all_vendors
                    if name.strip().upper() == forced_vendor_name.strip().upper()
                ]
                logger.info(f"[Whitelist] 單一總代理模式：目標='{forced_vendor_name}'，找到 {len(exact_matches)} 筆")
                if len(exact_matches) == 1:
                    matched_id, matched_name = exact_matches[0]
                    logger.info(f"[Whitelist] 單一總代理模式匹配：id={matched_id}, name={matched_name}")
                else:
                    logger.error(f"[Whitelist] 單一總代理模式無法確定廠商 '{forced_vendor_name}'（{len(exact_matches)} 筆），中止")
            else:
                # ── Step 4：逐段比對廠商名稱 ──────────────────────
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
                    else:
                        # 候選 ≥2 筆：嘗試 Transfer / Seamless 消歧（同品牌前綴僅差這兩條線，
                        # 依帳號段數判斷：3 段（含幣別）視為 Transfer，2 段視為 Seamless）
                        suffixes = {name.upper()[len(prefix):].lstrip('_-') for _, name in candidates}
                        if suffixes == {"TRANSFER", "SEAMLESS"}:
                            seg_count = len(username_parts)
                            target_suffix = "TRANSFER" if seg_count >= 3 else ("SEAMLESS" if seg_count == 2 else None)
                            if target_suffix:
                                pick = next((c for c in candidates if c[1].upper().endswith(target_suffix)), None)
                                if pick:
                                    matched_id, matched_name = pick
                                    logger.info(
                                        f"[Whitelist] Transfer/Seamless 消歧：帳號共 {seg_count} 段 → 判定為 {matched_name}"
                                    )
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

                # ── Step 4c-2：廠商名稱後綴比對（帳號第一段是廠商名稱的結尾，
                # 兩者間無底線/破折號分隔時適用，例如帳號 "TR1_xxx" 對應廠商 "TitanTR1"）──
                if not matched_id:
                    first_seg = username_parts[0].upper()
                    suffix_matches = [
                        (api_id, name)
                        for api_id, name in all_vendors
                        if name.upper().endswith(first_seg) and len(name) > len(first_seg)
                    ]
                    logger.info(f"[Whitelist] Step4c-2 後綴比對：first_seg='{first_seg}'，候選={[n for _, n in suffix_matches]}")
                    if len(suffix_matches) == 1:
                        matched_id, matched_name = suffix_matches[0]
                        logger.info(f"[Whitelist] Step4c-2 唯一匹配：id={matched_id}, name={matched_name}")
                    elif len(suffix_matches) > 1:
                        logger.error(f"[Whitelist] Step4c-2 後綴比對有歧義（{[n for _, n in suffix_matches]}），中止")

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
