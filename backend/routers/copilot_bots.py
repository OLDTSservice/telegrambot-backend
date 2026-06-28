from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

router = APIRouter(prefix="/api/copilot-bots", tags=["Copilot機器人"])

BACKEND_URL = "https://tg-admin-backend-rm99.onrender.com"


@router.get("", response_model=List[schemas.CopilotBotOut])
def list_copilot_bots(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.CopilotBot).all()


@router.post("", response_model=schemas.CopilotBotOut)
def create_copilot_bot(payload: schemas.CopilotBotCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = models.CopilotBot(**payload.model_dump())
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.put("/{bot_id}", response_model=schemas.CopilotBotOut)
def update_copilot_bot(bot_id: int, payload: schemas.CopilotBotUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.CopilotBot).filter(models.CopilotBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(bot, k, v)
    db.commit()
    db.refresh(bot)
    return bot


@router.delete("/{bot_id}")
def delete_copilot_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.CopilotBot).filter(models.CopilotBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}


@router.get("/{bot_id}/query-url")
def get_query_url(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    bot = db.query(models.CopilotBot).filter(models.CopilotBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    return {"query_url": f"{BACKEND_URL}/api/copilot/query"}
