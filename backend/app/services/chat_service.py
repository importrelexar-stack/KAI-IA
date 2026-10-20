"""Orquestación de una conversación: persistencia + proveedor de IA + estados."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import AppContext
from app.core.errors import KaiError, NotFoundError, ProviderNotConfiguredError
from app.core.persona import build_system_prompt
from app.core.state import AssistantState
from app.models.entities import Conversation, Message, utcnow
from app.providers.base import ChatTurn, Completed, GenerationOptions, TextDelta
from app.schemas.chat import MessageOut
from app.security.audit import audit
from app.services.settings_service import get_preferences
from app.services.usage_service import ensure_within_budget, record_usage

log = logging.getLogger(__name__)

REFUSAL_NOTICE = "[Claude declinó responder esta solicitud por sus políticas de seguridad.]"
TITLE_MAX = 60


def build_turns(messages: list[Message], window: int) -> list[ChatTurn]:
    """Arma el contexto para el modelo: últimos `window` mensajes, alternando roles
    (los mensajes consecutivos del mismo rol se unen) y empezando siempre por `user`."""
    recent = messages[-window:]
    turns: list[ChatTurn] = []
    for m in recent:
        if m.role not in ("user", "assistant") or not m.content.strip():
            continue
        if turns and turns[-1].role == m.role:
            turns[-1] = ChatTurn(role=m.role, content=f"{turns[-1].content}\n\n{m.content}")  # type: ignore[arg-type]
        else:
            turns.append(ChatTurn(role=m.role, content=m.content))  # type: ignore[arg-type]
    while turns and turns[0].role != "user":
        turns.pop(0)
    return turns


def _title_from(text: str) -> str:
    line = " ".join(text.strip().split())
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 1].rstrip() + "…"


def _next_seq(db: Session, conversation_id: str) -> int:
    current = db.execute(
        select(func.coalesce(func.max(Message.seq), 0)).where(Message.conversation_id == conversation_id)
    ).scalar_one()
    return int(current) + 1


async def stream_chat(ctx: AppContext, message: str, conversation_id: str | None,
                      channel: str = "text") -> AsyncIterator[dict[str, Any]]:
    """Genera eventos: meta → delta* → done | error."""
    db = ctx.db.SessionLocal()
    state_started = False
    try:
        prefs = get_preferences(db)
        provider = ctx.provider()
        if not provider.configured:
            raise ProviderNotConfiguredError(
                "No hay una clave de API de Anthropic configurada. El chat real no está disponible: "
                "cargala en Configuración o iniciá en modo demostración."
            )
        if not ctx.demo_mode:
            ensure_within_budget(db, prefs.daily_token_budget)

        if conversation_id:
            conv = db.get(Conversation, conversation_id)
            if conv is None:
                raise NotFoundError("La conversación no existe.")
        else:
            conv = Conversation(title=_title_from(message))
            db.add(conv)
            db.commit()

        user_msg = Message(conversation_id=conv.id, seq=_next_seq(db, conv.id), role="user", content=message)
        db.add(user_msg)
        conv.updated_at = utcnow()
        db.commit()

        history = list(db.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq.desc())
            .limit(prefs.history_window)
        ).scalars())[::-1]
        turns = build_turns(history, prefs.history_window)

        yield {"type": "meta", "conversation_id": conv.id, "user_message": _out(user_msg),
               "title": conv.title, "provider": provider.name}

        ctx.state.begin(AssistantState.PROCESSING, "Pensando la respuesta")
        state_started = True
        options = GenerationOptions(model=prefs.model, max_tokens=prefs.max_tokens, effort=prefs.effort,
                                    use_fallbacks=prefs.use_fallbacks)
        chunks: list[str] = []
        completed: Completed | None = None
        try:
            async for ev in provider.stream_chat(system=build_system_prompt(prefs, voice=channel == "voice"), turns=turns, options=options):
                if isinstance(ev, TextDelta):
                    chunks.append(ev.text)
                    yield {"type": "delta", "text": ev.text}
                elif isinstance(ev, Completed):
                    completed = ev
        except (asyncio.CancelledError, GeneratorExit):
            # El cliente canceló: se guarda lo recibido y se marca como interrumpido.
            if chunks:
                _save_assistant(db, conv, "".join(chunks), prefs.model, "cancelled", None)
            raise

        text = "".join(chunks)
        assert completed is not None, "el proveedor terminó sin evento de cierre"
        if completed.stop_reason == "refusal" and not text.strip():
            text = REFUSAL_NOTICE
        assistant = _save_assistant(db, conv, text, completed.model, completed.stop_reason, completed)
        if not ctx.demo_mode:
            record_usage(db, completed.model, completed.usage)
        ctx.state.end()
        state_started = False
        yield {"type": "done", "conversation_id": conv.id, "assistant_message": _out(assistant),
               "served_by_fallback": completed.served_by_fallback,
               "usage": {"input_tokens": completed.usage.input_tokens,
                         "output_tokens": completed.usage.output_tokens,
                         "cache_read_tokens": completed.usage.cache_read_tokens}}
    except KaiError as e:
        if state_started:
            ctx.state.fail(e.message)
            state_started = False
        log.warning("chat error code=%s: %s", e.code, e.message)
        try:
            audit(db, "chat.error", details={"code": e.code})
        except Exception:  # noqa: BLE001
            db.rollback()
        yield {"type": "error", "code": e.code, "message": e.message, "status": e.status_code}
    except Exception:
        log.exception("Error inesperado en el chat")
        if state_started:
            ctx.state.fail("Error interno")
            state_started = False
        yield {"type": "error", "code": "internal_error", "message": "Error interno de KAI. Revisá data/logs/kai.log.",
               "status": 500}
    finally:
        if state_started:
            ctx.state.end()
        db.close()


def _save_assistant(db: Session, conv: Conversation, text: str, model: str, stop_reason: str | None,
                    completed: Completed | None) -> Message:
    msg = Message(conversation_id=conv.id, seq=_next_seq(db, conv.id), role="assistant", content=text,
                  model=model, stop_reason=stop_reason,
                  input_tokens=completed.usage.input_tokens if completed else 0,
                  output_tokens=completed.usage.output_tokens if completed else 0)
    db.add(msg)
    conv.updated_at = utcnow()
    db.commit()
    return msg


def _out(m: Message) -> dict[str, Any]:
    return MessageOut.model_validate(m).model_dump(mode="json")
