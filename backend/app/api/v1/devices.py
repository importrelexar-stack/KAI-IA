from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import segno
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db, require_local
from app.core.context import AppContext
from app.core.errors import KaiError
from app.models.entities import Device
from app.security import devices as dev
from app.security.access import RateLimiter
from app.security.audit import audit

router = APIRouter(prefix="/devices", tags=["devices"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]
Local = Depends(require_local)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    platform: str
    revoked: bool
    last_seen_at: datetime | None
    last_ip: str | None
    created_at: datetime


class PairIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)
    name: str = Field(default="Teléfono", min_length=1, max_length=80)
    platform: str = Field(default="android", max_length=32)


class RemoteIn(BaseModel):
    enabled: bool


def _remote_status(ctx: AppContext, db: Session) -> dict[str, Any]:
    enabled = dev.remote_enabled(db)
    bound = ctx.settings.host not in ("127.0.0.1", "localhost", "::1")
    return {
        "enabled": enabled,
        "listening_on_network": bound,
        "restart_required": enabled != bound,
        "port": ctx.settings.port,
        "addresses": dev.local_addresses(),
    }


@router.get("/remote", summary="Estado del acceso remoto", dependencies=[Local])
def remote_status(ctx: Ctx, db: Db) -> dict[str, Any]:
    return _remote_status(ctx, db)


@router.put("/remote", summary="Activar o desactivar el acceso remoto (requiere reiniciar KAI)", dependencies=[Local])
def set_remote(body: RemoteIn, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    dev.set_remote_enabled(db, body.enabled)
    audit(db, "devices.remote", details={"enabled": body.enabled}, client=client_id(request))
    return _remote_status(ctx, db)


@router.post("/pairing", summary="Generar un código de vinculación (5 minutos, un solo uso)", dependencies=[Local])
def create_pairing(request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    status = _remote_status(ctx, db)
    if not status["enabled"]:
        raise KaiError("Primero activá el acceso remoto.", code="remote_disabled", status_code=409)
    code, expires = dev.create_pairing_code(db)
    urls = [f"http://{a}:{ctx.settings.port}" for a in status["addresses"]]
    payload = f"kai://pair?c={code}&u={','.join(urls)}"
    qr = segno.make(payload, error="m")
    audit(db, "devices.pairing", client=client_id(request))
    return {"code": code, "expires_at": expires.isoformat(), "urls": urls, "payload": payload,
            "qr_svg": qr.svg_inline(scale=6, dark="#05070b", light="#ffffff"), **status}


@router.post("/pair", summary="Vincular un dispositivo con el código (lo usa la app del teléfono)")
def pair(body: PairIn, request: Request, db: Db) -> dict[str, Any]:
    ip = request.client.host if request.client else None
    limiter = getattr(request.app.state, "pair_limiter", None)
    if limiter is None:
        limiter = request.app.state.pair_limiter = RateLimiter(limit=5)
    if not limiter.check(ip or "?"):
        raise KaiError("Demasiados intentos. Esperá un minuto.", code="rate_limited", status_code=429)
    device, token = dev.pair_device(db, body.code, body.name, body.platform, ip)
    audit(db, "devices.paired", target=device.id, details={"name": device.name, "ip": ip}, client=ip)
    return {"token": token, "device_id": device.id, "name": device.name}


@router.get("/me", summary="El dispositivo que hace la consulta")
def me(request: Request) -> dict[str, Any]:
    device = getattr(request.state, "device", None)
    if device is None:
        raise KaiError("Esta consulta es para dispositivos vinculados.", code="not_a_device", status_code=400)
    return {"id": device.id, "name": device.name, "platform": device.platform}


@router.delete("/me", status_code=204, summary="El teléfono se desvincula a sí mismo (revoca su token)")
def unpair_me(request: Request, db: Db) -> None:
    device = getattr(request.state, "device", None)
    if device is None:
        raise KaiError("Esta acción es para dispositivos vinculados.", code="not_a_device", status_code=400)
    dev.revoke(db, device.id)
    audit(db, "devices.unpaired", target=device.id, details={"name": device.name}, client=client_id(request))


@router.get("", response_model=list[DeviceOut], summary="Dispositivos vinculados", dependencies=[Local])
def list_devices(db: Db) -> list[Device]:
    return list(db.execute(select(Device).order_by(Device.created_at.desc())).scalars())


@router.delete("/{device_id}", response_model=DeviceOut, summary="Revocar un dispositivo", dependencies=[Local])
def revoke_device(device_id: str, request: Request, db: Db) -> Device:
    device = dev.revoke(db, device_id)
    audit(db, "devices.revoked", target=device_id, details={"name": device.name}, client=client_id(request))
    return device
