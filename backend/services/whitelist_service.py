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


def parse_whitelist_request(text: str) -> tuple[Optional[str], list[str]]:
    """
    解析訊息，回傳 (vendor_code, ip_list)
    - vendor_code: Username 第一段（例：JK_ongcuci_MYR → JK）
    - ip_list: 所有偵測到的 IP
    """
    vendor_code = None
    username_m = re.search(
        r'(?:Username|代理[帐账]号|User(?:name)?|后台帐号|帳號|后台账号|ID)\s*[：:]\s*([A-Za-z0-9_\-]+)',
        text, re.IGNORECASE
    )
    if username_m:
        username = username_m.group(1).strip()
        parts = re.split(r'[_\-]', username)
        if parts and parts[0]:
            vendor_code = parts[0].upper()

    ips = _IP_RE.findall(text)
    return vendor_code, ips


def run_whitelist_sync(vendor_code: str, ips: list[str]) -> bool:
    """同步包裝，供 asyncio.to_thread 呼叫（在獨立 event loop 執行 Playwright）"""
    return asyncio.run(_do_add_whitelist(vendor_code, ips))


async def _do_add_whitelist(vendor_code: str, ips: list[str]) -> bool:
    """Playwright 自動化主流程"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("[Whitelist] playwright 套件未安裝，請執行：playwright install chromium --with-deps")
        return False

    ip_text = "\n".join(ips)
    logger.info(f"[Whitelist] 開始自動化：廠商={vendor_code}, IPs={ips}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page()
        page.set_default_timeout(20000)

        try:
            # ── Step 1：登入 ────────────────────────────────
            logger.info("[Whitelist] 開啟登入頁面")
            await page.goto(SITE_URL, wait_until="domcontentloaded", timeout=30000)

            # 填入帳號（嘗試多種 selector）
            await page.locator(
                'input[name="username"], input[name="account"], '
                'input[placeholder*="帳號"], input[placeholder*="账号"], '
                'input[placeholder*="Username"], input[type="text"]'
            ).first.fill(SITE_USER)

            await page.locator('input[type="password"]').first.fill(SITE_PASS)

            await page.locator(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("登入"), button:has-text("登录"), '
                'button:has-text("Login")'
            ).first.click()

            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info(f"[Whitelist] 登入完成，URL={page.url}")

            # ── Step 2：點選主選單「維護」 ──────────────────
            await page.locator(':text("維護"), :text("维护"), :text("Maintenance")').first.click()
            await page.wait_for_timeout(600)
            logger.info("[Whitelist] 已點選「維護」選單")

            # ── Step 3：點選「白名單設定工具」 ─────────────
            await page.locator(
                ':text("白名單設定工具"), :text("白名单设置工具"), '
                ':text("白名单"), :text("白名單")'
            ).first.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            logger.info("[Whitelist] 已進入白名單設定工具")

            # ── Step 4：點選右上角「新增」 ──────────────────
            await page.locator(
                'button:has-text("新增"), a:has-text("新增"), :text("新增")'
            ).first.click()
            await page.wait_for_timeout(800)
            logger.info("[Whitelist] 已開啟新增表單")

            # ── Step 5：選擇類型 = 後台登入白名單IP ─────────
            # 取得頁面中所有 <select>，第一個通常是類型
            selects = page.locator('select')
            count = await selects.count()
            logger.info(f"[Whitelist] 偵測到 {count} 個 <select> 元素")

            type_select = selects.nth(0)
            # 嘗試依 label 選取
            try:
                await type_select.select_option(label="後台登入白名單IP")
            except Exception:
                # 若失敗，嘗試 value 或文字包含
                options = await type_select.locator('option').all()
                for opt in options:
                    t = (await opt.inner_text()).strip()
                    if "後台" in t or "后台" in t or "BO" in t.upper():
                        v = await opt.get_attribute('value')
                        await type_select.select_option(value=v)
                        logger.info(f"[Whitelist] 類型已選：{t}")
                        break
            logger.info("[Whitelist] 類型選擇完成")

            # ── Step 6：選擇廠商名稱 ────────────────────────
            vendor_select = selects.nth(1)
            options = await vendor_select.locator('option').all()
            matched_value = None
            for opt in options:
                opt_text = (await opt.inner_text()).strip()
                if vendor_code.upper() in opt_text.upper():
                    matched_value = await opt.get_attribute('value')
                    logger.info(f"[Whitelist] 找到廠商選項：{opt_text} (value={matched_value})")
                    break

            if not matched_value:
                logger.error(f"[Whitelist] 找不到廠商 '{vendor_code}' 對應的選項，可用選項：")
                for opt in options:
                    logger.error(f"  - {(await opt.inner_text()).strip()}")
                return False

            await vendor_select.select_option(value=matched_value)
            logger.info(f"[Whitelist] 廠商已選：{vendor_code}")

            # ── Step 7：填入 IP ──────────────────────────────
            await page.locator('textarea').first.fill(ip_text)
            logger.info(f"[Whitelist] IP 已填入：{ips}")

            # ── Step 8：送出 ────────────────────────────────
            await page.locator(
                'button:has-text("確認"), button:has-text("送出"), '
                'button:has-text("確定"), button:has-text("保存"), '
                'button:has-text("Submit"), button[type="submit"]:not([style*="display:none"])'
            ).first.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(500)
            logger.info(f"[Whitelist] 自動化完成：廠商={vendor_code}, IPs={ips}")
            return True

        except Exception as e:
            logger.error(f"[Whitelist] Playwright 步驟失敗：{e}", exc_info=True)
            try:
                await page.screenshot(path="/tmp/whitelist_error.png")
                logger.info("[Whitelist] 錯誤截圖已儲存至 /tmp/whitelist_error.png")
            except Exception:
                pass
            return False
        finally:
            await browser.close()
