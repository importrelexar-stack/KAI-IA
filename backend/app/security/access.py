"""Protección de endpoints.

Fase 1: KAI Core escucha sólo en 127.0.0.1. Se bloquean:
- Solicitudes con encabezado Host ajeno (protección contra DNS rebinding).
- Solicitudes desde páginas web con Origin no autorizado (CSRF desde el navegador).
- Clientes que no sean locales, salvo que presenten el token de acceso
  (`data/access_token`), preparado para el emparejamiento con Android (Fase 5).
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_ALLOWED_HOST_NAMES = {"127.0.0.1", "localhost", "[::1]", "testserver", "tauri.localhost"}


def load_or_create_token(path: Path) -> str:
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class AccessControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str, allowed_origins: list[str]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._token = token
        self._origins = set(allowed_origins)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        host_header = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
        if host_header and host_header not in _ALLOWED_HOST_NAMES:
            return _error(403, "forbidden_host", "Host no permitido.")

        origin = request.headers.get("origin")
        if origin and origin not in self._origins:
            return _error(403, "forbidden_origin", "Origen no autorizado.")

        client_host = request.client.host if request.client else ""
        if client_host not in LOCAL_HOSTS and request.url.path.startswith("/api/"):
            supplied = request.headers.get("x-kai-token") or ""
            if not hmac.compare_digest(supplied, self._token):
                return _error(401, "unauthorized", "Se requiere un token de acceso válido.")
        return await call_next(request)


class RateLimiter:
    """Ventana deslizante en memoria por cliente."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
