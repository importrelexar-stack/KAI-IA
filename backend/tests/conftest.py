from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.base import (
    AIProvider,
    ChatTurn,
    Completed,
    GenerationOptions,
    ProviderEvent,
    TextDelta,
    ToolActivity,
    ToolCall,
    ToolExecutor,
    Usage,
    ValidationResult,
)
from app.security.secrets import SecretStore

FAKE_KEY = "sk-ant-test-0000000000000000000000"


class FakeProvider(AIProvider):
    """Proveedor simulado para pruebas: nunca llama a la red."""

    name = "fake"

    def __init__(self, api_key: str | None, *, reply: str = "Hola, soy KAI.", stop_reason: str = "end_turn",
                 error: Exception | None = None, tool_script: list[tuple[str, dict]] | None = None) -> None:
        self.api_key = api_key
        self.tool_script = tool_script or []
        self.tool_results: list = []
        self.reply = reply
        self.stop_reason = stop_reason
        self.error = error
        self.calls: list[dict] = []

    @property
    def configured(self) -> bool:
        return self.api_key is not None

    async def stream_chat(self, *, system: str, turns: list[ChatTurn], options: GenerationOptions,
                          tools: list[dict] | None = None,
                          executor: ToolExecutor | None = None) -> AsyncIterator[ProviderEvent]:
        self.calls.append({"system": system, "turns": turns, "options": options, "tools": tools})
        if self.error:
            raise self.error
        for i, (name, args) in enumerate(self.tool_script):
            assert executor is not None, "las herramientas están desactivadas"
            result = await executor(ToolCall(id=f"call_{i}", name=name, input=args))
            self.tool_results.append(result)
            yield ToolActivity(name=name, summary=result.summary, ok=result.ok)
        for part in self.reply.split(" "):
            yield TextDelta(text=part + " ")
        yield Completed(model=options.model, stop_reason=self.stop_reason,
                        usage=Usage(input_tokens=10, output_tokens=5))

    async def validate(self) -> ValidationResult:
        return ValidationResult(ok=self.configured, message="ok" if self.configured else "sin clave")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def make_settings(data_dir: Path) -> Callable[..., Settings]:
    def _make(**overrides) -> Settings:
        base = {"KAI_DATA_DIR": str(data_dir), "KAI_WEB_DIST": str(data_dir / "no-dist"),
                "KAI_USE_KEYRING": False, "KAI_CHAT_RATE_LIMIT": 1000}
        base.update(overrides)
        return Settings(_env_file=None, **base)  # type: ignore[call-arg]

    return _make


@pytest.fixture
def providers() -> list[FakeProvider]:
    return []


@pytest.fixture
def make_client(make_settings, providers) -> Callable[..., TestClient]:
    def _make(api_key: str | None = FAKE_KEY, provider_kwargs: dict | None = None, **settings_overrides) -> TestClient:
        def factory(key: str | None) -> FakeProvider:
            p = FakeProvider(key, **(provider_kwargs or {}))
            providers.append(p)
            return p

        settings = make_settings(**settings_overrides)
        app = create_app(settings, provider_factory=factory, secrets=SecretStore(api_key, use_keyring=False),
                         configure_logging=False)
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    with make_client() as c:
        yield c


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events
