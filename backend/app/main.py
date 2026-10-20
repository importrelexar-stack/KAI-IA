"""Punto de entrada de KAI Core (FastAPI)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1 import chat, cowork, settings as settings_api, system, tasks
from app.core.config import Settings, get_settings
from app.core.context import AppContext, ProviderFactory, default_provider_factory
from app.core.errors import KaiError, kai_error_handler
from app.core.logging import setup_logging
from app.core.state import EventBus, StateManager
from app.cowork.bridge import CoworkBridge
from app.database.session import Database
from app.security.access import AccessControlMiddleware, RateLimiter, load_or_create_token
from app.security.secrets import SecretStore

log = logging.getLogger("kai")


async def _validation_handler(_, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg", "")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error",
                                                            "message": "Datos inválidos.", "details": errors}})


def create_app(settings: Settings | None = None, *, provider_factory: ProviderFactory | None = None,
               secrets: SecretStore | None = None, configure_logging: bool = True) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    if configure_logging:
        setup_logging(settings.log_level, settings.logs_dir)

    db = Database(settings.database_url)
    db.create_all()
    bus = EventBus()
    ctx = AppContext(
        settings=settings,
        db=db,
        secrets=secrets or SecretStore(settings.anthropic_api_key, use_keyring=settings.use_keyring),
        bus=bus,
        state=StateManager(bus),
        access_token=load_or_create_token(settings.data_dir / "access_token"),
        chat_limiter=RateLimiter(settings.chat_rate_limit_per_minute),
        provider_factory=provider_factory or default_provider_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        key, source = ctx.secrets.get_api_key()
        if ctx.demo_mode:
            log.info("KAI Core %s iniciado en MODO DEMOSTRACIÓN (sin IA)", __version__)
        elif key is None:
            log.warning("KAI Core %s iniciado SIN clave de API: el chat real no está disponible", __version__)
        else:
            log.info("KAI Core %s iniciado. Clave de API desde: %s", __version__, source)
        yield
        db.engine.dispose()

    app = FastAPI(
        title="KAI Core API",
        version=__version__,
        description="API local de KAI AI. Escucha sólo en 127.0.0.1 por defecto.",
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    app.state.cowork = CoworkBridge(settings.cowork_dir, settings.max_upload_mb * 1024 * 1024)

    app.add_exception_handler(KaiError, kai_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_middleware(AccessControlMiddleware, token=ctx.access_token, allowed_origins=settings.allowed_origins)
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-KAI-Token"])

    for r in (system.router, chat.router, settings_api.router, tasks.router, cowork.router):
        app.include_router(r, prefix="/api/v1")

    _mount_frontend(app, settings.web_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """En producción, KAI Core sirve la interfaz compilada (apps/web/dist)."""
    index = dist / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        def no_frontend() -> JSONResponse:
            return JSONResponse({"message": "KAI Core activo. La interfaz no está compilada: ejecutá "
                                            "scripts\\build-web.ps1 o usá el modo desarrollo (puerto 5173).",
                                 "docs": "/docs"})
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    dist_resolved = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Ruta inexistente."}})  # type: ignore[return-value]
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist_resolved in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


def run() -> None:
    import uvicorn

    s = get_settings()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("KAI_HOST=%s expone KAI Core fuera de este equipo. No lo publiques en Internet.", s.host)
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level=s.log_level.lower())


if __name__ == "__main__":
    run()
