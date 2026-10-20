from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_db
from app.cowork.bridge import UNTRUSTED_NOTICE, CoworkBridge, safe_filename
from app.core.errors import KaiError
from app.models.entities import CoworkHandoff
from app.schemas.cowork import CoworkHandoffOut, CoworkPrepareRequest, CoworkResultIn, CoworkStatus
from app.security.audit import audit

router = APIRouter(prefix="/cowork", tags=["cowork"])
Db = Annotated[Session, Depends(get_db)]


def get_bridge(request: Request) -> CoworkBridge:
    return request.app.state.cowork


Bridge = Annotated[CoworkBridge, Depends(get_bridge)]


@router.get("/status", response_model=CoworkStatus, summary="Capacidades reales de la integración con Cowork")
def status(bridge: Bridge) -> CoworkStatus:
    c = bridge.adapter.capabilities()
    return CoworkStatus(adapter=c.name, official_api=c.official_api, can_submit=c.can_submit,
                        can_fetch_results=c.can_fetch_results, description=c.description,
                        untrusted_notice=UNTRUSTED_NOTICE)


@router.post("/prepare", response_model=CoworkHandoffOut, status_code=201,
             summary="Preparar instrucciones estructuradas para Cowork")
def prepare(body: CoworkPrepareRequest, request: Request, bridge: Bridge, db: Db) -> CoworkHandoff:
    h = bridge.prepare(db, title=body.title.strip(), objective=body.objective, context=body.context,
                       deliverables=[d.strip() for d in body.deliverables if d.strip()],
                       constraints=[c.strip() for c in body.constraints if c.strip()],
                       folders=[f.strip() for f in body.folders if f.strip()],
                       conversation_id=body.conversation_id, include_messages=body.include_messages)
    audit(db, "cowork.prepare", target=h.id, client=client_id(request))
    return h


@router.get("/handoffs", response_model=list[CoworkHandoffOut], summary="Listar transferencias")
def list_handoffs(db: Db, limit: int = 50) -> list[CoworkHandoff]:
    stmt = select(CoworkHandoff).order_by(CoworkHandoff.created_at.desc()).limit(max(1, min(limit, 200)))
    return list(db.execute(stmt).scalars())


@router.get("/handoffs/{handoff_id}", response_model=CoworkHandoffOut, summary="Ver una transferencia")
def get_handoff(handoff_id: str, bridge: Bridge, db: Db) -> CoworkHandoff:
    return bridge.get(db, handoff_id)


@router.get("/handoffs/{handoff_id}/export", response_class=PlainTextResponse,
            summary="Descargar las instrucciones como .md")
def export_handoff(handoff_id: str, bridge: Bridge, db: Db) -> PlainTextResponse:
    h = bridge.get(db, handoff_id)
    name = safe_filename(f"kai-cowork-{h.title[:40]}.md")
    return PlainTextResponse(h.instructions_md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name.encode("ascii", "replace").decode()}"'})


@router.post("/handoffs/{handoff_id}/sent", summary="Marcar como enviada a Cowork")
def mark_sent(handoff_id: str, request: Request, bridge: Bridge, db: Db) -> dict:
    h, guide = bridge.mark_sent(db, handoff_id)
    audit(db, "cowork.sent", target=h.id, client=client_id(request))
    return {"handoff": CoworkHandoffOut.model_validate(h).model_dump(mode="json"), "guide": guide}


@router.post("/handoffs/{handoff_id}/result", response_model=CoworkHandoffOut, summary="Importar el resultado")
def import_result(handoff_id: str, body: CoworkResultIn, request: Request, bridge: Bridge, db: Db) -> CoworkHandoff:
    h = bridge.import_result(db, handoff_id, body.text)
    audit(db, "cowork.result", target=h.id, client=client_id(request))
    return h


@router.post("/handoffs/{handoff_id}/cancel", response_model=CoworkHandoffOut, summary="Cancelar")
def cancel(handoff_id: str, request: Request, bridge: Bridge, db: Db) -> CoworkHandoff:
    h = bridge.cancel(db, handoff_id)
    audit(db, "cowork.cancel", target=h.id, client=client_id(request))
    return h


@router.post("/handoffs/{handoff_id}/files", status_code=201, summary="Importar un archivo generado por Cowork")
async def upload_file(handoff_id: str, request: Request, bridge: Bridge, db: Db,
                      file: UploadFile = File(...)) -> dict:
    data = await file.read(bridge.max_upload_bytes + 1)
    if not data:
        raise KaiError("El archivo está vacío.", code="empty_file")
    info = bridge.store_file(db, handoff_id, file.filename or "archivo", data)
    audit(db, "cowork.file", target=handoff_id, details={"name": info["name"], "size": info["size"]},
          client=client_id(request))
    return info


@router.get("/handoffs/{handoff_id}/files/{name}", summary="Descargar un archivo importado")
def download_file(handoff_id: str, name: str, bridge: Bridge, db: Db) -> FileResponse:
    path = bridge.file_path(db, handoff_id, name)
    return FileResponse(path, filename=path.name)
