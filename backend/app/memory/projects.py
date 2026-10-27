"""Memoria de proyectos: objetivos, decisiones, avances, archivos y próximos pasos."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import KaiError, NotFoundError
from app.models.entities import Memory, Project, Task, utcnow

LogKind = Literal["decision", "progress", "note"]


def create_project(db: Session, *, name: str, goal: str = "", next_steps: str = "",
                   files: list[str] | None = None) -> Project:
    name = name.strip()
    if not name:
        raise KaiError("El proyecto necesita un nombre.", code="empty_name", status_code=422)
    p = Project(name=name[:200], goal=goal.strip(), next_steps=next_steps.strip(),
                files=[f.strip() for f in files or [] if f.strip()][:50], log=[])
    db.add(p)
    db.commit()
    return p


def get_project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise NotFoundError("El proyecto no existe.")
    return p


def find_project(db: Session, ref: str) -> Project:
    """Busca por id o por nombre (sin distinguir mayúsculas)."""
    p = db.get(Project, ref)
    if p:
        return p
    p = db.execute(select(Project).where(Project.name.ilike(ref.strip()))).scalars().first()
    if p:
        return p
    p = db.execute(select(Project).where(Project.name.ilike(f"%{ref.strip()}%"))).scalars().first()
    if p is None:
        raise NotFoundError(f"No encontré un proyecto llamado «{ref}».")
    return p


def update_project(db: Session, project_id: str, **fields: Any) -> Project:
    p = get_project(db, project_id)
    for key in ("name", "goal", "next_steps", "status"):
        value = fields.get(key)
        if value is not None:
            if key == "status" and value not in ("active", "paused", "done"):
                raise KaiError("Estado de proyecto inválido.", code="invalid_status", status_code=422)
            setattr(p, key, value.strip() if isinstance(value, str) else value)
    if fields.get("files") is not None:
        p.files = [f.strip() for f in fields["files"] if f.strip()][:50]
    p.updated_at = utcnow()
    db.commit()
    return p


def add_log(db: Session, project_id: str, kind: LogKind, text: str, by: str = "user") -> Project:
    p = get_project(db, project_id)
    text = " ".join(text.split())
    if not text:
        raise KaiError("El registro está vacío.", code="empty_log", status_code=422)
    p.log = [*(p.log or []), {"kind": kind, "text": text[:2000], "by": by, "at": utcnow().isoformat()}][-200:]
    p.updated_at = utcnow()
    db.commit()
    return p


def delete_project(db: Session, project_id: str) -> None:
    p = get_project(db, project_id)
    for t in db.execute(select(Task).where(Task.project_id == p.id)).scalars():
        t.project_id = None
    for m in db.execute(select(Memory).where(Memory.project_id == p.id)).scalars():
        m.project_id = None
    db.delete(p)
    db.commit()


def list_projects(db: Session, status: str | None = None) -> list[Project]:
    stmt = select(Project).order_by(Project.updated_at.desc())
    if status:
        stmt = stmt.where(Project.status == status)
    return list(db.execute(stmt).scalars())


def project_summary(db: Session, p: Project) -> dict[str, Any]:
    tasks = list(db.execute(select(Task).where(Task.project_id == p.id).order_by(Task.priority)).scalars())
    memories = list(db.execute(select(Memory).where(Memory.project_id == p.id, Memory.status == "active")).scalars())
    return {
        "id": p.id, "name": p.name, "goal": p.goal, "status": p.status, "next_steps": p.next_steps,
        "files": p.files, "recent_log": (p.log or [])[-15:],
        "tasks": [{"id": t.id, "title": t.title, "status": t.status, "priority": t.priority,
                   "depends_on": t.depends_on or []} for t in tasks],
        "memories": [m.content for m in memories][:20],
    }
