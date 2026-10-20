"""Registro de actividad con rotación y redacción de secretos."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(x-api-key|authorization)(\"?\s*[:=]\s*\"?)([^\s\"']+)"),
]


def redact(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub("sk-ant-***", text)
    return _SECRET_PATTERNS[1].sub(r"\1\2***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - nunca romper el logging
            return True
        record.msg = redact(msg)
        record.args = None
        return True


def setup_logging(level: str, logs_dir: Path | None) -> None:
    root = logging.getLogger()
    if getattr(root, "_kai_configured", False):
        return
    root.setLevel(level.upper())
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(logs_dir / "kai.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        )
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    root._kai_configured = True  # type: ignore[attr-defined]
