from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.core.context import AppContext
from app.core.errors import KaiError
from app.memory import projects as project_store
from app.models.entities import Memory, Project
from app.security.audit import audit

router = APIRouter(tags=["memory"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]
Kind = Literal["preference", "fact", "project"]


class MemoryIn(BaseModel):
    kind: Kind
    content: str = Field(min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    project_id: str | None = Field(default=None, max_length=32)


class MemoryPatch(BaseModel):
    kind: Kind | None = None
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=10)
    project_id: str | None = Field(default=None, max_length=32)


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    content: str
    tags: list[str]
    status: str
    source: str
    project_id: str | None
    conversation_id: str | None
    use_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=4000)
    next_steps: str = Field(default="", max_length=4000)
    files: list[str] = Field(default_factory=list, max_length=50)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=4000)
    next_steps: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "paused", "done"] | None = None
    files: list[str] | None = Field(default=None, max_length=50)


class ProjectLogIn(BaseModel):
    kind: Literal["decision", "progress", "note"]
    text: str = Field(min_length=1, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    goal: str
    status: str
    next_steps: str
    files: list[str]
    log: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


# ---------- Memorias ----------

@router.get("/memory", response_model=list[MemoryOut], summary="Listar memorias")
def list_memories(ctx: Ctx, db: Db, kind: Kind | None = None, status: Literal["active", "proposed"] | None = None,
                  project_id: str | None = None) -> list[Memory]:
    return ctx.memory.list(db, kind=kind, status=status, project_id=project_id)


@router.get("/memory/search", response_model=list[MemoryOut], summary="Buscar en la memoria (BM25 local)")
def search_memories(q: str, ctx: Ctx, db: Db, limit: int = 10) -> list[Memory]:
    return ctx.memory.search(db, q[:300], limit=max(1, min(limit, 50)))


@router.post("/memory", response_model=MemoryOut, status_code=201, summary="Guardar una memoria")
def create_memory(body: MemoryIn, request: Request, ctx: Ctx, db: Db) -> Memory:
    if body.project_id:
        project_store.get_project(db, body.project_id)
    m = ctx.memory.create(db, kind=body.kind, content=body.content, tags=body.tags, project_id=body.project_id)
    audit(db, "memory.create", target=m.id, client=client_id(request))
    return m


@router.patch("/memory/{memory_id}", response_model=MemoryOut, summary="Editar una memoria")
def update_memory(memory_id: str, body: MemoryPatch, request: Request, ctx: Ctx, db: Db) -> Memory:
    m = ctx.memory.update(db, memory_id, content=body.content, kind=body.kind, tags=body.tags,
                          project_id=body.project_id)
    audit(db, "memory.update", target=m.id, client=client_id(request))
    return m


@router.post("/memory/{memory_id}/approve", response_model=MemoryOut, summary="Aprobar una memoria propuesta")
def approve_memory(memory_id: str, request: Request, ctx: Ctx, db: Db) -> Memory:
    m = ctx.memory.approve(db, memory_id)
    audit(db, "memory.approve", target=m.id, client=client_id(request))
    return m


@router.delete("/memory/{memory_id}", status_code=204, summary="Eliminar una memoria")
def delete_memory(memory_id: str, request: Request, ctx: Ctx, db: Db) -> None:
    ctx.memory.delete(db, memory_id)
    audit(db, "memory.delete", target=memory_id, client=client_id(request))


@router.delete("/memory", summary="Eliminar TODA la memoria (requiere confirm=true)")
def delete_all_memories(request: Request, ctx: Ctx, db: Db, confirm: bool = False) -> dict[str, int]:
    if not confirm:
        raise KaiError("Acción destructiva: repetí la solicitud con confirm=true.", code="confirmation_required",
                       status_code=428)
    n = ctx.memory.delete_all(db)
    audit(db, "memory.delete_all", details={"count": n}, client=client_id(request))
    return {"deleted": n}


# ---------- Proyectos ----------

@router.get("/projects", response_model=list[ProjectOut], summary="Listar proyectos")
def list_projects(db: Db, status: Literal["active", "paused", "done"] | None = None) -> list[Project]:
    return project_store.list_projects(db, status)


@router.post("/projects", response_model=ProjectOut, status_code=201, summary="Crear un proyecto")
def create_project(body: ProjectIn, request: Request, ctx: Ctx, db: Db) -> Project:
    p = project_store.create_project(db, name=body.name, goal=body.goal, next_steps=body.next_steps,
                                     files=body.files)
    audit(db, "project.create", target=p.id, client=client_id(request))
    ctx.bus.publish({"type": "project", "id": p.id})
    return p


@router.get("/projects/{project_id}", summary="Proyecto con tareas y memorias")
def get_project(project_id: str, db: Db) -> dict[str, Any]:
    p = project_store.get_project(db, project_id)
    return {**ProjectOut.model_validate(p).model_dump(mode="json"), **project_store.project_summary(db, p)}


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="Editar un proyecto")
def update_project(project_id: str, body: ProjectPatch, request: Request, ctx: Ctx, db: Db) -> Project:
    p = project_store.update_project(db, project_id, **body.model_dump(exclude_none=True))
    audit(db, "project.update", target=p.id, client=client_id(request))
    ctx.bus.publish({"type": "project", "id": p.id})
    return p


@router.post("/projects/{project_id}/log", response_model=ProjectOut, summary="Registrar decisión o avance")
def add_project_log(project_id: str, body: ProjectLogIn, request: Request, ctx: Ctx, db: Db) -> Project:
    p = project_store.add_log(db, project_id, body.kind, body.text)
    audit(db, "project.log", target=p.id, client=client_id(request))
    ctx.bus.publish({"type": "project", "id": p.id})
    return p


@router.delete("/projects/{project_id}", status_code=204, summary="Eliminar un proyecto (tareas y memorias se conservan)")
def delete_project(project_id: str, request: Request, ctx: Ctx, db: Db) -> None:
    project_store.delete_project(db, project_id)
    audit(db, "project.delete", target=project_id, client=client_id(request))
