"""Contenedor de dependencias de KAI Core (una instancia por aplicación)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import Settings
from app.core.state import EventBus, StateManager
from app.database.session import Database
from app.memory.store import MemoryStore
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import AIProvider
from app.providers.demo_provider import DemoProvider
from app.security.access import RateLimiter
from app.security.secrets import SecretStore

ProviderFactory = Callable[[str | None], AIProvider]


def default_provider_factory(api_key: str | None) -> AIProvider:
    return AnthropicProvider(api_key)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    secrets: SecretStore
    bus: EventBus
    state: StateManager
    access_token: str
    chat_limiter: RateLimiter
    provider_factory: ProviderFactory = default_provider_factory
    started_at: float = field(default_factory=time.time)
    mcp: Any = None  # McpManager (Fase 6)
    background_tasks: set[Any] = field(default_factory=set)
    _provider: AIProvider | None = None
    _memory: MemoryStore | None = None

    @property
    def memory(self) -> MemoryStore:
        if self._memory is None:
            self._memory = MemoryStore(self.db.features.get("fts5", False))
        return self._memory

    @property
    def demo_mode(self) -> bool:
        return self.settings.demo_mode

    def provider(self) -> AIProvider:
        if self.demo_mode:
            if not isinstance(self._provider, DemoProvider):
                self._provider = DemoProvider()
            return self._provider
        if self._provider is None:
            key, _ = self.secrets.get_api_key()
            self._provider = self.provider_factory(key)
        return self._provider

    def reset_provider(self) -> None:
        """Se llama cuando cambia la clave de API."""
        self._provider = None
