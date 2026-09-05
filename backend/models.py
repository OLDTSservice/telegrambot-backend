from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy import text
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

    is_managed = Column(Boolean, default=False)       # 即時對話管控總開關
    whitelist_enabled = Column(Boolean, default=False) # 後台白名單自動處理開關
    game_asset_enabled = Column(Boolean, default=False) # JILI 遊戲素材查詢開關
    tada_asset_enabled = Column(Boolean, default=False) # TADA 遊戲素材查詢開關
    tada_gamelist_query_enabled = Column(Boolean, default=False) # TADA Gamelist進階查詢開關（熱門排行/欄位查詢/複合篩選）
    tada_certification_query_enabled = Column(Boolean, default=False) # TADA 認證文件查詢開關（含多輪追問機制）

    # 查輸贏回覆：偵測到廠商在問「這個玩家/這筆下注是否正常」時，先呼叫 tjadmin 外部客服 API
    # 查該玩家近2日淨值，淨值在門檻以下才讓機器人直接依固定內容回覆，否則轉人工。
    netwin_query_enabled = Column(Boolean, default=False)
    netwin_key_id = Column(String(24), nullable=True)      # tjadmin API 金鑰前24字元識別段
    netwin_api_key = Column(String(64), nullable=True)     # tjadmin API 完整64字元金鑰（機密）
    netwin_api_base_url = Column(String(255), nullable=True)  # tjadmin API 網域，例如 https://xxx.example.com
    netwin_threshold = Column(Float, default=5000)         # netwin_2d_thb 門檻，低於此值才自動回覆
    netwin_reply_zh = Column(Text, nullable=True)          # 自動回覆固定內容（中文）
    netwin_reply_en = Column(Text, nullable=True)          # 自動回覆固定內容（英文）

    keyword_rules = relationship("KeywordRule", back_populates="bot", cascade="all, delete-orphan")
    knowledge_docs = relationship("KnowledgeDoc", back_populates="bot", cascade="all, delete-orphan")
    usage_stats = relationship("UsageStat", back_populates="bot", cascade="all, delete-orphan")
    ignores = relationship("TelegramIgnore", back_populates="bot", cascade="all, delete-orphan")
    bot_admins = relationship("TelegramBotAdmin", back_populates="bot", cascade="all, delete-orphan")
    group_stats = relationship("TelegramGroupStat", back_populates="bot", cascade="all, delete-orphan")
    group_settings = relationship("TelegramGroupSetting", back_populates="bot", cascade="all, delete-orphan")
    live_messages = relationship("TelegramMessage", back_populates="bot", cascade="all, delete-orphan")
    whitelist_logs = relationship("WhitelistLog", back_populates="bot", cascade="all, delete-orphan")
    conversation_logs = relationship("ConversationLog", back_populates="bot", cascade="all, delete-orphan")
    no_answer_logs = relationship("NoAnswerLog", back_populates="bot", cascade="all, delete-orphan")
    ai_rescue_setting = relationship("AIRescueSetting", back_populates="bot", uselist=False, cascade="all, delete-orphan")
    rescue_candidates = relationship("AIRescueCandidate", back_populates="bot", cascade="all, delete-orphan")
    cert_pending = relationship("TadaCertPending", back_populates="bot", cascade="all, delete-orphan")
    netwin_query_logs = relationship("NetwinQueryLog", back_populates="bot", cascade="all, delete-orphan")


class KeywordRule(Base):
    __tablename__ = "keyword_rules"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    keyword = Column(String(500), nullable=False)
    reply_message = Column(Text, nullable=False)
    reply_message_en = Column(Text, nullable=True)   # 英文回覆（選填）
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
    qas = relationship("KnowledgeQA", back_populates="doc", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """文件段落（取代 ChromaDB，直接存 SQLite）"""
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)

    doc = relationship("KnowledgeDoc", back_populates="chunks")


class KnowledgeQA(Base):
    """知識庫 Q&A 條目（每筆對應一組問答）"""
    __tablename__ = "knowledge_qas"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id"), nullable=False)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    question = Column(Text, nullable=False)
    keywords = Column(Text, nullable=True)   # 問題的其他說法或關鍵字（換行分隔）
    answer = Column(Text, nullable=False)
    order_index = Column(Integer, default=0)
    chunk_id = Column(Integer, ForeignKey("knowledge_chunks.id"), nullable=True)  # 對應的查詢用 chunk，編輯/刪除時需同步
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    doc = relationship("KnowledgeDoc", back_populates="qas")


class ConversationLog(Base):
    """Telegram 機器人對話日誌（近 7 日）"""
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="conversation_logs")


class NoAnswerLog(Base):
    """AI 無解答對話紀錄（近 7 日，觸發固定回覆時儲存）"""
    __tablename__ = "no_answer_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="no_answer_logs")


class UsageStat(Base):
    __tablename__ = "usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)   # 實際計費等效 token
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
    exception_keyword = Column(String(500), nullable=True)  # 例外關鍵字（逗號分隔），訊息含此字樣時不忽略
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="ignores")


# ── Telegram 機器人管理員名單（可下達 收回/undo 等管理指令）───────────────
class TelegramBotAdmin(Base):
    __tablename__ = "telegram_bot_admins"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    identifier = Column(String(255), nullable=False)   # Telegram user_id 或 @username
    note = Column(String(500), nullable=True)           # 備註說明
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="bot_admins")


# ── Telegram Live Messages ────────────────────────────────────────────────
class TelegramMessage(Base):
    """即時對話管控：記錄機器人有匹配的訊息（關鍵字或知識庫命中）"""
    __tablename__ = "telegram_messages"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    chat_type = Column(String(32), nullable=False)
    sender_id = Column(String(64), nullable=True)
    sender_name = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    telegram_message_id = Column(Integer, nullable=True)  # Telegram 原生訊息 ID（用於引用回覆）
    is_read = Column(Boolean, default=False)
    is_from_admin = Column(Boolean, default=False)   # True = 後台手動發送
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="live_messages")
    pending_reply = relationship("TelegramPendingReply", back_populates="message", uselist=False, cascade="all, delete-orphan")


class TelegramPendingReply(Base):
    """即時對話管控：管控模式下暫留的機器人回覆"""
    __tablename__ = "telegram_pending_replies"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    message_id = Column(Integer, ForeignKey("telegram_messages.id"), nullable=False)
    reply_text = Column(Text, nullable=False)
    status = Column(String(16), default="pending")   # pending / sent / discarded
    source = Column(String(16), default="knowledge_base")  # knowledge_base / keyword，發送時決定是否寫入 AI 對話日誌
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)

    message = relationship("TelegramMessage", back_populates="pending_reply")


# ── Whitelist Log ─────────────────────────────────────────────────────────
class WhitelistLog(Base):
    """後台白名單自動處理記錄"""
    __tablename__ = "whitelist_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    vendor_name = Column(String(64), nullable=False)   # 廠商代碼（從 Username 第一段取得）
    full_username = Column(String(255), nullable=True) # 完整代理帳號（如 Ogpro_GOLDBET9AU_MYR）
    ip_list = Column(Text, nullable=False)              # 換行分隔的 IP 列表
    status = Column(String(16), default="success")     # success / failed
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="whitelist_logs")


# ── 查輸贏回覆 Log ────────────────────────────────────────────────────────
class NetwinQueryLog(Base):
    """查輸贏回覆功能：每次偵測到查詢意圖時的處理紀錄。
    outcome：auto_replied（自動回覆）／no_account（偵測到意圖但擷取不到帳號）／
    zero_match（查無此玩家）／multi_match（比對到多筆玩家）／over_threshold（淨值超過門檻）／
    null_netwin（淨值查詢失敗，欄位為null）／api_error（呼叫API本身失敗）。
    除了 auto_replied 以外都算「未查詢的次數」（統計頁面用）。"""
    __tablename__ = "netwin_query_logs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    chat_type = Column(String(30), nullable=True)
    extracted_account = Column(String(255), nullable=True)
    match_count = Column(Integer, nullable=True)
    netwin_2d_thb = Column(Float, nullable=True)
    outcome = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="netwin_query_logs")


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


class AIRescueSetting(Base):
    """AI 機器人救援功能設定（每個 bot 一筆）"""
    __tablename__ = "ai_rescue_settings"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), unique=True, nullable=False)
    enabled = Column(Boolean, default=False)
    timeout_minutes = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="ai_rescue_setting")


class AIRescueCandidate(Base):
    """AI 救援候選訊息（AI 關閉的群組中收到的未回應訊息）"""
    __tablename__ = "ai_rescue_candidates"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False)
    chat_type = Column(String(32), nullable=True)
    telegram_message_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    sender_id = Column(String(64), nullable=True)
    sender_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_handled = Column(Boolean, default=False)
    handled_at = Column(DateTime, nullable=True)

    bot = relationship("TelegramBot", back_populates="rescue_candidates")


class TadaCertPending(Base):
    """TADA 認證文件查詢的追問待答狀態（每人同時只保留一筆，等待廠商回覆缺少的市場/遊戲資訊）"""
    __tablename__ = "tada_cert_pending"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False)
    prompt_message_id = Column(Integer, nullable=False)  # 機器人發出的追問訊息 id，比對 reply_to_message_id 用
    missing = Column(String(16), nullable=False)          # "market" 或 "game"：還缺哪一項資訊
    doc_keyword = Column(String(255), nullable=False)     # 命中的文件類型關鍵字（原文）
    doc_type = Column(String(32), nullable=False)         # "game"（需指定遊戲）或 "platform"（不分遊戲）
    candidate_markets = Column(Text, nullable=True)       # JSON 陣列字串，缺市場時的候選清單
    resolved_market = Column(String(64), nullable=True)   # 市場已確定後存這裡
    original_text = Column(Text, nullable=False)          # 使用者原始問句，逾時重問時要用
    is_chinese = Column(Boolean, default=True)             # 觸發當下問句的語言，後續追問/回覆都沿用同一語言，避免中英夾雜
    reasked = Column(Boolean, default=False)              # 是否已經逾時重問過一次
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    bot = relationship("TelegramBot", back_populates="cert_pending")


class NotifySetting(Base):
    """Freshdesk 工單通知設定：指定哪個機器人發通知到哪個群組"""
    __tablename__ = "notify_settings"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(64), nullable=False)
    chat_name = Column(String(255), nullable=False, default="")
    enabled = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TelegramGroupSetting(Base):
    """每個群組的 AI 問答開關設定"""
    __tablename__ = "telegram_group_settings"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bots.id"), nullable=False)
    chat_id = Column(String(50), nullable=False)
    ai_enabled = Column(Boolean, default=True)
    is_managed = Column(Boolean, default=False)               # 群組層級管控模式開關
    whitelist_vendor_check = Column(Boolean, default=False)   # 白名單廠商驗證開關
    whitelist_allowed_vendors = Column(Text, nullable=True)   # 允許廠商前綴，逗號分隔
    silent_no_answer = Column(Boolean, default=False)         # 找不到答案時靜默不回覆（仍記錄 log）
    single_vendor_mode = Column(Boolean, default=False)       # 單一總代理模式開關
    single_vendor_name = Column(String(128), nullable=True)  # 該群組的總代理名稱（訊息無帳號時使用）
    relaxed_bo_detect = Column(Boolean, default=False)        # Bo白名單添加放寬（規則四：無需「後台」字樣也可觸發）
    ticket_creation_enabled = Column(Boolean, default=True)    # 自動建立工單開關（關閉時完全不建單，Notify 也不會觸發）
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("TelegramBot", back_populates="group_settings")


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
