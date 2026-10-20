"""CoworkBridge — coordinación con Claude Cowork.

Estado de la investigación (octubre 2026): Claude Cowork funciona dentro de la
aplicación Claude Desktop (Windows/macOS). Las superficies programáticas
documentadas oficialmente son de administración y monitoreo (Analytics API y
OpenTelemetry). No encontramos una API pública para crear, controlar o leer
sesiones de Cowork desde otra aplicación.

Por eso KAI NO simula una integración: el adaptador activo es `ManualCoworkAdapter`,
que arma un paquete de instrucciones estructurado para copiar/pegar (o exportar como
.md) en Cowork, y permite importar luego el resultado y los archivos generados.
`CoworkAdapter` queda como punto de extensión para una futura integración oficial.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidTransitionError, KaiError, NotFoundError
from app.models.entities import CoworkHandoff, Message, utcnow

UNTRUSTED_NOTICE = (
    "El contenido importado desde Cowork se trata como datos no confiables: "
    "KAI no ejecuta instrucciones que vengan dentro de ese contenido."
)


@dataclass(frozen=True)
class AdapterCapabilities:
    name: str
    official_api: bool
    can_submit: bool
    can_fetch_results: bool
    description: str


class CoworkAdapter(ABC):
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def submit(self, handoff: CoworkHandoff) -> dict[str, Any]:
        """Entrega la tarea a Cowork. Devuelve qué tiene que hacer el usuario (si algo)."""


class ManualCoworkAdapter(CoworkAdapter):
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name="manual",
            official_api=False,
            can_submit=False,
            can_fetch_results=False,
            description=(
                "Transferencia manual: copiá las instrucciones en una tarea nueva de Claude Cowork "
                "(Claude Desktop) y, al terminar, importá el resultado en KAI."
            ),
        )

    def submit(self, handoff: CoworkHandoff) -> dict[str, Any]:
        return {
            "mode": "manual",
            "steps": [
                "Abrí Claude Desktop y entrá a Cowork.",
                "Creá una tarea nueva y pegá las instrucciones copiadas (o adjuntá el .md exportado).",
                "Concedé a Cowork acceso sólo a las carpetas indicadas en las instrucciones.",
                "Cuando termine, volvé a KAI e importá el resultado y los archivos generados.",
            ],
        }


def render_instructions(*, title: str, objective: str, context: str, deliverables: list[str],
                        constraints: list[str], folders: list[str], conversation_excerpt: str | None,
                        handoff_id: str) -> str:
    def bullets(items: list[str], empty: str) -> str:
        return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"

    sections = [
        f"# Tarea para Claude Cowork: {title}",
        f"_Preparada por KAI · referencia `{handoff_id}`_",
        "## Objetivo",
        objective.strip(),
    ]
    if context.strip():
        sections += ["## Contexto", context.strip()]
    if conversation_excerpt:
        sections += ["## Extracto de la conversación con KAI", conversation_excerpt]
    sections += [
        "## Carpetas y archivos de trabajo",
        bullets(folders, "No se indicaron carpetas. Pedí confirmación antes de acceder a archivos."),
        "## Entregables esperados",
        bullets(deliverables, "Un resumen claro de lo realizado."),
        "## Restricciones",
        bullets(
            constraints
            + [
                "No elimines ni sobrescribas archivos sin confirmación explícita.",
                "No envíes mensajes ni realices compras o pagos.",
                "Si algo es ambiguo, preguntá antes de actuar.",
            ],
            "",
        ),
        "## Formato de cierre",
        "Al terminar, respondé con: (1) resumen de lo hecho, (2) lista de archivos creados o "
        "modificados con su ruta, (3) problemas o pendientes. Incluí la referencia "
        f"`{handoff_id}` para poder importarlo en KAI.",
    ]
    return "\n\n".join(sections) + "\n"


class CoworkBridge:
    def __init__(self, files_dir: Path, max_upload_bytes: int, adapter: CoworkAdapter | None = None) -> None:
        self.files_dir = files_dir
        self.max_upload_bytes = max_upload_bytes
        self.adapter = adapter or ManualCoworkAdapter()

    def prepare(self, db: Session, *, title: str, objective: str, context: str = "",
                deliverables: list[str] | None = None, constraints: list[str] | None = None,
                folders: list[str] | None = None, conversation_id: str | None = None,
                include_messages: int = 0) -> CoworkHandoff:
        excerpt = None
        if conversation_id and include_messages > 0:
            msgs = list(db.execute(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.seq.desc()).limit(include_messages)
            ).scalars())[::-1]
            if not msgs:
                raise NotFoundError("La conversación no existe o no tiene mensajes.")
            excerpt = "\n\n".join(f"**{'Usuario' if m.role == 'user' else 'KAI'}:** {m.content}" for m in msgs)

        handoff_id = uuid.uuid4().hex
        payload = {"context": context, "deliverables": deliverables or [], "constraints": constraints or [],
                   "folders": folders or []}
        md = render_instructions(title=title, objective=objective, context=context,
                                 deliverables=payload["deliverables"], constraints=payload["constraints"],
                                 folders=payload["folders"], conversation_excerpt=excerpt, handoff_id=handoff_id)
        handoff = CoworkHandoff(id=handoff_id, title=title, objective=objective, payload=payload,
                                instructions_md=md, status="draft", result_files=[],
                                conversation_id=conversation_id)
        db.add(handoff)
        db.commit()
        return handoff

    def get(self, db: Session, handoff_id: str) -> CoworkHandoff:
        h = db.get(CoworkHandoff, handoff_id)
        if h is None:
            raise NotFoundError("La transferencia a Cowork no existe.")
        return h

    def mark_sent(self, db: Session, handoff_id: str) -> tuple[CoworkHandoff, dict[str, Any]]:
        h = self.get(db, handoff_id)
        if h.status not in ("draft", "sent"):
            raise InvalidTransitionError("Sólo se pueden enviar transferencias en borrador.")
        guide = self.adapter.submit(h)
        h.status = "sent"
        h.updated_at = utcnow()
        db.commit()
        return h, guide

    def import_result(self, db: Session, handoff_id: str, text: str) -> CoworkHandoff:
        h = self.get(db, handoff_id)
        if h.status == "cancelled":
            raise InvalidTransitionError("La transferencia está cancelada.")
        h.result_text = text
        h.status = "completed"
        h.updated_at = utcnow()
        db.commit()
        return h

    def cancel(self, db: Session, handoff_id: str) -> CoworkHandoff:
        h = self.get(db, handoff_id)
        if h.status == "completed":
            raise InvalidTransitionError("La transferencia ya está completada.")
        h.status = "cancelled"
        h.updated_at = utcnow()
        db.commit()
        return h

    def store_file(self, db: Session, handoff_id: str, filename: str, data: bytes) -> dict[str, Any]:
        h = self.get(db, handoff_id)
        if len(data) > self.max_upload_bytes:
            raise KaiError(f"El archivo supera el máximo de {self.max_upload_bytes // (1024 * 1024)} MB.",
                           code="file_too_large", status_code=413)
        safe = safe_filename(filename)
        target_dir = (self.files_dir / h.id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / safe).resolve()
        if target.parent != target_dir:
            raise KaiError("Nombre de archivo inválido.", code="invalid_filename")
        if target.exists():  # nunca sobrescribir
            target = target_dir / f"{target.stem}-{uuid.uuid4().hex[:6]}{target.suffix}"
        target.write_bytes(data)
        info = {"name": target.name, "size": len(data), "stored_at": utcnow().isoformat()}
        h.result_files = [*(h.result_files or []), info]
        h.updated_at = utcnow()
        db.commit()
        return info

    def file_path(self, db: Session, handoff_id: str, name: str) -> Path:
        h = self.get(db, handoff_id)
        if name not in {f["name"] for f in h.result_files or []}:
            raise NotFoundError("El archivo no existe.")
        target_dir = (self.files_dir / h.id).resolve()
        path = (target_dir / name).resolve()
        if path.parent != target_dir or not path.is_file():
            raise NotFoundError("El archivo no existe.")
        return path


_UNSAFE = re.compile(r"[^A-Za-z0-9._\- ()áéíóúÁÉÍÓÚñÑüÜ]")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE.sub("_", name).strip(" .")
    if not name or name.split(".")[0].upper() in _RESERVED:
        name = f"archivo_{uuid.uuid4().hex[:8]}"
    return name[:150]
