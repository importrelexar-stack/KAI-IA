from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatusLiteral = Literal["pending", "awaiting_approval", "running", "completed", "failed", "cancelled"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    priority: int = Field(default=2, ge=1, le=3)
    requires_approval: bool = False
    project_id: str | None = Field(default=None, max_length=32)
    depends_on: list[str] = Field(default_factory=list, max_length=30)


class TaskTransition(BaseModel):
    status: TaskStatusLiteral
    note: str | None = Field(default=None, max_length=2000)
    result: str | None = Field(default=None, max_length=50_000)
    error: str | None = Field(default=None, max_length=10_000)


class TaskApproval(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    status: TaskStatusLiteral
    priority: int
    requires_approval: bool
    tools_used: list[str]
    result: str | None
    error: str | None
    approvals: list[dict[str, Any]]
    history: list[dict[str, Any]]
    project_id: str | None = None
    depends_on: list[str] = []
    created_by: str = "user"
    created_at: datetime
    updated_at: datetime
