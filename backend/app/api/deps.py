from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.context import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.ctx.db.session()


def client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"
