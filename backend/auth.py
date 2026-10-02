import json
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models

SECRET_KEY = "tg-admin-secret-key-change-in-production-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小時

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無效的認證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*roles):
    def checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="權限不足")
        return current_user
    return checker


require_superadmin = require_role("superadmin")
require_editor = require_role("superadmin", "editor")
require_viewer = require_role("superadmin", "editor", "viewer")


# ── 頁面權限 ────────────────────────────────────────────────────────────────
# 每個 key 對應側邊選單的一個頁面（前端 frontend/src/permissions.js 的 PAGES 需同步）。
# 「帳號管理」不在其中：固定只有超級管理員能使用。
PAGE_KEYS = (
    "telegram_bots", "telegram_rules", "telegram_knowledge", "telegram_ignores",
    "telegram_bot_admins", "telegram_reply_stats", "telegram_live", "telegram_whitelist",
    "telegram_netwin",
    "teams_bots", "teams_rules", "teams_knowledge", "teams_ignores",
    "teams_reply_stats", "teams_whitelist", "teams_netwin",
    "usage_stats",
)


def sanitize_page_permissions(raw, role: str) -> dict:
    """只保留合法的頁面 key 與 view/edit；檢視者的 edit 一律降為 view。"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, level in raw.items():
        if key in PAGE_KEYS and level in ("view", "edit"):
            out[key] = "edit" if (level == "edit" and role == "editor") else "view"
    return out


def effective_page_permissions(user) -> dict:
    """回傳 {page_key: "view" | "edit"}，沒列出的頁面＝不能查看。
    超級管理員全部可編輯；permissions 為 NULL（功能上線前就存在、還沒設定過的帳號）沿用原本的
    角色行為：編輯員全部可編輯、檢視者全部可查看，部署後既有帳號權限不會改變。"""
    if user.role == "superadmin":
        return {k: "edit" for k in PAGE_KEYS}
    if user.permissions is None:
        level = "edit" if user.role == "editor" else "view"
        return {k: level for k in PAGE_KEYS}
    try:
        raw = json.loads(user.permissions)
    except Exception:
        raw = {}                      # 資料損毀時寧可全部關閉，不放行
    return sanitize_page_permissions(raw, user.role)


def can_view_page(user, *keys) -> bool:
    perms = effective_page_permissions(user)
    return any(k in perms for k in keys)


def can_edit_page(user, *keys) -> bool:
    perms = effective_page_permissions(user)
    return any(perms.get(k) == "edit" for k in keys)


def require_page_view(*keys):
    """可查看任一指定頁面才放行（同一支 API 可能被多個頁面使用）。"""
    def checker(current_user: models.User = Depends(get_current_user)):
        if not can_view_page(current_user, *keys):
            raise HTTPException(status_code=403, detail="沒有此頁面的查看權限")
        return current_user
    return checker


def require_page_edit(*keys):
    """可編輯任一指定頁面才放行。"""
    def checker(current_user: models.User = Depends(get_current_user)):
        if not can_edit_page(current_user, *keys):
            raise HTTPException(status_code=403, detail="沒有此頁面的編輯權限")
        return current_user
    return checker


def ensure_field_permissions(user, fields, field_pages: dict, default_pages: tuple):
    """同一支更新 API 被多個頁面共用時（例如機器人設定），逐欄位檢查：
    每個要修改的欄位，使用者必須能編輯該欄位所屬的任一頁面，否則整筆拒絕。"""
    denied = [f for f in fields if not can_edit_page(user, *field_pages.get(f, default_pages))]
    if denied:
        raise HTTPException(status_code=403, detail=f"沒有權限修改這些設定：{', '.join(denied)}")
