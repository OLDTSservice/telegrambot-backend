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
    return {"status": "ok"}
