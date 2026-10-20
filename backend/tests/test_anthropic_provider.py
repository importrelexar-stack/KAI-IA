"""Pruebas del proveedor Anthropic con el SDK simulado (sin red ni claves reales)."""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.core.errors import ProviderError, ProviderNotConfiguredError
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ChatTurn, Completed, GenerationOptions, TextDelta


class _FakeStream:
    def __init__(self, texts, final, error=None):
        self._texts, self._final, self._error = texts, final, error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            for t in self._texts:
                yield t
        return gen()

    async def get_final_message(self):
        return self._final


def _final(stop_reason="end_turn", iterations=None):
    usage = SimpleNamespace(input_tokens=12, output_tokens=7, cache_read_input_tokens=3, iterations=iterations)
    return SimpleNamespace(model="claude-opus-5-5", stop_reason=stop_reason, usage=usage)


def _provider(monkeypatch, stream: _FakeStream) -> tuple[AnthropicProvider, dict]:
    p = AnthropicProvider("sk-ant-test-0000000000000000000000", max_retries=0)
    captured: dict = {}

    def fake_stream(**kwargs):
        captured.update(kwargs)
        return stream

    monkeypatch.setattr(p._client.beta.messages, "stream", fake_stream)
    return p, captured


async def _collect(p, options=None):
    opts = options or GenerationOptions(model="claude-opus-5-5", effort="low")
    return [ev async for ev in p.stream_chat(system="sys", turns=[ChatTurn("user", "hola")], options=opts)]


async def test_builds_request_and_streams(monkeypatch):
    p, captured = _provider(monkeypatch, _FakeStream(["Ho", "la"], _final()))
    events = await _collect(p)
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Ho", "la"]
    done = events[-1]
    assert isinstance(done, Completed) and done.usage.input_tokens == 12 and done.usage.cache_read_tokens == 3
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"] == {"effort": "low"}
    assert captured["cache_control"] == {"type": "ephemeral"}
    assert captured["fallbacks"] == "default" and captured["betas"] == ["server-side-fallback-2026-07-01"]
    assert captured["messages"] == [{"role": "user", "content": "hola"}]
    assert "thinking" not in captured  # Opus 5.5: pensamiento adaptativo por defecto


async def test_no_fallbacks_for_haiku_or_when_disabled(monkeypatch):
    p, captured = _provider(monkeypatch, _FakeStream(["x"], _final()))
    await _collect(p, GenerationOptions(model="claude-haiku-5-5"))
    assert "fallbacks" not in captured and "betas" not in captured
    p2, captured2 = _provider(monkeypatch, _FakeStream(["x"], _final()))
    await _collect(p2, GenerationOptions(model="claude-opus-5-5", use_fallbacks=False))
    assert "fallbacks" not in captured2


async def test_detects_fallback(monkeypatch):
    p, _ = _provider(monkeypatch, _FakeStream(["x"], _final(iterations=[SimpleNamespace(type="fallback_message")])))
    assert (await _collect(p))[-1].served_by_fallback is True


def _status_error(cls, status):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("fallo", response=httpx2.Response(status, request=req), body={"error": {"message": "detalle"}})


@pytest.mark.parametrize("exc_cls,status,code", [
    (anthropic.AuthenticationError, 401, "auth_failed"),
    (anthropic.RateLimitError, 429, "rate_limited"),
    (anthropic.NotFoundError, 404, "model_not_found"),
    (anthropic.BadRequestError, 400, "bad_request"),
    (anthropic.InternalServerError, 500, "upstream_error"),
])
async def test_maps_api_errors(monkeypatch, exc_cls, status, code):
    p, _ = _provider(monkeypatch, _FakeStream([], None, error=_status_error(exc_cls, status)))
    with pytest.raises(ProviderError) as ei:
        await _collect(p)
    assert ei.value.code == code
    if code == "bad_request":
        assert "detalle" in ei.value.message


async def test_maps_connection_error(monkeypatch):
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    p, _ = _provider(monkeypatch, _FakeStream([], None, error=err))
    with pytest.raises(ProviderError) as ei:
        await _collect(p)
    assert ei.value.code == "connection_error"


async def test_without_key():
    p = AnthropicProvider(None)
    assert p.configured is False
    with pytest.raises(ProviderNotConfiguredError):
        await _collect(p)
    assert (await p.validate()).ok is False
