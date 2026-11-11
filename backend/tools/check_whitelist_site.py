"""驗證「新後台（tj-report）白名單」流程能否走通（由人工在本機執行，會連線真實後台）。

用法（在 backend 目錄、用專案的 venv 執行）：
    venv\\Scripts\\python.exe tools\\check_whitelist_site.py            # 只檢查：登入 + 取廠商清單 + 確認測試廠商存在
    venv\\Scripts\\python.exe tools\\check_whitelist_site.py --add 192.0.2.1
                                                                      # 實際對測試廠商 WinBet_1 新增一筆 IP（會真的寫入後台，
                                                                      # 請用不影響任何人的 IP，驗完到後台手動刪除）

站點、帳號、密碼讀 whitelist_service.NEW_SITE（預設值或環境變數 WHITELIST_NEW_SITE_*），
腳本不會把密碼印出來。若某一步失敗，輸出會指出是哪一步（登入頁／登入／取清單／新增），
把輸出貼回來即可判斷新站與舊站流程哪裡不同。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import httpx  # noqa: E402

from services import whitelist_service as w  # noqa: E402

TEST_VENDOR = "WinBet_1"


def check(site: dict) -> bool:
    print(f"站點：{site['base']}（帳號 {site['user']}）")
    with httpx.Client(base_url=site["base"], follow_redirects=True, timeout=60) as client:
        r = client.get(site["login_page"])
        print(f"[1] GET {site['login_page']} → {r.status_code}")
        r = client.post(site["do_login"], data={"account": site["user"], "password": site["password"], "rememberMe": "0"})
        print(f"[2] POST {site['do_login']} → {r.status_code}")
        try:
            body = r.json()
        except Exception:
            print("    登入回應不是 JSON，前 200 字：", r.text[:200].replace("\n", " "))
            return False
        err = body.get("response", {}).get("error", -1)
        print(f"    登入結果 error={err}" + ("" if err == 0 else f"，訊息：{str(body)[:200]}"))
        if err != 0:
            return False
        r = client.post(site["init"], data={"action": "init"}, headers={
            "X-Requested-With": "XMLHttpRequest", "Referer": f"{site['base']}{site['referer']}"})
        print(f"[3] POST {site['init']} → {r.status_code}，{len(r.content)} bytes")
        vendors = []
        for mv in re.finditer(r'"(\d+)":\{"id":\1[,}]', r.text):
            nm = re.search(r'"name":"([^"]*)"', r.text[mv.start(): mv.start() + 300])
            if nm:
                vendors.append((mv.group(1), nm.group(1)))
        print(f"    解析到廠商數：{len(vendors)}，前 3 筆：{vendors[:3]}")
        if not vendors:
            print("    廠商清單解析失敗，回應前 300 字：", r.text[:300].replace("\n", " "))
            return False
        hit = [v for v in vendors if v[1].upper() == TEST_VENDOR.upper()]
        print(f"    測試廠商 {TEST_VENDOR}：{'找到 ' + str(hit[0]) if hit else '找不到'}")
        return bool(hit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", metavar="IP", help="實際對測試廠商新增這個 IP（會寫入後台）")
    args = ap.parse_args()
    ok = check(w.NEW_SITE)
    if not ok:
        print("結果：檢查未通過")
        sys.exit(1)
    if args.add:
        print(f"[4] 對 {TEST_VENDOR} 新增 IP {args.add} …")
        success, vendor, rejected = w.run_whitelist_sync_new(TEST_VENDOR.split("_"), [args.add])
        print(f"    結果：success={success}, vendor={vendor}, rejected={rejected}")
        sys.exit(0 if success else 1)
    print("結果：檢查通過（登入、取清單、測試廠商皆正常）；要驗證新增請加上 --add <IP>")


if __name__ == "__main__":
    main()
