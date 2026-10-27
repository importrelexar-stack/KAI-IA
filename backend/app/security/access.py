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


def split_host(host_header: str) -> str:
    h = (host_header or "").strip().lower()
    if h.startswith("["):  # IPv6 [::1]:8765
        return h[: h.find("]") + 1] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


class RemoteAuth:
    """Resultado de autorizar un cliente que no es local."""

    def __init__(self, ok: bool, status: int = 200, code: str = "", message: str = "",
                 device: object | None = None, admin: bool = False) -> None:
        self.ok, self.status, self.code, self.message = ok, status, code, message
        self.device, self.admin = device, admin


def authorize_remote(db_factory, admin_token: str, client_host: str, host: str, credential: str,  # type: ignore[no-untyped-def]
                     method: str, path: str) -> RemoteAuth:
    from app.security import devices

    if not devices.is_private_address(client_host):
        return RemoteAuth(False, 403, "public_network", "KAI sólo acepta conexiones desde tu red privada.")
    db = db_factory()
    try:
        if not devices.remote_enabled(db):
            return RemoteAuth(False, 403, "remote_disabled",
                              "El acceso remoto está desactivado en KAI (Configuración → Dispositivos).")
        if host and not devices.host_header_allowed_remote(host):
            return RemoteAuth(False, 403, "forbidden_host", "Host no permitido.")
        if credential and hmac.compare_digest(credential, admin_token):
            return RemoteAuth(True, admin=True)
        if path == "/api/v1/devices/pair" and method == "POST":
            return RemoteAuth(True)
        device = devices.authenticate(db, credential, client_host) if credential else None
        if device is None:
            return RemoteAuth(False, 401, "unauthorized", "Se requiere un dispositivo vinculado.")
        if not devices.device_may(method, path):
            return RemoteAuth(False, 403, "device_forbidden",
                              "Esa acción sólo se puede hacer desde la computadora donde corre KAI.")
        return RemoteAuth(True, device=device)
    finally:
        db.close()


def bearer(request_headers) -> str:  # type: ignore[no-untyped-def]
    auth = request_headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request_headers.get("x-kai-token") or ""


class AccessControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str, allowed_origins: list[str], db_factory) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._token = token
        self._origins = set(allowed_origins)
        self._db_factory = db_factory

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        host_header = request.headers.get("host") or ""
        host = split_host(host_header)
        client_host = request.client.host if request.client else ""
        origin = request.headers.get("origin")
        request.state.device = None

        if client_host in LOCAL_HOSTS:
            if host and host not in _ALLOWED_HOST_NAMES:
                return _error(403, "forbidden_host", "Host no permitido.")
            if origin and origin not in self._origins:
                return _error(403, "forbidden_origin", "Origen no autorizado.")
            return await call_next(request)

        # Cliente remoto (teléfono vinculado o navegador en la red privada)
        if origin and origin not in self._origins and origin != f"http://{host_header.lower()}":
            return _error(403, "forbidden_origin", "Origen no autorizado.")
        path = request.url.path
        if not path.startswith("/api/"):
            # Interfaz web estática: sólo desde la red privada y con el acceso remoto activado.
            result = authorize_remote(self._db_factory, self._token, client_host, host, self._token,
                                      request.method, path)
        else:
            result = authorize_remote(self._db_factory, self._token, client_host, host, bearer(request.headers),
                                      request.method, path)
        if not result.ok:
            return _error(result.status, result.code, result.message)
        request.state.device = result.device
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
