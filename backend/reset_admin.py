"""緊急重設後台帳號密碼（取代原本不需登入的 /api/debug/reset-admin API）。

只能在伺服器上執行（例如 Render 後台的 Shell），能登入伺服器的人才用得到，外部無法呼叫。
會重設指定帳號的密碼並重新啟用該帳號；角色與頁面權限不變。

用法（在 backend 目錄執行）：
  python reset_admin.py              # 重設 admin，互動輸入新密碼（輸入時不會顯示）
  python reset_admin.py 帳號名稱      # 重設指定帳號
"""
import getpass
import os
import sys

# database.py 在沒有 /data（Render 永久磁碟）時使用目前目錄的 tgadmin.db，先切到本檔所在目錄確保找對資料庫
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal  # noqa: E402
from auth import hash_password  # noqa: E402
import models  # noqa: E402


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            existing = ", ".join(u.username for u in db.query(models.User).all()) or "（無）"
            sys.exit(f"找不到帳號「{username}」。目前的帳號：{existing}")

        password = getpass.getpass(f"請輸入「{username}」的新密碼：")
        if len(password) < 8:
            sys.exit("密碼至少需要 8 個字元，未變更。")
        if getpass.getpass("請再輸入一次：") != password:
            sys.exit("兩次輸入不一致，未變更。")

        user.hashed_password = hash_password(password)
        user.is_active = True
        db.commit()
        print(f"已重設「{username}」的密碼並啟用帳號（角色：{user.role}）。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
