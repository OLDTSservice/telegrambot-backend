from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/rules", tags=["關鍵字規則"])


@router.get("", response_model=List[schemas.RuleOut])
def list_rules(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.KeywordRule).all()


@router.post("", response_model=schemas.RuleOut)
def create_rule(payload: schemas.RuleCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TelegramBot).filter(models.TelegramBot.id == payload.bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    rule = models.KeywordRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(rule_id: int, payload: schemas.RuleUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    rule = db.query(models.KeywordRule).filter(models.KeywordRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="規則不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    rule = db.query(models.KeywordRule).filter(models.KeywordRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="規則不存在")
    db.delete(rule)
    db.commit()
    return {"message": "已刪除"}
