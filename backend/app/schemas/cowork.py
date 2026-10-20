from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CoworkPrepareRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=20_000)
    context: str = Field(default="", max_length=50_000)
    deliverables: list[str] = Field(default_factory=list, max_length=30)
    constraints: list[str] = Field(default_factory=list, max_length=30)
    folders: list[str] = Field(default_factory=list, max_length=30)
    conversation_id: str | None = Field(default=None, max_length=32)
    include_messages: int = Field(default=0, ge=0, le=50)


class CoworkResultIn(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)


class CoworkHandoffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    objective: str
    payload: dict[str, Any]
    instructions_md: str
    status: str
    result_text: str | None
    result_files: list[dict[str, Any]]
    conversation_id: str | None
    created_at: datetime
    updated_at: datetime


class CoworkStatus(BaseModel):
    adapter: str
    official_api: bool
    can_submit: bool
    can_fetch_results: bool
    description: str
    untrusted_notice: str
