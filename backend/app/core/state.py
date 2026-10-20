"""Estado global del asistente y bus de eventos en tiempo real (WebSocket)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class AssistantState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"  # Fase 2 (voz)
    PROCESSING = "processing"
    SPEAKING = "speaking"  # Fase 2 (voz)
    EXECUTING = "executing"  # Fase 4 (automatizaciones)
    ERROR = "error"


class EventBus:
    """Publica eventos a todos los clientes WebSocket conectados."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(q)

    @property
    def subscribers(self) -> int:
        return len(self._queues)

    def publish(self, event: dict[str, Any]) -> None:
        event.setdefault("at", datetime.now(timezone.utc).isoformat())
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("Cliente WebSocket lento: se descarta un evento")


class StateManager:
    """Estado real del asistente. Cuenta operaciones activas para no volver a
    `idle` mientras siga habiendo trabajo en curso."""

    ERROR_RESET_SECONDS = 6.0

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._state = AssistantState.IDLE
        self._detail: str | None = None
        self._active = 0
        self._reset_task: asyncio.Task[None] | None = None
        # Estado informado por la interfaz de voz (escuchando / hablando). Sólo se muestra
        # cuando KAI Core no tiene trabajo propio en curso.
        self._client_state: AssistantState | None = None

    @property
    def state(self) -> AssistantState:
        return self._state

    @property
    def detail(self) -> str | None:
        return self._detail

    def snapshot(self) -> dict[str, Any]:
        return {"state": self._state.value, "detail": self._detail, "active_operations": self._active}

    def _set(self, state: AssistantState, detail: str | None = None) -> None:
        self._state = state
        self._detail = detail
        self._bus.publish({"type": "state", **self.snapshot()})

    def begin(self, state: AssistantState = AssistantState.PROCESSING, detail: str | None = None) -> None:
        self._cancel_reset()
        self._active += 1
        self._set(state, detail)

    def _resting(self) -> AssistantState:
        return self._client_state or AssistantState.IDLE

    def set_client_state(self, state: AssistantState | None) -> None:
        """La interfaz informa que está escuchando o reproduciendo voz (None = terminó)."""
        if state not in (None, AssistantState.LISTENING, AssistantState.SPEAKING):
            raise ValueError("Estado de cliente inválido")
        self._client_state = state
        if self._active == 0:
            self._cancel_reset()
            self._set(self._resting(), "Escuchando" if state == AssistantState.LISTENING
                      else "Hablando" if state == AssistantState.SPEAKING else None)

    def end(self) -> None:
        self._active = max(0, self._active - 1)
        if self._active == 0 and self._state != AssistantState.ERROR:
            self._set(self._resting())

    def fail(self, detail: str) -> None:
        self._active = max(0, self._active - 1)
        self._set(AssistantState.ERROR, detail)
        self._schedule_reset()

    def _cancel_reset(self) -> None:
        if self._reset_task and not self._reset_task.done():
            self._reset_task.cancel()
        self._reset_task = None

    def _schedule_reset(self) -> None:
        self._cancel_reset()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _reset() -> None:
            await asyncio.sleep(self.ERROR_RESET_SECONDS)
            if self._active == 0:
                self._set(self._resting())

        self._reset_task = loop.create_task(_reset())
