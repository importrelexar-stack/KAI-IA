from __future__ import annotations

import json
from typing import Annotated

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.core.context import AppContext
from app.core.errors import KaiError, NotFoundError, ProviderNotConfiguredError
from app.automation.files import read_text
from app.cowork.bridge import safe_filename
from app.models.entities import Attachment, Conversation, Message
from app.schemas.chat import (
    AttachmentOut,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationRename,
    ConversationSummary,
    MessageOut,
)
from app.security.audit import audit
from app.services.chat_service import stream_chat

router = APIRouter(tags=["chat"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Enviar un mensaje a KAI",
    description=(
        "Con `stream=true` (por defecto) responde `text/event-stream` con eventos `meta`, `delta`, "
        "`done` o `error`. Con `stream=false` responde JSON al terminar."
    ),
)
async def chat(body: ChatRequest, request: Request, ctx: Ctx):  # type: ignore[no-untyped-def]
    if not ctx.chat_limiter.check(client_id(request)):
        raise KaiError("Demasiados mensajes por minuto. Esperá un momento.", code="rate_limited", status_code=429)

    if not ctx.provider().configured:
        raise ProviderNotConfiguredError(
            "No hay una clave de API de Anthropic configurada. El chat real no está disponible: "
            "cargala en Configuración o iniciá en modo demostración."
        )
    events = stream_chat(ctx, body.message, body.conversation_id, channel=body.channel,
                         attachment_ids=body.attachment_ids, client=client_id(request))
    if body.stream:
        async def sse():  # type: ignore[no-untyped-def]
            async for ev in events:
                yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    meta = done = None
    async for ev in events:
        if ev["type"] == "meta":
            meta = ev
        elif ev["type"] == "done":
            done = ev
        elif ev["type"] == "error":
            return JSONResponse(status_code=ev["status"],
                                content={"error": {"code": ev["code"], "message": ev["message"]}})
    assert meta and done
    return ChatResponse(conversation_id=done["conversation_id"], user_message=meta["user_message"],
                        assistant_message=done["assistant_message"], served_by_fallback=done["served_by_fallback"])


IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/chat/attachments", response_model=AttachmentOut, status_code=201,
             summary="Adjuntar un documento (texto, PDF, Word) o una imagen al próximo mensaje")
async def upload_attachment(request: Request, ctx: Ctx, db: Db, file: UploadFile = File(...)) -> AttachmentOut:
    limit = ctx.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise KaiError("El archivo está vacío.", code="empty_file", status_code=422)
    if len(data) > limit:
        raise KaiError(f"El archivo supera {ctx.settings.max_upload_mb} MB.", code="file_too_large", status_code=413)
    name = safe_filename(file.filename or "archivo")
    media = (file.content_type or "").split(";")[0].strip().lower()
    att_id = uuid.uuid4().hex
    folder = ctx.settings.data_dir / "attachments" / att_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    text: str | None = None
    if media in IMAGE_TYPES or Path(name).suffix.lower() in IMAGE_TYPES.values():
        if len(data) > MAX_IMAGE_BYTES:
            raise KaiError("La imagen supera 5 MB.", code="file_too_large", status_code=413)
        kind = "image"
        media = media if media in IMAGE_TYPES else {v: k for k, v in IMAGE_TYPES.items()}.get(
            Path(name).suffix.lower().replace(".jpeg", ".jpg"), "image/jpeg")
    else:
        kind = "document"
        try:
            text, _ = read_text(path)
        except KaiError:
            path.unlink(missing_ok=True)
            raise
        media = media or "text/plain"
    att = Attachment(id=att_id, name=name, kind=kind, media_type=media, size=len(data), text=text, path=str(path))
    db.add(att)
    db.commit()
    audit(db, "chat.attachment", target=att_id, details={"name": name, "kind": kind, "size": len(data)},
          client=client_id(request))
    return AttachmentOut(id=att.id, name=att.name, kind=att.kind, media_type=att.media_type, size=att.size,
                         chars=len(text or ""))


@router.get("/conversations", response_model=list[ConversationSummary], summary="Listar conversaciones")
def list_conversations(db: Db, limit: int = 50, offset: int = 0, q: str | None = None) -> list[ConversationSummary]:
    limit = max(1, min(limit, 200))
    counts = (select(Message.conversation_id, func.count(Message.id).label("n"))
              .group_by(Message.conversation_id).subquery())
    stmt = (select(Conversation, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.conversation_id == Conversation.id)
            .order_by(Conversation.updated_at.desc()).limit(limit).offset(max(0, offset)))
    if q:
        stmt = stmt.where(Conversation.title.ilike(f"%{q.strip()[:100]}%"))
    return [
        ConversationSummary(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at, message_count=n)
        for c, n in db.execute(stmt).all()
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail, summary="Ver una conversación")
def get_conversation(conversation_id: str, db: Db) -> ConversationDetail:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("La conversación no existe.")
    msgs = [MessageOut.model_validate(m) for m in conv.messages]
    return ConversationDetail(id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at,
                              message_count=len(msgs), messages=msgs)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary, summary="Renombrar")
def rename_conversation(conversation_id: str, body: ConversationRename, db: Db) -> ConversationSummary:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("La conversación no existe.")
    conv.title = body.title.strip()
    db.commit()
    return ConversationSummary(id=conv.id, title=conv.title, created_at=conv.created_at,
                               updated_at=conv.updated_at, message_count=len(conv.messages))


@router.delete("/conversations/{conversation_id}", status_code=204, summary="Eliminar una conversación")
def delete_conversation(conversation_id: str, request: Request, db: Db) -> None:
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError("La conversación no existe.")
    db.delete(conv)
    db.commit()
    audit(db, "conversation.delete", target=conversation_id, client=client_id(request))


@router.delete("/conversations", summary="Eliminar TODO el historial (requiere confirm=true)")
def delete_all_conversations(request: Request, db: Db, confirm: bool = False) -> dict[str, int]:
    if not confirm:
        raise KaiError("Acción destructiva: repetí la solicitud con confirm=true.", code="confirmation_required",
                       status_code=428)
    n = 0
    for conv in db.execute(select(Conversation)).scalars():
        db.delete(conv)
        n += 1
    db.commit()
    audit(db, "conversation.delete_all", details={"count": n}, client=client_id(request))
    return {"deleted": n}
