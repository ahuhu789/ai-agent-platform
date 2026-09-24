from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------- Message ----------
class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


# ---------- Conversation ----------
class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, examples=["Hỏi đáp Tuyển dụng"])
    user_id: Optional[str] = Field(default=None, examples=["default_user"])


class ConversationOut(BaseModel):
    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = []


# ---------- Chat ----------
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = Field(
        default=None,
        description="Nếu để trống, hệ thống tự tạo conversation mới.",
    )
    message: str = Field(..., min_length=1, examples=["Có bao nhiêu ứng viên đang chờ phỏng vấn?"])
    user_id: Optional[str] = Field(default=None, description="ID người dùng (nếu hệ thống có auth).")


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    success: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    messages: List[MessageOut] = []
