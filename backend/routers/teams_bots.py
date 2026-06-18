import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models, schemas
from auth import require_editor, require_viewer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/teams-bots", tags=["Teams機器人"])

BACKEND_URL = ""  # 由前端顯示，動態填入


@router.get("", response_model=List[schemas.TeamsBotOut])
def list_teams_bots(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return db.query(models.TeamsBot).all()


@router.post("", response_model=schemas.TeamsBotOut)
def create_teams_bot(payload: schemas.TeamsBotCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = models.TeamsBot(**payload.model_dump())
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.put("/{bot_id}", response_model=schemas.TeamsBotOut)
def update_teams_bot(bot_id: int, payload: schemas.TeamsBotUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(bot, field, value)
    db.commit()
    db.refresh(bot)
    return bot


@router.delete("/{bot_id}")
def delete_teams_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}


@router.post("/webhook/{bot_id}")
async def teams_webhook(bot_id: int, request: Request, db: Session = Depends(get_db)):
    """接收 Microsoft Teams 訊息 Webhook"""
    from services.teams_service import process_teams_activity

    bot = db.query(models.TeamsBot).filter(
        models.TeamsBot.id == bot_id,
        models.TeamsBot.is_enabled == True
    ).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在或已停用")

    auth_header = request.headers.get("Authorization", "")
    body = await request.body()

    try:
        await process_teams_activity(bot, body, auth_header, db)
    except Exception as e:
        logger.error(f"Teams Bot {bot_id} 處理 Webhook 失敗：{e}", exc_info=True)

    return Response(status_code=200)
