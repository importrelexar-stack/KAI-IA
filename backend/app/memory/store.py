"""Almacén de memoria persistente con búsqueda local (SQLite FTS5 / BM25).

Tipos de memoria:
- preference: preferencias autorizadas por el usuario (siempre presentes en el contexto).
- fact: datos útiles sobre el usuario o su trabajo (se recuperan por relevancia).
- project: notas ligadas a un proyecto (se recuperan por relevancia).

Las memorias que propone KAI quedan en estado "proposed" y no se usan hasta que el
usuario las aprueba (salvo que active la aprobación automática).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import KaiError, NotFoundError
from app.models.entities import Memory, utcnow

MemoryKind = Literal["preference", "fact", "project"]
KINDS = ("preference", "fact", "project")
MAX_CONTENT = 2000
_SECRET_RE = re.compile(
    r"(sk-ant-[\w-]{8,}|(?i:contrase(?:ñ|n)a|password|clave)\s*[:=]\s*\S+|\b\d{13,19}\b)"
)

_STOPWORDS = set(
    "que con para por los las del una uno unos unas como pero mas más esto esta este ese esa eso sus son"
    " hay muy ser fue era tengo tenes tenés tiene sobre entre cuando donde quien cual cuál qué cómo"
    " the and for you are with this that".split()
)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def search_terms(query: str, max_terms: int = 12) -> list[str]:
    words = re.findall(r"\w{3,}", _fold(query))
    out: list[str] = []
    for w in words:
        if w not in _STOPWORDS and w not in out and not w.isdigit():
            out.append(w)
    return out[:max_terms]


def check_content(content: str) -> str:
    content = " ".join(content.strip().split())
    if not content:
        raise KaiError("La memoria está vacía.", code="empty_memory", status_code=422)
    if len(content) > MAX_CONTENT:
        raise KaiError(f"La memoria supera los {MAX_CONTENT} caracteres.", code="memory_too_long", status_code=422)
    if _SECRET_RE.search(content):
        raise KaiError("Por seguridad, KAI no guarda contraseñas, claves ni números de tarjeta en la memoria.",
                       code="sensitive_memory", status_code=422)
    return content


class MemoryStore:
    def __init__(self, fts_enabled: bool) -> None:
        self.fts = fts_enabled

    # ---- índice ----
    def _index(self, db: Session, m: Memory) -> None:
        if not self.fts:
            return
        db.execute(text("DELETE FROM memories_fts WHERE memory_id = :id"), {"id": m.id})
        db.execute(text("INSERT INTO memories_fts (memory_id, content, tags) VALUES (:id, :c, :t)"),
                   {"id": m.id, "c": m.content, "t": " ".join(m.tags or [])})

    def _unindex(self, db: Session, memory_id: str) -> None:
        if self.fts:
            db.execute(text("DELETE FROM memories_fts WHERE memory_id = :id"), {"id": memory_id})

    # ---- CRUD ----
    def create(self, db: Session, *, kind: str, content: str, tags: list[str] | None = None,
               project_id: str | None = None, source: str = "user", status: str = "active",
               conversation_id: str | None = None) -> Memory:
        if kind not in KINDS:
            raise KaiError("Tipo de memoria inválido.", code="invalid_kind", status_code=422)
        m = Memory(kind=kind, content=check_content(content), tags=[t.strip()[:40] for t in tags or [] if t.strip()][:10],
                   project_id=project_id, source=source, status=status, conversation_id=conversation_id)
        db.add(m)
        db.flush()
        self._index(db, m)
        db.commit()
        return m

    def get(self, db: Session, memory_id: str) -> Memory:
        m = db.get(Memory, memory_id)
        if m is None:
            raise NotFoundError("La memoria no existe.")
        return m

    def update(self, db: Session, memory_id: str, *, content: str | None = None, kind: str | None = None,
               tags: list[str] | None = None, project_id: str | None = None) -> Memory:
        m = self.get(db, memory_id)
        if content is not None:
            m.content = check_content(content)
        if kind is not None:
            if kind not in KINDS:
                raise KaiError("Tipo de memoria inválido.", code="invalid_kind", status_code=422)
            m.kind = kind
        if tags is not None:
            m.tags = [t.strip()[:40] for t in tags if t.strip()][:10]
        if project_id is not None:
            m.project_id = project_id or None
        m.updated_at = utcnow()
        self._index(db, m)
        db.commit()
        return m

    def approve(self, db: Session, memory_id: str) -> Memory:
        m = self.get(db, memory_id)
        m.status = "active"
        m.updated_at = utcnow()
        db.commit()
        return m

    def delete(self, db: Session, memory_id: str) -> None:
        m = self.get(db, memory_id)
        self._unindex(db, m.id)
        db.delete(m)
        db.commit()

    def delete_all(self, db: Session) -> int:
        rows = list(db.execute(select(Memory)).scalars())
        for m in rows:
            db.delete(m)
        if self.fts:
            db.execute(text("DELETE FROM memories_fts"))
        db.commit()
        return len(rows)

    def list(self, db: Session, *, kind: str | None = None, status: str | None = None,
             project_id: str | None = None, limit: int = 200) -> list[Memory]:
        stmt = select(Memory).order_by(Memory.updated_at.desc()).limit(limit)
        if kind:
            stmt = stmt.where(Memory.kind == kind)
        if status:
            stmt = stmt.where(Memory.status == status)
        if project_id:
            stmt = stmt.where(Memory.project_id == project_id)
        return list(db.execute(stmt).scalars())

    # ---- recuperación ----
    def search(self, db: Session, query: str, *, limit: int = 8, exclude_kinds: tuple[str, ...] = (),
               project_id: str | None = None) -> list[Memory]:
        terms = search_terms(query)
        if not terms:
            return []
        ids: list[str]
        if self.fts:
            match = " OR ".join(f'"{t}"' for t in terms)
            rows = db.execute(text(
                "SELECT memory_id FROM memories_fts WHERE memories_fts MATCH :q ORDER BY bm25(memories_fts) LIMIT :n"
            ), {"q": match, "n": limit * 4}).all()
            ids = [r[0] for r in rows]
            if not ids:
                return []
            found = {m.id: m for m in db.execute(select(Memory).where(Memory.id.in_(ids))).scalars()}
            ordered = [found[i] for i in ids if i in found]
        else:
            conds = [Memory.content.ilike(f"%{t}%") for t in terms]
            ordered = list(db.execute(select(Memory).where(or_(*conds)).limit(limit * 4)).scalars())
        result = [m for m in ordered if m.status == "active" and m.kind not in exclude_kinds
                  and (project_id is None or m.project_id == project_id)]
        return result[:limit]

    def preferences(self, db: Session, limit: int = 30) -> list[Memory]:
        stmt = (select(Memory).where(Memory.kind == "preference", Memory.status == "active")
                .order_by(Memory.created_at.asc()).limit(limit))
        return list(db.execute(stmt).scalars())

    def mark_used(self, db: Session, memories: list[Memory]) -> None:
        now = utcnow()
        for m in memories:
            m.use_count = (m.use_count or 0) + 1
            m.last_used_at = now
        if memories:
            db.commit()
