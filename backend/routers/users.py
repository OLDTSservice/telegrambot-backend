from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_superadmin, require_viewer, hash_password

router = APIRouter(prefix="/api/users", tags=["帳號管理"])


@router.get("", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_superadmin)):
    return db.query(models.User).all()


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
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    db.commit()
    db.refresh(user)
    return user


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
