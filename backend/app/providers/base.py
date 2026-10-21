"""Interfaz común para proveedores de IA intercambiables.

KAI Core sólo conoce esta interfaz; cada proveedor (Anthropic, demo, futuros)
la implementa. Así se puede reemplazar el modelo o el proveedor sin tocar el
resto del sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    # Texto, o bloques de contenido (p. ej. contexto de memoria + mensaje)
    content: str | list[dict[str, Any]]


@dataclass(frozen=True)
class GenerationOptions:
    model: str
    max_tokens: int = 16000
    effort: str | None = None
    use_fallbacks: bool = True
    # Límites del orquestador (Fase 3)
    max_tool_iterations: int = 6
    request_token_budget: int = 200_000
    timeout_seconds: float = 240.0
    web_search: bool = False
    web_fetch: bool = False
    fast: bool = False  # modo rápido de Claude (sólo Opus 5.5 / Opus 5; cuesta el doble por token)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ToolResult:
    content: str
    summary: str
    ok: bool = True
    task_id: str | None = None


ToolExecutor = Callable[[ToolCall], Awaitable[ToolResult]]


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


@dataclass
class ToolActivity:
    name: str
    summary: str
    ok: bool
    task_id: str | None = None
    type: Literal["tool"] = "tool"


ProviderEvent = TextDelta | ToolActivity | Completed


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
        self, *, system: str, turns: list[ChatTurn], options: GenerationOptions,
        tools: list[dict[str, Any]] | None = None, executor: ToolExecutor | None = None,
    ) -> AsyncIterator[ProviderEvent]: ...

    @abstractmethod
    async def validate(self) -> ValidationResult: ...
