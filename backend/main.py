import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, SessionLocal
import models
from auth import hash_password
from routers import auth, users, bots, rules, knowledge, stats, telegram_ignores, group_stats, telegram_live

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _migrate_columns():
    """為既有資料表補齊新增欄位（SQLite 不支援 ALTER TABLE … IF NOT EXISTS，用 try/except）"""
    migrations = [
        "ALTER TABLE telegram_bots ADD COLUMN is_managed BOOLEAN DEFAULT 0",
        "ALTER TABLE telegram_messages ADD COLUMN telegram_message_id INTEGER",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                from sqlalchemy import text as sa_text
                conn.execute(sa_text(sql))
                conn.commit()
                logger.info(f"Migration OK: {sql[:60]}")
            except Exception:
                pass  # 欄位已存在時 SQLite 會拋例外，直接略過


def init_db():
    try:
        models.Base.metadata.create_all(bind=engine)
        _migrate_columns()
        db = SessionLocal()
        try:
            if not db.query(models.User).filter(models.User.username == "admin").first():
                admin = models.User(
                    username="admin",
                    email="admin@example.com",
                    hashed_password=hash_password("admin123"),
                    role="superadmin",
                )
                db.add(admin)
                db.commit()
                logger.info("預設管理員帳號已建立：admin / admin123")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"資料庫初始化失敗：{e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 嘗試啟動機器人，失敗不影響 API 服務
    try:
        from services.telegram_service import start_all_enabled_bots
        db = SessionLocal()
        try:
            start_all_enabled_bots(db)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Telegram 機器人啟動失敗（API 服務仍可正常使用）：{e}")
    yield


app = FastAPI(title="Telegram 機器人後台管理系統", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 部署階段開放所有來源，可透過 ALLOWED_ORIGINS 環境變數收緊
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(bots.router)
app.include_router(rules.router)
app.include_router(knowledge.router)
app.include_router(stats.router)
app.include_router(telegram_ignores.router)
app.include_router(group_stats.router)
app.include_router(telegram_live.router)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/api/health")
def health():
    from database import SQLALCHEMY_DATABASE_URL
    return {"status": "ok", "db": SQLALCHEMY_DATABASE_URL}


@app.get("/api/debug/ai")
def debug_ai():
    """診斷 AI 知識庫功能是否正常（無需登入）"""
    result = {}
    try:
        import chromadb
        result["chromadb"] = "ok"
    except Exception as e:
        result["chromadb"] = f"error: {e}"
    try:
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY", "")
        result["anthropic_key"] = "set" if key else "missing"
    except Exception as e:
        result["anthropic"] = f"error: {e}"
    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.DefaultEmbeddingFunction()
        result["embedding_function"] = "ok"
    except Exception as e:
        result["embedding_function"] = f"error: {e}"
    result["chroma_path"] = os.getenv("CHROMA_PATH", "/data/chroma_db if /data exists else ./chroma_db")
    result["/data exists"] = os.path.isdir("/data")
    return result


@app.post("/api/debug/reset-admin")
def reset_admin():
    """緊急重設 admin 密碼"""
    from auth import hash_password
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "admin").first()
        if user:
            user.hashed_password = hash_password("admin123")
            db.commit()
            return {"message": "admin 密碼已重設為 admin123"}
        return {"message": "admin 帳號不存在"}
    finally:
        db.close()


@app.get("/api/debug/knowledge")
def debug_knowledge():
    """診斷知識庫狀態（SQLite 段落數量）"""
    db = SessionLocal()
    try:
        docs = db.query(models.KnowledgeDoc).all()
        result = []
        for doc in docs:
            chunk_count = db.query(models.KnowledgeChunk).filter(
                models.KnowledgeChunk.doc_id == doc.id
            ).count()
            result.append({
                "id": doc.id,
                "bot_id": doc.bot_id,
                "filename": doc.original_filename,
                "is_enabled": doc.is_enabled,
                "chunk_count": chunk_count,
                "status": "ok" if chunk_count > 0 else "no_chunks（請重新上傳）",
            })
        total_chunks = db.query(models.KnowledgeChunk).count()
        return {"docs": result, "total_chunks": total_chunks}
    finally:
        db.close()


@app.get("/api/debug/managed-status")
def debug_managed_status():
    """確認各 Telegram 機器人的 is_managed 設定值"""
    db = SessionLocal()
    try:
        bots = db.query(models.TelegramBot).all()
        result = []
        for b in bots:
            msg_count = db.query(models.TelegramMessage).filter(
                models.TelegramMessage.bot_id == b.id
            ).count()
            result.append({
                "id": b.id,
                "name": b.name,
                "is_managed": b.is_managed,
                "is_enabled": b.is_enabled,
                "live_message_count": msg_count,
            })
        return {"bots": result}
    finally:
        db.close()


@app.post("/api/debug/test-knowledge")
async def test_knowledge(bot_id: int, question: str):
    """直接測試知識庫 AI 查詢"""
    from services.ai_service import query_knowledge
    db = SessionLocal()
    try:
        result = query_knowledge(bot_id, question, db)
        if result:
            reply, input_tokens, output_tokens = result
            return {"answer": reply, "input_tokens": input_tokens, "output_tokens": output_tokens}
        return {"answer": None, "reason": "沒有找到相關知識庫內容或知識庫為空"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()
