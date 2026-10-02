from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
import json
from auth import (require_superadmin, hash_password, effective_page_permissions,
                  sanitize_page_permissions)

router = APIRouter(prefix="/api/users", tags=["帳號管理"])


def user_out(user: models.User) -> dict:
    """UserOut 需要的欄位＋實際生效的頁面權限（/api/auth/me 也共用）"""
    return {
        "id": user.id, "username": user.username, "email": user.email, "role": user.role,
        "is_active": user.is_active, "created_at": user.created_at,
        "page_permissions": effective_page_permissions(user),
        "permissions_customized": user.role != "superadmin" and user.permissions is not None,
    }


def _store_permissions(user: models.User, raw):
    """超級管理員不存（固定全部權限）；其餘角色存清理過的 JSON，檢視者的 edit 自動降為 view。"""
    if user.role == "superadmin":
        user.permissions = None
    elif raw is not None:
        user.permissions = json.dumps(sanitize_page_permissions(raw, user.role), ensure_ascii=False)


@router.get("", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_superadmin)):
    return [user_out(u) for u in db.query(models.User).all()]


@router.post("", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db), _=Depends(require_superadmin)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="帳號已存在")
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email 已存在")
    if payload.role not in ("superadmin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="無效的角色")
    user = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    _store_permissions(user, payload.permissions)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, payload: schemas.UserUpdate, db: Session = Depends(get_db), _=Depends(require_superadmin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        if payload.role not in ("superadmin", "editor", "viewer"):
            raise HTTPException(status_code=400, detail="無效的角色")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    if payload.permissions is not None:
        _store_permissions(user, payload.permissions)
    elif payload.role is not None and user.permissions is not None:
        # 只改角色沒改權限：重新清理一次（改成檢視者時 edit 降為 view；改成超級管理員時清空）
        _store_permissions(user, json.loads(user.permissions))
    elif payload.role == "superadmin":
        user.permissions = None
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(require_superadmin)):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="無法刪除自己的帳號")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    db.delete(user)
    db.commit()
    return {"message": "已刪除"}
