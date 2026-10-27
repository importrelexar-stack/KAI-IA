from __future__ import annotations

import sys
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.automation import files as fs
from app.automation.permissions import (
    ALWAYS_ASK,
    DEFAULT_LEVELS,
    PathGuard,
    Permissions,
    get_permissions,
    resolve_app,
    save_permissions,
)
from app.core.context import AppContext
from app.core.errors import KaiError
from app.security.audit import audit

router = APIRouter(prefix="/automation", tags=["automation"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]


def _out(perms: Permissions) -> dict[str, Any]:
    apps = []
    for a in perms.apps:
        try:
            resolved, ok = resolve_app(a), True
        except KaiError:
            resolved, ok = None, False
        apps.append({**a.model_dump(), "resolved": resolved, "available": ok})
    return {
        "folders": [f.model_dump() for f in perms.folders],
        "apps": apps,
        "scripts": [s.model_dump() for s in perms.scripts],
        "start_menu_apps": perms.start_menu_apps,
        "levels": {name: perms.level(name) for name in DEFAULT_LEVELS},
        "default_levels": DEFAULT_LEVELS,
        "always_ask": sorted(ALWAYS_ASK),
    }


@router.get("/permissions", summary="Carpetas, aplicaciones, scripts y niveles de cada herramienta")
def read_permissions(db: Db) -> dict[str, Any]:
    return _out(get_permissions(db))


@router.put("/permissions", summary="Guardar permisos (se validan carpetas y scripts)")
def write_permissions(body: Permissions, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    saved = save_permissions(db, body, [ctx.settings.data_dir])
    audit(db, "automation.permissions", details={
        "folders": [f"{f.path} ({f.mode})" for f in saved.folders],
        "apps": [a.name for a in saved.apps], "scripts": [s.name for s in saved.scripts],
        "start_menu_apps": saved.start_menu_apps,
        "levels": saved.levels}, client=client_id(request))
    return _out(saved)


@router.get("/browse", summary="Listar una carpeta autorizada (sólo lectura)")
def browse(path: str, ctx: Ctx, db: Db) -> dict[str, Any]:
    guard = PathGuard(get_permissions(db), [ctx.settings.data_dir])
    p = guard.resolve(path)
    return {"path": str(p), "root": str(guard.root_of(p)), "items": fs.list_dir(p)}


@router.get("/installed-apps", summary="Aplicaciones del menú Inicio que KAI puede abrir por nombre")
def installed_apps(q: str = "") -> dict[str, Any]:
    from app.automation.apps_catalog import catalog, normalize

    apps = catalog.apps()
    if q.strip():
        nq = normalize(q)
        apps = [a for a in apps if nq in normalize(a.name)]
    return {"available": sys.platform == "win32", "total": len(apps), "apps": [a.name for a in apps[:500]]}
