"""Rutinas programadas (Fase 6). Se administran desde la PC."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db, require_local
from app.core.context import AppContext
from app.core.errors import KaiError, NotFoundError
from app.models.entities import Routine, utcnow
from app.routines import schedule as sched
from app.routines.runner import compute_next, run_routine
from app.security.audit import audit

# Ver y ejecutar: también desde un teléfono vinculado. Crear, modificar y borrar: sólo desde la PC.
router = APIRouter(prefix="/routines", tags=["routines"])
Local = [Depends(require_local)]
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]
MAX_ROUTINES = 30


class RoutineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=3, max_length=4000)
    schedule: sched.Schedule
    enabled: bool = True


class RoutineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    prompt: str | None = Field(default=None, min_length=3, max_length=4000)
    schedule: sched.Schedule | None = None
    enabled: bool | None = None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _out(r: Routine) -> dict[str, Any]:
    return {
        "id": r.id, "name": r.name, "prompt": r.prompt, "schedule": r.schedule,
        "schedule_text": sched.describe(sched.parse(r.schedule)), "enabled": r.enabled,
        "conversation_id": r.conversation_id, "next_run_at": _iso(r.next_run_at) if r.enabled else None,
        "last_run_at": _iso(r.last_run_at), "last_status": r.last_status, "last_error": r.last_error,
        "run_count": r.run_count,
    }


def _get(db: Session, routine_id: str) -> Routine:
    r = db.get(Routine, routine_id)
    if r is None:
        raise NotFoundError("La rutina no existe.")
    return r


@router.get("", summary="Rutinas programadas")
def list_routines(db: Db) -> list[dict[str, Any]]:
    return [_out(r) for r in db.execute(select(Routine).order_by(Routine.created_at)).scalars()]


@router.post("", status_code=201, summary="Crear una rutina", dependencies=Local)
def create_routine(body: RoutineIn, request: Request, db: Db) -> dict[str, Any]:
    if len(list(db.execute(select(Routine.id)).scalars())) >= MAX_ROUTINES:
        raise KaiError(f"Máximo {MAX_ROUTINES} rutinas.", code="too_many", status_code=409)
    r = Routine(name=body.name.strip(), prompt=body.prompt.strip(), schedule=body.schedule.model_dump(),
                enabled=body.enabled)
    r.next_run_at = compute_next(r)
    db.add(r)
    db.commit()
    audit(db, "routine.create", target=r.id, details={"name": r.name, "schedule": r.schedule},
          client=client_id(request))
    return _out(r)


@router.patch("/{routine_id}", summary="Modificar una rutina", dependencies=Local)
def update_routine(routine_id: str, body: RoutineUpdate, request: Request, db: Db) -> dict[str, Any]:
    r = _get(db, routine_id)
    if body.name is not None:
        r.name = body.name.strip()
    if body.prompt is not None:
        r.prompt = body.prompt.strip()
    if body.schedule is not None:
        r.schedule = body.schedule.model_dump()
    if body.enabled is not None:
        r.enabled = body.enabled
    if body.schedule is not None or body.enabled:
        r.next_run_at = compute_next(r)
    db.commit()
    audit(db, "routine.update", target=r.id, details=body.model_dump(exclude_none=True, mode="json"),
          client=client_id(request))
    return _out(r)


@router.delete("/{routine_id}", status_code=204, summary="Eliminar una rutina (su conversación queda en el historial)", dependencies=Local)
def delete_routine(routine_id: str, request: Request, db: Db) -> None:
    r = _get(db, routine_id)
    db.delete(r)
    db.commit()
    audit(db, "routine.delete", target=routine_id, client=client_id(request))


@router.post("/{routine_id}/run", status_code=202, summary="Ejecutar ahora (en segundo plano)")
async def run_now(routine_id: str, request: Request, ctx: Ctx, db: Db) -> dict[str, Any]:
    r = _get(db, routine_id)
    if r.last_status == "running":
        raise KaiError("La rutina ya se está ejecutando.", code="busy", status_code=409)
    audit(db, "routine.run", target=r.id, client=client_id(request))
    tasks = ctx.background_tasks
    task = asyncio.create_task(run_routine(ctx, r.id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"status": "started", "started_at": utcnow().isoformat()}
