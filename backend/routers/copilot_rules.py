from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/copilot-rules", tags=["Copilot關鍵字規則"])


@router.get("", response_model=List[schemas.CopilotRuleOut])
def list_rules(bot_id: int = None, db: Session = Depends(get_db), _=Depends(require_viewer)):
    q = db.query(models.CopilotKeywordRule)
    if bot_id:
        q = q.filter(models.CopilotKeywordRule.bot_id == bot_id)
    return q.all()


@router.post("", response_model=schemas.CopilotRuleOut)
def create_rule(payload: schemas.CopilotRuleCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    rule = models.CopilotKeywordRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.CopilotRuleOut)
def update_rule(rule_id: int, payload: schemas.CopilotRuleUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    rule = db.query(models.CopilotKeywordRule).filter(models.CopilotKeywordRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="規則不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    rule = db.query(models.CopilotKeywordRule).filter(models.CopilotKeywordRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="規則不存在")
    db.delete(rule)
    db.commit()
    return {"message": "已刪除"}
