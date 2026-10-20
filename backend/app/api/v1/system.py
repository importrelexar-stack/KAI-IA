from __future__ import annotations

import asyncio
import hmac
import logging
import platform
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import __version__
from app.agents.catalog import list_agents
from app.api.deps import get_ctx, get_db
from app.api.v1.settings import api_key_status
from app.core.context import AppContext
from app.core.errors import KaiError
from app.models.entities import AuditLog
from app.security.access import LOCAL_HOSTS
from app.services.settings_service import get_preferences
from app.services.usage_service import usage_for_day

router = APIRouter(tags=["system"])
log = logging.getLogger(__name__)
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/health", summary="Comprobación de vida")
def health(ctx: Ctx) -> dict:
    return {"status": "ok", "version": __version__, "assistant": ctx.state.snapshot()}


@router.get("/system/status", summary="Estado del sistema")
def system_status(ctx: Ctx, db: Db) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    prefs = get_preferences(db)
    usage = usage_for_day(db)
    provider = ctx.provider()
    return {
        "version": __version__,
        "uptime_seconds": int(time.time() - ctx.started_at),
        "platform": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "database": {"ok": db_ok, "fts5": ctx.db.features.get("fts5", False)},
        "assistant": ctx.state.snapshot(),
        "provider": {"name": provider.name, "configured": provider.configured, "model": prefs.model,
                     "effort": prefs.effort, "demo_mode": ctx.demo_mode},
        "api_key": api_key_status(ctx).model_dump(),
        "usage_today": usage,
        "budget": {"daily_tokens": prefs.daily_token_budget,
                   "remaining": max(0, prefs.daily_token_budget - usage["total_tokens"])
                   if prefs.daily_token_budget else None},
        "realtime_clients": ctx.bus.subscribers,
        "features": {
            "chat": "available" if provider.configured else "needs_api_key",
            "history": "available",
            "tasks": "available",
            "cowork_bridge": "manual",
            "voice": "available",
            "agents": "available" if prefs.agents_enabled else "disabled",
            "memory": "available" if prefs.memory_enabled else "disabled",
            "automation": "available",
            "files": "available",
            "attachments": "available",
            "android": "beta",
        },
    }


@router.post("/system/shutdown", include_in_schema=False)
def shutdown(request: Request) -> dict:
    """Cierre ordenado pedido por la app de escritorio (requiere el token que ella generó)."""
    token = getattr(request.app.state, "shutdown_token", None)
    supplied = request.headers.get("x-kai-shutdown", "")
    if not token or not hmac.compare_digest(supplied, token):
        raise KaiError("No autorizado.", code="forbidden", status_code=403)
    request.app.state.request_shutdown()
    log.info("Cierre ordenado solicitado por la app de escritorio")
    return {"status": "stopping"}


@router.get("/agents", summary="Catálogo de agentes y su estado real")
def agents(db: Db) -> list[dict]:
    return list_agents(get_preferences(db))


@router.get("/audit", summary="Registro de auditoría")
def audit_log(db: Db, limit: int = 100) -> list[dict]:
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))).scalars()
    return [{"id": r.id, "action": r.action, "target": r.target, "details": r.details, "client": r.client,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.websocket("/ws/events")
async def events(ws: WebSocket) -> None:
    ctx: AppContext = ws.app.state.ctx
    origin = ws.headers.get("origin")
    client_host = ws.client.host if ws.client else ""
    if client_host in LOCAL_HOSTS:
        if origin and origin not in ctx.settings.effective_origins:
            await ws.close(code=1008)
            return
    else:
        from app.security.access import authorize_remote, split_host

        result = authorize_remote(ctx.db.SessionLocal, ctx.access_token, client_host,
                                  split_host(ws.headers.get("host", "")), ws.query_params.get("token", ""),
                                  "GET", "/api/v1/ws/events")
        if not result.ok:
            await ws.close(code=1008)
            return
    await ws.accept()
    queue = ctx.bus.subscribe()
    try:
        await ws.send_json({"type": "state", **ctx.state.snapshot()})
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        ctx.bus.unsubscribe(queue)
