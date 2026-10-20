"""Registro de auditoría de acciones relevantes."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditLog

log = logging.getLogger("kai.audit")


def audit(db: Session, action: str, *, target: str | None = None, details: dict[str, Any] | None = None,
          client: str | None = None) -> None:
    db.add(AuditLog(action=action, target=target, details=details or {}, client=client))
    db.commit()
    log.info("audit action=%s target=%s", action, target)
