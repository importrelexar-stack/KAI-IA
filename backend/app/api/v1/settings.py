from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.core.context import AppContext
from app.schemas.settings import ApiKeyIn, ApiKeyStatus, PreferencesUpdate, SettingsOut, ValidationOut
from app.security.audit import audit
from app.security.secrets import mask_key
from app.services.settings_service import get_preferences, update_preferences

router = APIRouter(tags=["settings"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]


def api_key_status(ctx: AppContext) -> ApiKeyStatus:
    key, source = ctx.secrets.get_api_key()
    return ApiKeyStatus(configured=key is not None, source=source, masked=mask_key(key),
                        keyring_available=ctx.secrets.keyring_available,
                        persisted=source in ("env", "keyring"))


@router.get("/settings", response_model=SettingsOut, summary="Ver configuración")
def read_settings(ctx: Ctx, db: Db) -> SettingsOut:
    return SettingsOut(preferences=get_preferences(db), api_key=api_key_status(ctx), demo_mode=ctx.demo_mode)


@router.put("/settings", response_model=SettingsOut, summary="Actualizar preferencias")
def write_settings(body: PreferencesUpdate, request: Request, ctx: Ctx, db: Db) -> SettingsOut:
    prefs, changed = update_preferences(db, body)
    audit(db, "settings.update", details={"fields": changed}, client=client_id(request))
    return SettingsOut(preferences=prefs, api_key=api_key_status(ctx), demo_mode=ctx.demo_mode)


@router.put("/settings/api-key", response_model=ApiKeyStatus, summary="Guardar la clave de API de Anthropic")
def set_api_key(body: ApiKeyIn, request: Request, ctx: Ctx, db: Db) -> ApiKeyStatus:
    source = ctx.secrets.set_api_key(body.api_key)
    ctx.reset_provider()
    audit(db, "settings.api_key.set", details={"storage": source}, client=client_id(request))
    return api_key_status(ctx)


@router.delete("/settings/api-key", response_model=ApiKeyStatus, summary="Borrar la clave guardada")
def delete_api_key(request: Request, ctx: Ctx, db: Db) -> ApiKeyStatus:
    ctx.secrets.delete_api_key()
    ctx.reset_provider()
    audit(db, "settings.api_key.delete", client=client_id(request))
    return api_key_status(ctx)


@router.post("/settings/api-key/test", response_model=ValidationOut, summary="Probar la clave (no consume tokens)")
async def test_api_key(ctx: Ctx) -> ValidationOut:
    result = await ctx.provider().validate()
    return ValidationOut(ok=result.ok, message=result.message)
