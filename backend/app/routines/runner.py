"""Ejecución de rutinas programadas.

Una rutina corre como un mensaje del usuario en su propia conversación, con las mismas reglas del chat:
herramientas, permisos, autorizaciones pendientes (nunca se aprueban solas) y presupuesto diario.
El planificador revisa cada 30 segundos; si la PC estuvo apagada, una rutina vencida corre una sola vez.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.core.context import AppContext
from app.models.entities import Routine, utcnow
from app.routines import schedule as sched

log = logging.getLogger(__name__)
CHECK_SECONDS = 30.0
MAX_RUN_SECONDS = 600.0


def _aware(dt):  # type: ignore[no-untyped-def]
    from datetime import timezone

    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_next(r: Routine, after=None):  # type: ignore[no-untyped-def]
    return sched.next_run(sched.parse(r.schedule), after or utcnow())


def routine_message(r: Routine) -> str:
    return (f"[Rutina programada «{r.name}» — ejecución automática; el usuario no está presente: no hagas "
            f"preguntas, resolvé lo que puedas y dejá el resultado listo para leer. Las acciones que requieran "
            f"autorización quedan pendientes.]\n\n{r.prompt}")


async def run_routine(ctx: AppContext, routine_id: str) -> dict[str, Any]:
    """Ejecuta una rutina ahora. Devuelve {status, conversation_id, error}."""
    from app.services.chat_service import stream_chat

    with ctx.db.SessionLocal() as db:
        r = db.get(Routine, routine_id)
        if r is None:
            return {"status": "error", "error": "La rutina no existe."}
        if r.last_status == "running":
            return {"status": "running", "conversation_id": r.conversation_id}
        r.last_status = "running"
        db.commit()
        message, conversation_id, name = routine_message(r), r.conversation_id, r.name

    status, error, conv_id = "ok", None, conversation_id
    try:
        async def consume() -> None:
            nonlocal status, error, conv_id
            async for ev in stream_chat(ctx, message, conversation_id, channel="text", client=f"routine:{name}",
                                       title=f"Rutina: {name}"[:60]):
                if ev["type"] == "meta":
                    conv_id = ev["conversation_id"]
                elif ev["type"] == "error":
                    status, error = "error", ev["message"]
        await asyncio.wait_for(consume(), MAX_RUN_SECONDS)
    except asyncio.TimeoutError:
        status, error = "error", "La rutina superó el tiempo máximo (10 minutos)."
    except Exception as e:  # noqa: BLE001
        log.exception("Rutina %s", name)
        status, error = "error", f"{type(e).__name__}: {e}"[:500]

    with ctx.db.SessionLocal() as db:
        r = db.get(Routine, routine_id)
        if r is not None:
            r.last_status, r.last_error = status, error
            r.last_run_at = utcnow()
            r.run_count += 1
            if conv_id:
                r.conversation_id = conv_id
            db.commit()
    ctx.bus.publish({"type": "routine", "id": routine_id, "status": status, "conversation_id": conv_id,
                     "name": name})
    log.info("Rutina «%s» ejecutada: %s", name, status)
    return {"status": status, "conversation_id": conv_id, "error": error}


async def scheduler_loop(ctx: AppContext) -> None:
    with ctx.db.SessionLocal() as db:  # rutinas que quedaron «corriendo» por un cierre abrupto
        for r in db.execute(select(Routine).where(Routine.last_status == "running")).scalars():
            r.last_status, r.last_error = "error", "Interrumpida (KAI se cerró durante la ejecución)."
        db.commit()
    while True:
        try:
            await run_due(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el planificador no debe morir
            log.exception("Error en el planificador de rutinas")
        await asyncio.sleep(CHECK_SECONDS)


async def run_due(ctx: AppContext) -> list[str]:
    now = utcnow()
    due: list[str] = []
    with ctx.db.SessionLocal() as db:
        for r in db.execute(select(Routine).where(Routine.enabled.is_(True))).scalars():
            nxt = _aware(r.next_run_at)
            if nxt is None:
                r.next_run_at = compute_next(r, now)
            elif nxt <= now and r.last_status != "running":
                due.append(r.id)
                r.next_run_at = compute_next(r, now)  # se reprograma antes de correr (sin repeticiones)
        db.commit()
    for routine_id in due:
        await run_routine(ctx, routine_id)
    return due
