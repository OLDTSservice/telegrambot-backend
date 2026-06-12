import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 若 /data 目錄存在（Render Persistent Disk）則使用永久路徑，否則用本機路徑
_db_dir = "/data" if os.path.isdir("/data") else "."
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_dir}/tgadmin.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
