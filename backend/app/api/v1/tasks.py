from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.agents.automation_tools import run_approved
from app.automation import tasks as engine
from app.core.state import AssistantState
from app.core.context import AppContext
from app.models.entities import Task
from app.schemas.tasks import TaskApproval, TaskCreate, TaskOut, TaskStatusLiteral, TaskTransition
from app.security.audit import audit

router = APIRouter(tags=["tasks"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]


def _publish(ctx: AppContext, task: Task) -> None:
    ctx.bus.publish({"type": "task", "id": task.id, "status": task.status, "title": task.title})


@router.get("/tasks", response_model=list[TaskOut], summary="Listar tareas (ordenadas por prioridad)")
def list_tasks(db: Db, status: TaskStatusLiteral | None = None, project_id: str | None = None,
               limit: int = 100) -> list[Task]:
    stmt = select(Task).order_by(Task.priority.asc(), Task.created_at.desc()).limit(max(1, min(limit, 500)))
    if status:
        stmt = stmt.where(Task.status == status)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    return list(db.execute(stmt).scalars())


@router.post("/tasks", response_model=TaskOut, status_code=201, summary="Registrar una tarea")
def create_task(body: TaskCreate, request: Request, ctx: Ctx, db: Db) -> Task:
    task = engine.create_task(db, title=body.title.strip(), description=body.description, priority=body.priority,
                              requires_approval=body.requires_approval, project_id=body.project_id,
                              depends_on=body.depends_on)
    audit(db, "task.create", target=task.id, client=client_id(request))
    _publish(ctx, task)
    return task


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="Ver una tarea")
def get_task(task_id: str, db: Db) -> Task:
    return engine.get_task(db, task_id)


@router.post("/tasks/{task_id}/transition", response_model=TaskOut, summary="Cambiar el estado de una tarea")
def transition_task(task_id: str, body: TaskTransition, request: Request, ctx: Ctx, db: Db) -> Task:
    task = engine.transition(db, task_id, engine.TaskStatus(body.status), note=body.note, result=body.result,
                             error=body.error)
    audit(db, "task.transition", target=task_id, details={"status": body.status}, client=client_id(request))
    _publish(ctx, task)
    return task


@router.post("/tasks/{task_id}/approval", response_model=TaskOut,
             summary="Aprobar o rechazar una tarea (si tiene una acción, se ejecuta al aprobarla)")
def approve_task(task_id: str, body: TaskApproval, request: Request, ctx: Ctx, db: Db) -> Task:
    task = engine.decide_approval(db, task_id, approve=body.approve, by=client_id(request), note=body.note)
    audit(db, "task.approval", target=task_id, details={"approve": body.approve}, client=client_id(request))
    if body.approve and task.action:
        ctx.state.begin(AssistantState.EXECUTING, f"Ejecutando: {task.title[:60]}")
        try:
            task = run_approved(db, task, [ctx.settings.data_dir])
        finally:
            ctx.state.end()
        audit(db, "automation.execute", target=task_id,
              details={"tool": task.action.get("tool"), "status": task.status,
                       "args": {k: (v if len(str(v)) < 300 else f"{str(v)[:300]}…") for k, v in
                                (task.action.get("args") or {}).items()}},
              client=client_id(request))
    _publish(ctx, task)
    return task
