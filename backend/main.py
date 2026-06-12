import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, SessionLocal
import models
from auth import hash_password
from routers import auth, users, bots, rules, knowledge, stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db():
    try:
        models.Base.metadata.create_all(bind=engine)
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
    """診斷知識庫狀態"""
    db = SessionLocal()
    try:
        docs = db.query(models.KnowledgeDoc).all()
        result = []
        for doc in docs:
            item = {
                "id": doc.id,
                "bot_id": doc.bot_id,
                "filename": doc.original_filename,
                "is_enabled": doc.is_enabled,
                "chroma_collection": doc.chroma_collection,
                "collection_set": bool(doc.chroma_collection),
            }
            # 嘗試查詢 chroma collection 是否存在
            if doc.chroma_collection:
                try:
                    from services.ai_service import get_chroma_client, _CHROMA_AVAILABLE
                    from chromadb.utils import embedding_functions
                    if _CHROMA_AVAILABLE:
                        client = get_chroma_client()
                        col = client.get_collection(
                            name=doc.chroma_collection,
                            embedding_function=embedding_functions.DefaultEmbeddingFunction()
                        )
                        item["chroma_doc_count"] = col.count()
                        item["chroma_status"] = "ok"
                    else:
                        item["chroma_status"] = "chromadb not available"
                except Exception as e:
                    item["chroma_status"] = f"error: {e}"
            else:
                item["chroma_status"] = "no collection name"
            result.append(item)
        return {"docs": result}
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
