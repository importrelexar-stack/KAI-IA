from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=32)
    stream: bool = True
    channel: Literal["text", "voice"] = "text"

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje está vacío.")
        return v


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    model: str | None = None
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_events: list[dict] | None = None
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut
    served_by_fallback: bool = False


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)
