"""Integraciones (Fase 6): navegación web y servidores MCP. Sólo se administran desde la PC."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db, require_local
from app.core.context import AppContext
from app.core.errors import KaiError, NotFoundError
from app.integrations.mcp_manager import McpManager, SecretTokenStorage, ServerConfig, load_configs, new_server_id, save_configs
from app.security.audit import audit
from app.services.settings_service import get_preferences, update_preferences

router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_local)])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class McpServerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    transport: Literal["stdio", "http"]
    command: str = Field(default="", max_length=500)
    args: list[str] = Field(default_factory=list, max_length=40)
    env: dict[str, str] = Field(default_factory=dict, description="Variables no sensibles")
    secret_env: dict[str, str] = Field(default_factory=dict,
                                       description="Variables sensibles (claves): van al almacén de credenciales")
    url: str = Field(default="", max_length=500)
    token: str | None = Field(default=None, max_length=4000, description="Bearer token (servidores HTTP)")
    oauth: bool = Field(default=False, description="Iniciar sesión con OAuth (servidores HTTP)")

    @field_validator("env", "secret_env")
    @classmethod
    def _env_names(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 30:
            raise ValueError("Demasiadas variables.")
        for k, val in v.items():
            if not _ENV_NAME.match(k) or len(val) > 4000:
                raise ValueError(f"Variable inválida: {k}")
        return v

    @model_validator(mode="after")
    def _transport_fields(self) -> "McpServerIn":
        if self.transport == "stdio" and not self.command.strip():
            raise ValueError("Indicá el comando del servidor (ej.: npx, uvx o la ruta del programa).")
        if self.transport == "http" and not re.match(r"^https?://", self.url.strip()):
            raise ValueError("Indicá la URL del servidor (http:// o https://).")
        if self.oauth and (self.transport != "http" or self.token):
            raise ValueError("OAuth es sólo para servidores HTTP y reemplaza al token.")
        if self.transport == "http" and self.url.startswith("http://") and not re.match(
                r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)", self.url):
            raise ValueError("Para servidores remotos usá https:// (el token viajaría sin cifrar).")
        return self


class McpServerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=40)


class SecretsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret_env: dict[str, str] = Field(default_factory=dict)
    token: str | None = Field(default=None, max_length=4000)

    _names = field_validator("secret_env")(McpServerIn._env_names.__func__)  # type: ignore[attr-defined]


class ToolLevelIn(BaseModel):
    level: Literal["allow", "ask", "deny", "default"]


class WebIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_search_enabled: bool | None = None
    web_fetch_enabled: bool | None = None


def _manager(ctx: AppContext) -> McpManager:
    return ctx.mcp


def _status(ctx: AppContext, c: ServerConfig) -> dict[str, Any]:
    conn = _manager(ctx).connections.get(c.id)
    tools = []
    if conn is not None:
        for t in conn.tools:
            tools.append({"name": t.name, "description": t.description[:300], "read_only": t.read_only,
                          "destructive": t.destructive, "level": McpManager.level(c, t),
                          "custom": t.name in c.tool_levels})
    return {
        "id": c.id, "name": c.name, "transport": c.transport, "command": c.command, "args": c.args,
        "env": c.env, "secret_env": c.secret_env, "url": c.url, "has_token": c.has_token, "oauth": c.oauth,
        "enabled": c.enabled, "auth_url": conn.auth_url if conn else None,
        "status": conn.status if conn else ("stopped" if not c.enabled else "error"),
        "error": conn.error if conn else None, "server_info": conn.server_info if conn else "",
        "tools": tools,
    }


def _find(configs: list[ServerConfig], server_id: str) -> ServerConfig:
    found = next((c for c in configs if c.id == server_id), None)
    if found is None:
        raise NotFoundError("La integración no existe.")
    return found


@router.get("", summary="Integraciones: web y servidores MCP")
def overview(ctx: Ctx, db: Db) -> dict[str, Any]:
    p = get_preferences(db)
    return {
        "web": {"web_search_enabled": p.web_search_enabled, "web_fetch_enabled": p.web_fetch_enabled},
        "mcp": [_status(ctx, c) for c in load_configs(db)],
        "secure_storage": ctx.secrets.keyring_available,
    }


@router.put("/web", summary="Activar búsqueda y lectura web")
def set_web(body: WebIn, request: Request, db: Db) -> dict[str, Any]:
    from app.schemas.settings import PreferencesUpdate

    p, _ = update_preferences(db, PreferencesUpdate(**body.model_dump(exclude_none=True)))
    audit(db, "integrations.web", details=body.model_dump(exclude_none=True), client=client_id(request))
    return {"web_search_enabled": p.web_search_enabled, "web_fetch_enabled": p.web_fetch_enabled}


@router.post("/mcp", status_code=201, summary="Agregar un servidor MCP")
async def add_server(body: McpServerIn, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    configs = load_configs(db)
    if len(configs) >= 20:
        raise KaiError("Máximo 20 integraciones.", code="too_many", status_code=409)
    if any(c.name.lower() == body.name.strip().lower() for c in configs):
        raise KaiError("Ya hay una integración con ese nombre.", code="duplicate", status_code=409)
    c = ServerConfig(id=new_server_id(), name=body.name.strip(), transport=body.transport,
                     command=body.command.strip(), args=body.args, env=body.env,
                     secret_env=sorted(body.secret_env), url=body.url.strip(), has_token=bool(body.token),
                     oauth=body.oauth)
    for k, v in body.secret_env.items():
        ctx.secrets.set_secret(c.secret_name("env", k), v)
    if body.token:
        ctx.secrets.set_secret(c.secret_name("token"), body.token.strip())
    save_configs(db, [*configs, c])
    audit(db, "integrations.mcp.add", target=c.id,
          details={"name": c.name, "transport": c.transport, "command": c.command, "args": c.args[:10], "url": c.url},
          client=client_id(request))
    await _manager(ctx).apply(c)
    return _status(ctx, c)


@router.patch("/mcp/{server_id}", summary="Activar/desactivar o renombrar")
async def update_server(server_id: str, body: McpServerUpdate, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    configs = load_configs(db)
    c = _find(configs, server_id)
    if body.name is not None:
        c.name = body.name.strip()
    if body.enabled is not None:
        c.enabled = body.enabled
    save_configs(db, configs)
    audit(db, "integrations.mcp.update", target=c.id, details=body.model_dump(exclude_none=True),
          client=client_id(request))
    await _manager(ctx).apply(c)
    return _status(ctx, c)


@router.post("/mcp/{server_id}/reconnect", summary="Reconectar")
async def reconnect(server_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    c = _find(load_configs(db), server_id)
    await _manager(ctx).apply(c)
    return _status(ctx, c)


@router.put("/mcp/{server_id}/secrets", summary="Volver a cargar claves o token (y reconectar)")
async def set_secrets(server_id: str, body: SecretsIn, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    configs = load_configs(db)
    c = _find(configs, server_id)
    unknown = set(body.secret_env) - set(c.secret_env)
    if unknown:
        raise KaiError(f"Esta integración no usa: {', '.join(sorted(unknown))}.", code="unknown_secret", status_code=422)
    for k, v in body.secret_env.items():
        ctx.secrets.set_secret(c.secret_name("env", k), v)
    if body.token:
        if c.transport != "http":
            raise KaiError("El token es sólo para servidores HTTP.", code="invalid", status_code=422)
        ctx.secrets.set_secret(c.secret_name("token"), body.token.strip())
        c.has_token = True
        save_configs(db, configs)
    audit(db, "integrations.mcp.secrets", target=c.id, details={"names": sorted(body.secret_env), "token": bool(body.token)},
          client=client_id(request))
    await _manager(ctx).apply(c)
    return _status(ctx, c)


@router.put("/mcp/{server_id}/tools/{tool_name}", summary="Nivel de una herramienta (permitir/preguntar/bloquear)")
def set_tool_level(server_id: str, tool_name: str, body: ToolLevelIn, request: Request, ctx: Ctx,
                   db: Db) -> dict[str, Any]:
    configs = load_configs(db)
    c = _find(configs, server_id)
    if body.level == "default":
        c.tool_levels.pop(tool_name, None)
    else:
        c.tool_levels[tool_name] = body.level
    save_configs(db, configs)
    _manager(ctx).update_levels(c)
    audit(db, "integrations.mcp.level", target=c.id, details={"tool": tool_name, "level": body.level},
          client=client_id(request))
    return _status(ctx, c)


@router.delete("/mcp/{server_id}", status_code=204, summary="Quitar un servidor MCP (y sus secretos)")
async def remove_server(server_id: str, request: Request, ctx: Ctx, db: Db) -> None:
    configs = load_configs(db)
    c = _find(configs, server_id)
    await _manager(ctx).remove(c.id)
    for k in c.secret_env:
        ctx.secrets.delete_secret(c.secret_name("env", k))
    if c.has_token:
        ctx.secrets.delete_secret(c.secret_name("token"))
    SecretTokenStorage(ctx.secrets, c).clear()
    save_configs(db, [x for x in configs if x.id != c.id])
    audit(db, "integrations.mcp.remove", target=c.id, details={"name": c.name}, client=client_id(request))


@router.delete("/mcp/{server_id}/oauth", summary="Cerrar la sesión OAuth (borra los tokens y pide iniciar sesión de nuevo)")
async def oauth_logout(server_id: str, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    c = _find(load_configs(db), server_id)
    if not c.oauth:
        raise KaiError("Esta integración no usa OAuth.", code="invalid", status_code=422)
    SecretTokenStorage(ctx.secrets, c).clear()
    audit(db, "integrations.mcp.oauth_logout", target=c.id, client=client_id(request))
    await _manager(ctx).apply(c)
    return _status(ctx, c)


@router.post("/mcp/{server_id}/oauth/open", summary="Abrir el inicio de sesión en el navegador predeterminado de la PC")
def oauth_open(server_id: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    import webbrowser

    c = _find(load_configs(db), server_id)
    conn = _manager(ctx).connections.get(c.id)
    if conn is None or conn.status != "needs_auth" or not conn.auth_url:
        raise KaiError("Esta integración no está esperando un inicio de sesión.", code="invalid", status_code=409)
    opened = False
    try:
        opened = webbrowser.open(conn.auth_url)
    except Exception:  # noqa: BLE001 - sin navegador disponible: la interfaz muestra el enlace
        opened = False
    return {"opened": bool(opened), "auth_url": conn.auth_url}


_PAGE = """<!doctype html><html lang="es"><meta charset="utf-8"><title>KAI</title>
<body style="font-family:system-ui;background:#05070b;color:#e8ecf3;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;max-width:28rem"><h1 style="font-weight:600">{title}</h1><p>{text}</p></div></body></html>"""


@router.get("/oauth/callback", include_in_schema=False)
def oauth_callback(request: Request, ctx: Ctx, db: Db, state: str = "", code: str | None = None,
                   error: str | None = None) -> HTMLResponse:
    """El servicio vuelve acá después de que el usuario inicia sesión en su navegador."""
    from html import escape

    try:
        conn = _manager(ctx).complete_oauth(state, code, error)
    except KaiError as e:
        return HTMLResponse(_PAGE.format(title="No se pudo completar", text=escape(e.message)), status_code=400)
    audit(db, "integrations.mcp.oauth", target=conn.config.id, details={"ok": not error}, client=client_id(request))
    if error:
        return HTMLResponse(_PAGE.format(title="Inicio de sesión cancelado",
                                         text="Podés cerrar esta pestaña y volver a intentarlo desde KAI."))
    return HTMLResponse(_PAGE.format(title="Listo", text=f"KAI quedó conectado a «{escape(conn.config.name)}». "
                                                         "Podés cerrar esta pestaña."))
