"""Punto de entrada de KAI Core (FastAPI)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1 import automation, chat, cowork, devices, integrations, memory, routines, settings as settings_api, system, tasks, updates, voice
from app.core.config import Settings, get_settings
from app.core.context import AppContext, ProviderFactory, default_provider_factory
from app.core.errors import KaiError, kai_error_handler
from app.core.logging import setup_logging
from app.core.state import EventBus, StateManager
from app.core.updates import Updater
from app.cowork.bridge import CoworkBridge
from app.database.session import Database
from app.routines.runner import scheduler_loop
from app.integrations.mcp_manager import McpManager, load_configs as load_mcp_configs
from app.security.access import AccessControlMiddleware, RateLimiter, load_or_create_token
from app.security.secrets import SecretStore
from app.voice.base import VoiceEngineError
from app.voice.service import VoiceService

log = logging.getLogger("kai")


async def _voice_error_handler(_, exc: Exception) -> JSONResponse:
    assert isinstance(exc, VoiceEngineError)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


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
    ctx.updater = Updater()
    ctx.mcp = McpManager(ctx.secrets, settings.logs_dir,
                         oauth_redirect_uri=f"http://127.0.0.1:{settings.port}/api/v1/integrations/oauth/callback")

    def load_mcp_configs_safe() -> list:
        with db.SessionLocal() as s:
            try:
                return load_mcp_configs(s)
            except Exception:  # noqa: BLE001 - una configuración rota no impide arrancar
                log.exception("No se pudo leer la configuración de integraciones")
                return []

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        key, source = ctx.secrets.get_api_key()
        if ctx.demo_mode:
            log.info("KAI Core %s iniciado en MODO DEMOSTRACIÓN (sin IA)", __version__)
        elif key is None:
            log.warning("KAI Core %s iniciado SIN clave de API: el chat real no está disponible", __version__)
        else:
            log.info("KAI Core %s iniciado. Clave de API desde: %s", __version__, source)
        await ctx.mcp.start(load_mcp_configs_safe())
        scheduler = asyncio.create_task(scheduler_loop(ctx), name="kai-routines") if settings.routines_enabled else None
        # Lista de aplicaciones del menú Inicio lista de antemano: «abrí Excel» responde al instante.
        from app.automation.apps_catalog import catalog

        warm = asyncio.create_task(asyncio.to_thread(catalog.apps), name="kai-apps-warm")
        # Actualización automática (app de escritorio): se baja sola y se instala cuando KAI está sin uso.
        from app.core.updates import IDLE_SECONDS
        from app.services.settings_service import get_preferences

        def auto_update_on() -> bool:
            with ctx.db.SessionLocal() as s:
                return get_preferences(s).auto_update

        auto = asyncio.create_task(ctx.updater.auto_loop(auto_update_on, lambda: ctx.idle_for(IDLE_SECONDS)),
                                   name="kai-auto-update")
        ctx.background_tasks.add(auto)
        auto.add_done_callback(ctx.background_tasks.discard)
        ctx.background_tasks.add(warm)
        warm.add_done_callback(ctx.background_tasks.discard)
        yield
        for t in [scheduler, *ctx.background_tasks]:
            if t is not None:
                t.cancel()
        await asyncio.gather(*(t for t in [scheduler, *ctx.background_tasks] if t is not None), return_exceptions=True)
        await ctx.mcp.stop()
        db.engine.dispose()

    app = FastAPI(
        title="KAI Core API",
        version=__version__,
        description="API local de KAI AI. Escucha sólo en 127.0.0.1 por defecto.",
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    app.state.cowork = CoworkBridge(settings.cowork_dir, settings.max_upload_mb * 1024 * 1024)
    app.state.voice = VoiceService(settings.voice_models_dir, bus)

    app.add_exception_handler(KaiError, kai_error_handler)
    app.add_exception_handler(VoiceEngineError, _voice_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_middleware(AccessControlMiddleware, token=ctx.access_token, allowed_origins=settings.effective_origins,
                       db_factory=db.SessionLocal)
    app.add_middleware(CORSMiddleware, allow_origins=settings.effective_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-KAI-Token", "Authorization"])

    for r in (system.router, chat.router, settings_api.router, tasks.router, cowork.router, voice.router, memory.router,
              automation.router, devices.router, integrations.router, routines.router, updates.router):
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
    import os
    import sys

    import uvicorn

    for stream in (sys.stdout, sys.stderr):  # consola de Windows: evitar errores de codificación
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    s = get_settings()
    if not os.environ.get("KAI_HOST"):
        # Acceso remoto activado desde la interfaz: se escucha en la red (sólo se aceptan clientes de
        # redes privadas con un dispositivo vinculado; ver security/access.py).
        from app.database.session import Database
        from app.security.devices import remote_enabled

        s.ensure_dirs()
        probe = Database(s.database_url)
        probe.create_all()
        with probe.SessionLocal() as db:
            if remote_enabled(db):
                s = s.model_copy(update={"host": "0.0.0.0"})
        probe.engine.dispose()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("KAI Core escucha en %s: acepta sólo redes privadas y dispositivos vinculados. "
                    "No abras el puerto %s en el router.", s.host, s.port)
    app = create_app(s)
    server = uvicorn.Server(uvicorn.Config(app, host=s.host, port=s.port, log_level=s.log_level.lower()))
    # La app de escritorio pasa un token para pedir un cierre ordenado (POST /api/v1/system/shutdown).
    app.state.shutdown_token = os.environ.get("KAI_SHUTDOWN_TOKEN") or None
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    parent = os.environ.get("KAI_PARENT_PID", "")
    if parent.isdigit():
        from app.core.watchdog import watch_parent

        watch_parent(int(parent), app.state.request_shutdown)
    updating = {"on": False}

    def _after_update_launch() -> None:
        updating["on"] = True
        app.state.request_shutdown()

    app.state.ctx.updater.after_launch = _after_update_launch
    server.run()
    if updating["on"]:
        from app.core.updates import UPDATE_EXIT_CODE

        sys.exit(UPDATE_EXIT_CODE)


if __name__ == "__main__":
    run()
