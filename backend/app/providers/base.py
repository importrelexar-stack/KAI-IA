"""Interfaz común para proveedores de IA intercambiables.

KAI Core sólo conoce esta interfaz; cada proveedor (Anthropic, demo, futuros)
la implementa. Así se puede reemplazar el modelo o el proveedor sin tocar el
resto del sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationOptions:
    model: str
    max_tokens: int = 16000
    effort: str | None = None
    use_fallbacks: bool = True


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class TextDelta:
    text: str
    type: Literal["delta"] = "delta"


@dataclass
class Completed:
    model: str
    stop_reason: str | None
    usage: Usage = field(default_factory=Usage)
    served_by_fallback: bool = False
    type: Literal["completed"] = "completed"


ProviderEvent = TextDelta | Completed


@dataclass
class ValidationResult:
    ok: bool
    message: str


class AIProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    def stream_chat(
        self, *, system: str, turns: list[ChatTurn], options: GenerationOptions
    ) -> AsyncIterator[ProviderEvent]: ...

    @abstractmethod
    async def validate(self) -> ValidationResult: ...
