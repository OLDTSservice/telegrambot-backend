"""
後台白名單自動處理服務
- 偵測 Telegram 群組訊息中的後台 IP 白名單請求
- 解析廠商代碼（Username 第一段）與 IP 列表
- 使用 Playwright 登入目標網站並自動新增白名單
"""
import re
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SITE_URL   = os.getenv("WHITELIST_SITE_URL",  "https://wb-api4.jlfafafa3.com/admin/index")
SITE_USER  = os.getenv("WHITELIST_SITE_USER", "TESTwhitelist")
SITE_PASS  = os.getenv("WHITELIST_SITE_PASS", "Igs22995048")

# 後台 IP 關鍵字（只要含其中之一就觸發）
_BO_KEYWORDS = [
    "whitelist bo ip", "bo ip", "backend ip", "whitelist bo",
    "加白后台ip", "加白后台", "白名单ip", "後台ip", "白名單ip",
    "加白後台", "whitelist backend",
]
# 排除關鍵字（API IP 不處理）
_API_EXCLUDE = ["api ip", "api whitelist", "加白api", "api white", "apiip"]

_IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def detect_whitelist_request(text: str) -> bool:
    """判斷訊息是否為後台 BO IP 白名單請求"""
    lower = text.lower()
    if any(kw in lower for kw in _API_EXCLUDE):
        return False
    has_bo_kw = any(kw in lower for kw in _BO_KEYWORDS)
    has_ip = bool(_IP_RE.search(text))
    return has_bo_kw and has_ip


def parse_whitelist_request(text: str) -> tuple[Optional[str], list[str], list[str]]:
    """
    解析訊息，回傳 (vendor_code, username_parts, ip_list)
    - vendor_code:     第一段（供 log 顯示用）
    - username_parts:  所有分段（供逐段累加比對廠商名稱）
                       例：JK_ongcuci_MYR → ['JK', 'ongcuci', 'MYR']
                       例：TitanTR1_SCFLY_bk96_MYR → ['TitanTR1', 'SCFLY', 'bk96', 'MYR']
    - ip_list:         所有偵測到的 IP
    """
    vendor_code = None
    username_parts: list[str] = []

    username_m = re.search(
        r'(?:Username|代理[帐账]号|User(?:name)?|后台帐号|帳號|后台账号|ID)\s*[：:]\s*([A-Za-z0-9_\-]+)',
        text, re.IGNORECASE
    )
    if username_m:
        username = username_m.group(1).strip()
        username_parts = re.split(r'[_\-]', username)
        username_parts = [p for p in username_parts if p]
        if username_parts:
            vendor_code = username_parts[0].upper()

    ips = _IP_RE.findall(text)
    return vendor_code, username_parts, ips


def run_whitelist_sync(username_parts: list[str], ips: list[str]) -> tuple[bool, Optional[str]]:
    """同步包裝，供 asyncio.to_thread 呼叫，回傳 (成功與否, 最終匹配的廠商名稱)"""
    return asyncio.run(_do_add_whitelist(username_parts, ips))


async def _do_add_whitelist(username_parts: list[str], ips: list[str]) -> tuple[bool, Optional[str]]:
    """Playwright 自動化主流程，回傳 (成功與否, 最終匹配到的廠商名稱)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("[Whitelist] playwright 套件未安裝，請執行：playwright install chromium")
        return False, None

    import os as _os
    _os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/render/project/src/pw-browsers")

    ip_text = "\n".join(ips)
    logger.info(f"[Whitelist] 開始自動化：username_parts={username_parts}, IPs={ips}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page()
        page.set_default_timeout(20000)

        try:
            # ── Step 1：登入 ────────────────────────────────
            base = SITE_URL.rstrip('/').rsplit('/admin', 1)[0]
            login_url = base + '/admin/index'
            logger.info(f"[Whitelist] 開啟登入頁面 {login_url}")
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

            # 登入：直接呼叫 /do-login API（繞過 reCAPTCHA）
            # 網站登入按鈕需要 reCAPTCHA，但後端 /do-login 本身不驗 token
            login_api = base + '/do-login'
            login_resp = await page.request.post(
                login_api,
                form={"account": SITE_USER, "password": SITE_PASS, "rememberMe": "0"},
            )
            login_json = await login_resp.json()
            logger.info(f"[Whitelist] 登入 API 回應：{str(login_json)[:200]}")

            if login_json.get("response", {}).get("error", -1) != 0:
                logger.error(f"[Whitelist] 登入失敗：{login_json}")
                return False, None

            logger.info("[Whitelist] 登入成功")

            # ── Step 2：直接導航到白名單設定工具 ────────────
            wl_url = base + '/admin/maintenance/white-list-ip-setting'
            await page.goto(wl_url, wait_until="networkidle", timeout=20000)
            logger.info("[Whitelist] 已進入白名單設定工具")

            # ── Step 3：點選「新增」開啟表單 ─────────────────
            await page.locator('button:has-text("新增")').first.click()
            await page.wait_for_timeout(800)
            logger.info("[Whitelist] 已開啟新增表單")

            # ── Step 4：選擇類型 = 後台登入白名單IP（value=10）
            # 這是 Bootstrap selectpicker，用 JS 設值後觸發 change
            await page.evaluate(
                "() => { var s=document.getElementById('createType'); s.value='10'; $(s).selectpicker('refresh'); $(s).trigger('change'); }"
            )
            logger.info("[Whitelist] 類型已設為後台登入白名單IP")

            # ── Step 5：從 #createApiId 取所有選項並逐段比對廠商 ──
            # 選項格式：「數字_廠商名稱」，如「2182_eswn」
            # 比對策略：username 分段後以 _ 拼接前 i 段，在選項名稱（底線後）找含該字串者
            all_opts = await page.evaluate("""
                () => Array.from(document.getElementById('createApiId').options)
                     .filter(o => o.value)
                     .map(o => ({val: o.value, txt: o.text.trim()}))
            """)

            matched_value = None
            matched_text = None

            for i in range(1, len(username_parts) + 1):
                prefix = '_'.join(username_parts[:i]).upper()
                # 選項文字格式 "數字_XXX_YYY"，取底線後的部分做比對
                candidates = [
                    o for o in all_opts
                    if ('_' + prefix) in ('_' + o['txt'].upper().split('_', 1)[-1])
                ]
                logger.info(f"[Whitelist] 嘗試前綴 '{prefix}'，找到 {len(candidates)} 個候選")

                if len(candidates) == 1:
                    matched_text = candidates[0]['txt']
                    matched_value = candidates[0]['val']
                    logger.info(f"[Whitelist] 唯一匹配廠商：{matched_text}")
                    break
                elif len(candidates) == 0:
                    logger.error(f"[Whitelist] 前綴 '{prefix}' 無任何匹配，中止")
                    break

            if not matched_value:
                sample = [o['txt'] for o in all_opts[:20]]
                logger.error(f"[Whitelist] 廠商名稱無法確定，前20選項樣本：{sample}")
                return False, None

            # 用 JS 設定廠商選項並觸發 selectpicker 更新
            await page.evaluate(
                f"() => {{ var s=document.getElementById('createApiId'); s.value='{matched_value}'; $(s).selectpicker('refresh'); $(s).trigger('change'); }}"
            )
            logger.info(f"[Whitelist] 廠商已選：{matched_text}")

            # ── Step 6：填入 IP ──────────────────────────────
            await page.locator('textarea[placeholder*="IP"]').first.fill(ip_text)
            logger.info(f"[Whitelist] IP 已填入：{ips}")

            # ── Step 7：點選「儲存」 ─────────────────────────
            await page.locator('button:has-text("儲存")').first.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(800)
            logger.info(f"[Whitelist] 自動化完成：廠商={matched_text}, IPs={ips}")
            return True, matched_text

        except Exception as e:
            logger.error(f"[Whitelist] Playwright 步驟失敗：{e}", exc_info=True)
            try:
                await page.screenshot(path="/tmp/whitelist_error.png")
                logger.info("[Whitelist] 錯誤截圖已儲存至 /tmp/whitelist_error.png")
            except Exception:
                pass
            return False, None
        finally:
            await browser.close()
