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
    device = getattr(request.state, "device", None)
    if device is not None:
        return f"device:{device.name}"
    return request.client.host if request.client else "unknown"


def require_local(request: Request) -> None:
    """Sólo desde la propia computadora (administración de dispositivos y acceso remoto)."""
    from app.core.errors import KaiError
    from app.security.access import LOCAL_HOSTS

    if (request.client.host if request.client else "") not in LOCAL_HOSTS:
        raise KaiError("Esta acción sólo se puede hacer desde la computadora donde corre KAI.",
                       code="local_only", status_code=403)
