"""Motor de tareas basado en estados.

Fase 1: registro de tareas, transiciones validadas, autorizaciones e historial.
La ejecución automática de herramientas llega en la Fase 4; hasta entonces las
transiciones las hace el usuario (o KAI Core) explícitamente.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import InvalidTransitionError, NotFoundError
from app.models.entities import Task, utcnow


class TaskStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}

TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.AWAITING_APPROVAL, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.PENDING},  # reintento explícito
    TaskStatus.CANCELLED: set(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in TRANSITIONS[current]


def create_task(db: Session, *, title: str, description: str = "", priority: int = 2,
                requires_approval: bool = False, project_id: str | None = None,
                depends_on: list[str] | None = None, created_by: str = "user") -> Task:
    deps = list(dict.fromkeys(depends_on or []))
    for dep in deps:
        if db.get(Task, dep) is None:
            raise NotFoundError(f"La tarea de la que depende ({dep}) no existe.")
    task = Task(title=title, description=description, priority=priority, requires_approval=requires_approval,
                project_id=project_id, depends_on=deps, created_by=created_by,
                status=TaskStatus.PENDING.value, tools_used=[], approvals=[],
                history=[{"status": TaskStatus.PENDING.value, "at": utcnow().isoformat(), "note": "creada"}])
    db.add(task)
    db.commit()
    return task


def get_task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("La tarea no existe.")
    return task


def transition(db: Session, task_id: str, target: TaskStatus, *, note: str | None = None,
               result: str | None = None, error: str | None = None) -> Task:
    task = get_task(db, task_id)
    current = TaskStatus(task.status)
    if not can_transition(current, target):
        raise InvalidTransitionError(f"No se puede pasar de '{current.value}' a '{target.value}'.")

    if target == TaskStatus.RUNNING and task.depends_on:
        pending = [d for d in task.depends_on
                   if (dep := db.get(Task, d)) is not None and dep.status != TaskStatus.COMPLETED.value]
        if pending:
            raise InvalidTransitionError("Primero hay que completar las tareas de las que depende.")
    if target == TaskStatus.RUNNING and task.requires_approval:
        approvals = task.approvals or []
        approved = bool(approvals) and approvals[-1].get("decision") == "approved"
        if not approved:
            raise InvalidTransitionError(
                "Esta tarea requiere autorización antes de ejecutarse: pasala a 'awaiting_approval' y aprobala."
            )

    entry: dict[str, Any] = {"from": current.value, "status": target.value, "at": utcnow().isoformat()}
    if note:
        entry["note"] = note
    task.history = [*(task.history or []), entry]
    if target == TaskStatus.PENDING and task.approvals:
        # Un reintento exige una autorización nueva.
        task.approvals = [*task.approvals, {"decision": "reset", "at": entry["at"]}]
    task.status = target.value
    if result is not None:
        task.result = result
    if error is not None:
        task.error = error
    task.updated_at = utcnow()
    db.commit()
    return task


def decide_approval(db: Session, task_id: str, *, approve: bool, by: str = "local", note: str | None = None) -> Task:
    task = get_task(db, task_id)
    if TaskStatus(task.status) != TaskStatus.AWAITING_APPROVAL:
        raise InvalidTransitionError("La tarea no está esperando autorización.")
    decision = {"decision": "approved" if approve else "rejected", "by": by, "at": utcnow().isoformat()}
    if note:
        decision["note"] = note
    task.approvals = [*(task.approvals or []), decision]
    db.commit()
    if not approve:
        return transition(db, task_id, TaskStatus.CANCELLED, note="autorización rechazada")
    return task
