from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=32)
    stream: bool = True
    channel: Literal["text", "voice"] = "text"
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _not_blank(self) -> "ChatRequest":
        if not self.message.strip() and not self.attachment_ids:
            raise ValueError("El mensaje está vacío.")
        return self


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    media_type: str
    size: int
    chars: int = 0


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
    attachments: list[dict] | None = None
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
