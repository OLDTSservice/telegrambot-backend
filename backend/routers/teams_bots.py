"""Teams 機器人（個人帳號輪詢模式）管理 API。

新增機器人 = 裝置代碼登入：
  POST /login/start        → 回 {session_id, user_code, verification_uri}
  GET  /login/status/{sid} → 前端每 5 秒輪詢；success 時後端已建好機器人並啟動 watcher
既有機器人重新登入（refresh token 失效時）走同一組端點，start 時帶 bot_id。
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_editor, require_viewer
from database import get_db
from services import teams_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/teams-bots", tags=["Teams機器人"])


def _to_out(bot: models.TeamsBot) -> dict:
    return {
        "id": bot.id, "name": bot.name,
        "account_mri": bot.account_mri, "account_name": bot.account_name, "account_email": bot.account_email,
        "is_enabled": bool(bot.is_enabled),
        "whitelist_enabled": bool(bot.whitelist_enabled),
        "whitelist_mode": bot.whitelist_mode or "full",
        "poll_interval_sec": bot.poll_interval_sec or 20,
        "logged_in": bool(bot.refresh_token),
        "running": teams_service.is_watcher_running(bot.id),
        "last_poll_at": bot.last_poll_at, "last_error": bot.last_error,
        "created_at": bot.created_at, "updated_at": bot.updated_at,
    }


def _get_bot(db: Session, bot_id: int) -> models.TeamsBot:
    bot = db.query(models.TeamsBot).filter(models.TeamsBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="機器人不存在")
    return bot


# ── 機器人 CRUD ─────────────────────────────────────────────────────────────
@router.get("", response_model=List[schemas.TeamsBotOut])
def list_teams_bots(db: Session = Depends(get_db), _=Depends(require_viewer)):
    return [_to_out(b) for b in db.query(models.TeamsBot).order_by(models.TeamsBot.id).all()]


@router.put("/{bot_id}", response_model=schemas.TeamsBotOut)
def update_teams_bot(bot_id: int, payload: schemas.TeamsBotUpdate,
                     db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = _get_bot(db, bot_id)
    data = payload.model_dump(exclude_none=True)
    if "whitelist_mode" in data and data["whitelist_mode"] not in ("log_only", "no_reply", "full"):
        raise HTTPException(status_code=400, detail="whitelist_mode 只能是 log_only / no_reply / full")
    if "poll_interval_sec" in data:
        data["poll_interval_sec"] = max(teams_service.MIN_POLL_INTERVAL, int(data["poll_interval_sec"]))
    for field, value in data.items():
        setattr(bot, field, value)
    db.commit()
    db.refresh(bot)
    # 啟用/停用要同步 watcher；其他開關 watcher 每輪會自己從 DB 重讀
    if "is_enabled" in data:
        if bot.is_enabled and bot.refresh_token:
            bot.last_error = None
            db.commit()
            teams_service.start_watcher(bot.id, bot.refresh_token)
        else:
            teams_service.stop_watcher(bot.id)
    return _to_out(bot)


@router.delete("/{bot_id}")
def delete_teams_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    bot = _get_bot(db, bot_id)
    teams_service.stop_watcher(bot.id)
    db.delete(bot)
    db.commit()
    return {"message": "已刪除"}


@router.post("/{bot_id}/restart", response_model=schemas.TeamsBotOut)
def restart_teams_bot(bot_id: int, db: Session = Depends(get_db), _=Depends(require_editor)):
    """watcher 因例外停掉時手動重啟（登入失效的話要走重新登入）"""
    bot = _get_bot(db, bot_id)
    if not bot.refresh_token:
        raise HTTPException(status_code=400, detail="尚未登入，請先完成 Teams 帳號登入")
    bot.last_error = None
    bot.is_enabled = True
    db.commit()
    teams_service.restart_watcher(bot.id, bot.refresh_token)
    db.refresh(bot)
    return _to_out(bot)


# ── 裝置代碼登入 ────────────────────────────────────────────────────────────
@router.post("/login/start")
def login_start(payload: schemas.TeamsLoginStartIn, bot_id: Optional[int] = None,
                db: Session = Depends(get_db), _=Depends(require_editor)):
    if bot_id is not None:
        _get_bot(db, bot_id)
        name = None
    else:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="請輸入機器人名稱")
    try:
        return teams_service.start_device_login(name, bot_id=bot_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/login/status/{session_id}")
def login_status(session_id: str, db: Session = Depends(get_db), _=Depends(require_editor)):
    r = teams_service.poll_device_login(session_id)
    if r["status"] != "success":
        return {"status": r["status"], "error": r.get("error")}

    s = r["session"]
    # 同一個 session 可能被前端輪詢多次（請求交錯）：機器人只建一次，之後都回同一個結果
    if s.get("done_bot_id") is not None:
        return {"status": "success", "bot": _to_out(_get_bot(db, s["done_bot_id"]))}

    res = s["result"]
    if s.get("bot_id") is not None:
        bot = _get_bot(db, s["bot_id"])
    else:
        bot = models.TeamsBot(name=s["name"], app_id="", app_password="")
        db.add(bot)
    bot.refresh_token = res["refresh_token"]
    bot.account_name = res.get("account_name")
    bot.account_email = res.get("account_email")
    bot.last_error = None
    db.commit()
    db.refresh(bot)
    s["done_bot_id"] = bot.id
    s["result"] = None                     # refresh token 已入庫，不留在記憶體

    # 先 mint 一次拿 MRI（順便驗證權杖鏈），再啟動 watcher
    try:
        client = teams_service.TeamsAccountClient(bot.id, bot.refresh_token, teams_service.persist_refresh_token)
        client.ensure_auth(force=True)
        bot.account_mri = client.mri
        db.commit()
    except Exception as e:
        logger.error(f"[Teams {bot.id}] 登入後驗證權杖鏈失敗：{e}")
        bot.last_error = f"登入後驗證失敗：{str(e)[:200]}"
        db.commit()
    db.refresh(bot)
    if bot.is_enabled and bot.refresh_token:
        teams_service.restart_watcher(bot.id, bot.refresh_token)
    return {"status": "success", "bot": _to_out(bot)}


# ── 群組設定 ────────────────────────────────────────────────────────────────
@router.get("/{bot_id}/groups", response_model=List[schemas.TeamsGroupOut])
def list_groups(bot_id: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    """即時從 Teams 列出帳號所在群組，合併 DB 裡的群組設定（吃 1 次 API 額度）"""
    bot = _get_bot(db, bot_id)
    if not bot.refresh_token:
        raise HTTPException(status_code=400, detail="尚未登入，請先完成 Teams 帳號登入")
    try:
        live = teams_service.list_groups_live(bot)
    except teams_service.TeamsAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"讀取群組失敗：{str(e)[:200]}")

    settings = {s.chat_id: s for s in db.query(models.TeamsGroupSetting)
                .filter(models.TeamsGroupSetting.bot_id == bot_id).all()}
    seen = set()
    items = []
    for g in live:
        seen.add(g["chat_id"])
        s = settings.get(g["chat_id"])
        items.append({**g, **_setting_fields(s)})
    # DB 有設定但這次清單沒列到的群（舊 @thread.skype 偶發漏列）也顯示出來
    for cid, s in settings.items():
        if cid not in seen:
            items.append({"chat_id": cid, "chat_name": s.chat_name or cid, **_setting_fields(s)})
    return items


def _setting_fields(s: Optional[models.TeamsGroupSetting]) -> dict:
    return {
        "watch_enabled": s.watch_enabled if s else True,
        "whitelist_vendor_check": s.whitelist_vendor_check if s else False,
        "whitelist_allowed_vendors": s.whitelist_allowed_vendors if s else None,
        "single_vendor_mode": s.single_vendor_mode if s else False,
        "single_vendor_name": s.single_vendor_name if s else None,
        "relaxed_bo_detect": s.relaxed_bo_detect if s else False,
        "ticket_creation_enabled": s.ticket_creation_enabled if s else True,
    }


@router.put("/{bot_id}/groups/{chat_id:path}")
def update_group(bot_id: int, chat_id: str, payload: schemas.TeamsGroupUpdateIn,
                 db: Session = Depends(get_db), _=Depends(require_editor)):
    _get_bot(db, bot_id)
    setting = db.query(models.TeamsGroupSetting).filter(
        models.TeamsGroupSetting.bot_id == bot_id,
        models.TeamsGroupSetting.chat_id == chat_id,
    ).first()
    if not setting:
        setting = models.TeamsGroupSetting(bot_id=bot_id, chat_id=chat_id)
        db.add(setting)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(setting, field, value)
    db.commit()
    return {"message": "已更新"}


# ── 白名單處理紀錄 ──────────────────────────────────────────────────────────
@router.get("/{bot_id}/whitelist-logs", response_model=List[schemas.TeamsWhitelistLogOut])
def whitelist_logs(bot_id: int, limit: int = 50, db: Session = Depends(get_db), _=Depends(require_viewer)):
    return (
        db.query(models.TeamsWhitelistLog)
        .filter(models.TeamsWhitelistLog.bot_id == bot_id)
        .order_by(models.TeamsWhitelistLog.created_at.desc())
        .limit(limit)
        .all()
    )
