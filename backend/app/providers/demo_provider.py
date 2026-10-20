"""Proveedor de demostración: NO usa IA.

Sirve para probar la interfaz sin clave de API. Cada respuesta está marcada
explícitamente como demostración para no confundirla con Claude.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.providers.base import (
    AIProvider,
    ChatTurn,
    Completed,
    GenerationOptions,
    ProviderEvent,
    TextDelta,
    Usage,
    ValidationResult,
)

DEMO_PREFIX = "[MODO DEMOSTRACIÓN — sin IA] "


class DemoProvider(AIProvider):
    name = "demo"

    def __init__(self, delay: float = 0.02) -> None:
        self._delay = delay

    @property
    def configured(self) -> bool:
        return True

    async def stream_chat(
        self, *, system: str, turns: list[ChatTurn], options: GenerationOptions
    ) -> AsyncIterator[ProviderEvent]:
        last = turns[-1].content if turns else ""
        text = (
            f"{DEMO_PREFIX}Recibí tu mensaje ({len(last)} caracteres). "
            "Para conversar con Claude, desactivá KAI_DEMO_MODE y configurá una clave de API."
        )
        for word in text.split(" "):
            yield TextDelta(text=word + " ")
            if self._delay:
                await asyncio.sleep(self._delay)
        yield Completed(model="demo", stop_reason="end_turn", usage=Usage())

    async def validate(self) -> ValidationResult:
        return ValidationResult(ok=True, message="Modo demostración activo: no se usa ningún proveedor de IA.")
