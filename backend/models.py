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
    ignores = relationship("TelegramIgnore", back_populates="bot", cascade="all, delete-orphan")
    group_stats = relationship("TelegramGroupStat", back_populates="bot", cascade="all, delete-orphan")


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
    chunks = relationship("KnowledgeChunk", back_populates="doc", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """文件段落（取代 ChromaDB，直接存 SQLite）"""
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)

    doc = relationship("KnowledgeDoc", back_populates="chunks")


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


# ── Telegram Ignore List ───────────────────────────────────────────────────
class TelegramIgnore(Base):
    __tablename__ = "telegram_ignores"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    identifier = Column(String(255), nullable=False)   # Telegram user_id 或 @username
    note = Column(String(500), nullable=True)           # 備註說明
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="ignores")


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
    ignores = relationship("TeamsIgnore", back_populates="bot", cascade="all, delete-orphan")
    group_stats = relationship("TeamsGroupStat", back_populates="bot", cascade="all, delete-orphan")


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
    chunks = relationship("TeamsKnowledgeChunk", back_populates="doc", cascade="all, delete-orphan")


class TeamsKnowledgeChunk(Base):
    """Teams 文件段落（取代 ChromaDB）"""
    __tablename__ = "teams_knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("teams_knowledge_docs.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)

    doc = relationship("TeamsKnowledgeDoc", back_populates="chunks")


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


# ── Teams Ignore List ──────────────────────────────────────────────────────
class TeamsIgnore(Base):
    __tablename__ = "teams_ignores"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    identifier = Column(String(255), nullable=False)   # Teams 使用者 email 或 AAD Object ID
    note = Column(String(500), nullable=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TeamsBot", back_populates="ignores")


# ── Telegram Group Reply Stats ─────────────────────────────────────────────
class TelegramGroupStat(Base):
    __tablename__ = "telegram_group_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(50), nullable=False)       # Telegram chat ID（群組為負數）
    chat_name = Column(String(255), nullable=False)    # 群組或私聊名稱
    chat_type = Column(String(30), nullable=True)      # private / group / supergroup / channel
    date = Column(String(10), nullable=False)           # YYYY-MM-DD
    reply_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="group_stats")


# ── Teams Group Reply Stats ────────────────────────────────────────────────
class TeamsGroupStat(Base):
    __tablename__ = "teams_group_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("teams_bots.id"), nullable=False)
    conversation_id = Column(String(500), nullable=False)
    conversation_name = Column(String(255), nullable=False)
    date = Column(String(10), nullable=False)           # YYYY-MM-DD
    reply_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TeamsBot", back_populates="group_stats")


# ── Copilot Bot (Copilot Studio 整合) ─────────────────────────────────────
class CopilotBot(Base):
    __tablename__ = "copilot_bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    keyword_rules = relationship("CopilotKeywordRule", back_populates="bot", cascade="all, delete-orphan")
    knowledge_docs = relationship("CopilotKnowledgeDoc", back_populates="bot", cascade="all, delete-orphan")
    group_stats = relationship("CopilotGroupStat", back_populates="bot", cascade="all, delete-orphan")


class CopilotKeywordRule(Base):
    __tablename__ = "copilot_keyword_rules"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("copilot_bots.id"), nullable=False)
    keyword = Column(String(500), nullable=False)
    reply_message = Column(Text, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("CopilotBot", back_populates="keyword_rules")


class CopilotKnowledgeDoc(Base):
    __tablename__ = "copilot_knowledge_docs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("copilot_bots.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_size = Column(Integer)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("CopilotBot", back_populates="knowledge_docs")
    chunks = relationship("CopilotKnowledgeChunk", back_populates="doc", cascade="all, delete-orphan")


class CopilotKnowledgeChunk(Base):
    __tablename__ = "copilot_knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("copilot_knowledge_docs.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("copilot_bots.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)

    doc = relationship("CopilotKnowledgeDoc", back_populates="chunks")


class CopilotGroupStat(Base):
    __tablename__ = "copilot_group_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("copilot_bots.id"), nullable=False)
    conversation_id = Column(String(500), nullable=False)
    conversation_name = Column(String(255), nullable=False)
    date = Column(String(10), nullable=False)
    reply_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("CopilotBot", back_populates="group_stats")
