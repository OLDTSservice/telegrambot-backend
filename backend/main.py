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
from services.telegram_service import start_all_enabled_bots

logging.basicConfig(level=logging.INFO)


def init_db():
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
            logging.info("預設管理員帳號已建立：admin / admin123")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        start_all_enabled_bots(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Telegram 機器人後台管理系統", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
