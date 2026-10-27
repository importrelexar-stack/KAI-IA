from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_ctx, require_local
from app.core.context import AppContext

router = APIRouter(prefix="/system/update", tags=["system"], dependencies=[Depends(require_local)])
Ctx = Annotated[AppContext, Depends(get_ctx)]


@router.get("", summary="¿Hay una versión nueva de KAI?")
async def check_update(ctx: Ctx, force: bool = False) -> dict:
    return await ctx.updater.check(force)


@router.get("/state", summary="Progreso de la actualización")
def update_state(ctx: Ctx) -> dict:
    return ctx.updater.state


@router.post("/install", status_code=202, summary="Descargar e instalar la versión nueva")
async def install_update(ctx: Ctx) -> dict:
    ctx.updater.start_install()
    return ctx.updater.state
