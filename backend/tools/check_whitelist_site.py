"""驗證「新後台（tj-report）白名單」流程能否走通（由人工在本機執行，會連線真實後台）。

在專案根目錄執行（PowerShell）：
    & ".\\backend\\venv\\Scripts\\python.exe" ".\\backend\\tools\\check_whitelist_site.py"
        只檢查：登入、取廠商清單、確認測試廠商存在、看該廠商目前的白名單設定（不寫入任何東西）
    & ".\\backend\\venv\\Scripts\\python.exe" ".\\backend\\tools\\check_whitelist_site.py" --add 192.0.2.1
        實際對測試廠商 WinBet_1 新增一筆 IP（會真的寫入後台，請用不影響任何人的 IP，驗完到後台手動刪除）

站點、帳號、密碼讀 whitelist_service 的 NEW_SITE_*（預設值或環境變數 WHITELIST_NEW_SITE_*），
腳本不會把密碼印出來。若某一步失敗，輸出會指出是哪一步，把輸出貼回來即可判斷哪裡不同。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import httpx  # noqa: E402

from services import whitelist_service as w  # noqa: E402

TEST_VENDOR = "WinBet_1"


def check() -> bool:
    base = w.NEW_SITE_BASE.rstrip("/") + "/api"
    print(f"站點：{w.NEW_SITE_BASE}（帳號 {w.NEW_SITE_USER}）")
    with httpx.Client(base_url=base, timeout=60, follow_redirects=True) as client:
        r = client.post("/auth/login", json={"username": w.NEW_SITE_USER, "password": w.NEW_SITE_PASS,
                                             "recaptcha_token": ""})
        print(f"[1] POST /api/auth/login → {r.status_code}")
        try:
            data = r.json()
        except Exception:
            print("    回應不是 JSON，前 200 字：", r.text[:200].replace("\n", " "))
            return False
        if r.status_code != 200:
            print(f"    登入失敗：{str(data.get('error') or data)[:200]}")
            return False
        print(f"    stage={data.get('stage')}, required_factors={data.get('required_factors')}")
        if data.get("stage") != "full" or not data.get("token"):
            print("    登入未完成（需要二次驗證或改密碼），機器人無法自動處理這種帳號狀態")
            return False
        client.headers["Authorization"] = f"Bearer {data['token']}"

        r = client.get("/api-catalog/options")
        print(f"[2] GET /api/api-catalog/options → {r.status_code}")
        if r.status_code != 200:
            print("    ", r.text[:200].replace("\n", " "))
            return False
        users = r.json().get("api_users") or []
        print(f"    廠商數：{len(users)}，前 3 筆：{[(u.get('id'), u.get('name')) for u in users[:3]]}")
        hit = [u for u in users if (u.get("name") or "").upper() == TEST_VENDOR.upper()]
        print(f"    測試廠商 {TEST_VENDOR}：{'找到 id=' + str(hit[0]['id']) if hit else '找不到'}")
        if not hit:
            return False

        r = client.get("/ip-whitelist")
        print(f"[3] GET /api/ip-whitelist → {r.status_code}")
        if r.status_code != 200:
            print("    ", r.text[:200].replace("\n", " "))
            return False
        entries = r.json().get("entries") or []
        mine = [e for e in entries if e.get("target_type") == "api" and e.get("target_id") == hit[0]["id"]]
        print(f"    白名單設定共 {len(entries)} 筆；{TEST_VENDOR} 目前："
              + (f"已有設定 id={mine[0].get('id')}、status={mine[0].get('status')}、IP 數={len(mine[0].get('ips') or [])}"
                 if mine else "尚無設定（新增時會建立一筆）"))
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", metavar="IP", help="實際對測試廠商新增這個 IP（會寫入後台）")
    args = ap.parse_args()
    if not check():
        print("結果：檢查未通過")
        sys.exit(1)
    if args.add:
        print(f"[4] 對 {TEST_VENDOR} 新增 IP {args.add} …")
        success, vendor, rejected = w.run_whitelist_sync_new(TEST_VENDOR.split("_"), [args.add])
        print(f"    結果：success={success}, vendor={vendor}, rejected={rejected}")
        sys.exit(0 if success else 1)
    print("結果：檢查通過；要驗證新增請加上 --add <IP>")


if __name__ == "__main__":
    main()
