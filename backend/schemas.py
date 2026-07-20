from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# ── User ──────────────────────────────────────────
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: str = "viewer"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── TelegramBot ────────────────────────────────────
class BotBase(BaseModel):
    name: str
    token: str


class BotCreate(BotBase):
    pass


class BotUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    is_enabled: Optional[bool] = None
    is_managed: Optional[bool] = None
    whitelist_enabled: Optional[bool] = None


class BotOut(BotBase):
    id: int
    is_enabled: bool
    is_managed: bool = False
    whitelist_enabled: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Telegram Live ──────────────────────────────────
class TelegramPendingReplyOut(BaseModel):
    id: int
    reply_text: str
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TelegramMessageOut(BaseModel):
    id: int
    chat_id: str
    chat_name: str
    chat_type: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    text: str
    is_read: bool
    is_from_admin: bool
    created_at: datetime
    pending_reply: Optional[TelegramPendingReplyOut] = None

    class Config:
        from_attributes = True


class ChatGroupOut(BaseModel):
    chat_id: str
    chat_name: str
    chat_type: str
    last_message_at: datetime
    unread_count: int
    pending_count: int


class LiveSendRequest(BaseModel):
    bot_id: int
    chat_id: str
    text: str


class PendingReplyUpdate(BaseModel):
    reply_text: str


# ── WhitelistLog ───────────────────────────────────
class WhitelistLogOut(BaseModel):
    id: int
    chat_name: str
    vendor_name: str
    ip_list: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── KeywordRule ────────────────────────────────────
class RuleBase(BaseModel):
    bot_id: int
    keyword: str
    reply_message: str
    reply_message_en: Optional[str] = None


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    bot_id: Optional[int] = None
    keyword: Optional[str] = None
    reply_message: Optional[str] = None
    reply_message_en: Optional[str] = None
    is_enabled: Optional[bool] = None


class RuleOut(RuleBase):
    id: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── KnowledgeDoc ───────────────────────────────────
class DocOut(BaseModel):
    id: int
    bot_id: int
    original_filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    is_enabled: bool
    created_at: datetime
    qa_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DocUpdate(BaseModel):
    bot_id: Optional[int] = None
    is_enabled: Optional[bool] = None


# ── Stats ──────────────────────────────────────────
class DailyStatOut(BaseModel):
    date: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    request_count: int


class BotStatOut(BaseModel):
    bot_id: int
    bot_name: str
    total_tokens: int
    request_count: int


class StatsSummary(BaseModel):
    total_tokens_today: int
    total_tokens_month: int
    total_requests_today: int
    total_requests_month: int
    daily: List[DailyStatOut]
    by_bot: List[BotStatOut]


# ── TeamsBot ───────────────────────────────────────
class TeamsBotBase(BaseModel):
    name: str
    app_id: str
    app_password: str
    tenant_id: Optional[str] = None


class TeamsBotCreate(TeamsBotBase):
    pass


class TeamsBotUpdate(BaseModel):
    name: Optional[str] = None
    app_id: Optional[str] = None
    app_password: Optional[str] = None
    tenant_id: Optional[str] = None
    is_enabled: Optional[bool] = None


class TeamsBotOut(BaseModel):
    id: int
    name: str
    app_id: str
    tenant_id: Optional[str]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── TeamsKeywordRule ───────────────────────────────
class TeamsRuleBase(BaseModel):
    bot_id: int
    keyword: str
    reply_message: str


class TeamsRuleCreate(TeamsRuleBase):
    pass


class TeamsRuleUpdate(BaseModel):
    bot_id: Optional[int] = None
    keyword: Optional[str] = None
    reply_message: Optional[str] = None
    is_enabled: Optional[bool] = None


class TeamsRuleOut(TeamsRuleBase):
    id: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── TeamsKnowledgeDoc ──────────────────────────────
class TeamsDocOut(BaseModel):
    id: int
    bot_id: int
    original_filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TeamsDocUpdate(BaseModel):
    bot_id: Optional[int] = None
    is_enabled: Optional[bool] = None


# ── TelegramIgnore ─────────────────────────────────
class TelegramIgnoreCreate(BaseModel):
    bot_id: int
    identifier: str
    note: Optional[str] = None


class TelegramIgnoreUpdate(BaseModel):
    identifier: Optional[str] = None
    note: Optional[str] = None
    is_enabled: Optional[bool] = None


class TelegramIgnoreOut(BaseModel):
    id: int
    bot_id: int
    identifier: str
    note: Optional[str]
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── TeamsIgnore ────────────────────────────────────
class TeamsIgnoreCreate(BaseModel):
    bot_id: int
    identifier: str
    note: Optional[str] = None


class TeamsIgnoreUpdate(BaseModel):
    identifier: Optional[str] = None
    note: Optional[str] = None
    is_enabled: Optional[bool] = None


class TeamsIgnoreOut(BaseModel):
    id: int
    bot_id: int
    identifier: str
    note: Optional[str]
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── CopilotBot ─────────────────────────────────────
class CopilotBotCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CopilotBotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None


class CopilotBotOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── CopilotKeywordRule ─────────────────────────────
class CopilotRuleCreate(BaseModel):
    bot_id: int
    keyword: str
    reply_message: str


class CopilotRuleUpdate(BaseModel):
    keyword: Optional[str] = None
    reply_message: Optional[str] = None
    is_enabled: Optional[bool] = None


class CopilotRuleOut(BaseModel):
    id: int
    bot_id: int
    keyword: str
    reply_message: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── CopilotKnowledgeDoc ────────────────────────────
class CopilotDocOut(BaseModel):
    id: int
    bot_id: int
    original_filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CopilotDocUpdate(BaseModel):
    is_enabled: Optional[bool] = None


# ── CopilotQuery ───────────────────────────────────
class CopilotQueryRequest(BaseModel):
    bot_id: int
    question: str
    conversation_id: str = "unknown"
    conversation_name: str = "未知對話"
