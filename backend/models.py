from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="viewer")  # superadmin, editor, viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramBot(Base):
    __tablename__ = "telegram_bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    keyword_rules = relationship("KeywordRule", back_populates="bot", cascade="all, delete-orphan")
    knowledge_docs = relationship("KnowledgeDoc", back_populates="bot", cascade="all, delete-orphan")
    usage_stats = relationship("UsageStat", back_populates="bot", cascade="all, delete-orphan")


class KeywordRule(Base):
    __tablename__ = "keyword_rules"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    keyword = Column(String(500), nullable=False)
    reply_message = Column(Text, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="keyword_rules")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_size = Column(Integer)
    chroma_collection = Column(String(100))
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="knowledge_docs")


class UsageStat(Base):
    __tablename__ = "usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    request_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="usage_stats")


# ── Teams Bot ──────────────────────────────────────────────────────────────
class TeamsBot(Base):
    __tablename__ = "teams_bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    app_id = Column(String(255), nullable=False)        # Azure App Registration Client ID
    app_password = Column(String(500), nullable=False)  # Azure App Registration Client Secret
    tenant_id = Column(String(255), nullable=True)      # 空白 = 多租戶
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    keyword_rules = relationship("TeamsKeywordRule", back_populates="bot", cascade="all, delete-orphan")
    knowledge_docs = relationship("TeamsKnowledgeDoc", back_populates="bot", cascade="all, delete-orphan")
    usage_stats = relationship("TeamsUsageStat", back_populates="bot", cascade="all, delete-orphan")


class TeamsKeywordRule(Base):
    __tablename__ = "teams_keyword_rules"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    keyword = Column(String(500), nullable=False)
    reply_message = Column(Text, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TeamsBot", back_populates="keyword_rules")


class TeamsKnowledgeDoc(Base):
    __tablename__ = "teams_knowledge_docs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_size = Column(Integer)
    chroma_collection = Column(String(100))
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TeamsBot", back_populates="knowledge_docs")


class TeamsUsageStat(Base):
    __tablename__ = "teams_usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    date = Column(String(10), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    request_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TeamsBot", back_populates="usage_stats")
