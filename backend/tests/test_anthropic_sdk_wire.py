"""Prueba el proveedor contra el SDK real de Anthropic con un transporte HTTP simulado.

No hay red ni claves reales: se verifica el JSON y los encabezados exactos que envía el SDK,
y que el streaming SSE de la API se interpreta correctamente.
"""

from __future__ import annotations

import json

import anthropic
import httpx2

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ChatTurn, Completed, GenerationOptions, TextDelta


def _sse(events: list[tuple[str, dict]]) -> bytes:
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


def _message_stream(text_parts: list[str], stop_reason: str = "end_turn") -> bytes:
    events: list[tuple[str, dict]] = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 21, "output_tokens": 1, "cache_read_input_tokens": 0,
                      "cache_creation_input_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
    ]
    for part in text_parts:
        events.append(("content_block_delta", {"type": "content_block_delta", "index": 0,
                                               "delta": {"type": "text_delta", "text": part}}))
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 9}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return _sse(events)


def _provider(handler) -> AnthropicProvider:
    p = AnthropicProvider("sk-ant-test-0000000000000000000000", max_retries=0)
    p._client = anthropic.AsyncAnthropic(
        api_key="sk-ant-test-0000000000000000000000",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return p


async def _run(p: AnthropicProvider, **opts):
    options = GenerationOptions(model="claude-opus-5-5", effort="low", **opts)
    return [ev async for ev in p.stream_chat(system="Sos KAI", turns=[ChatTurn("user", "hola")], options=options)]


async def test_wire_request_and_streaming():
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=_message_stream(["¡Ho", "la!"]))

    events = await _run(_provider(handler))
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "¡Hola!"
    done = events[-1]
    assert isinstance(done, Completed)
    assert done.stop_reason == "end_turn" and done.usage.input_tokens == 21 and done.usage.output_tokens == 9

    req = seen[0]
    assert req.url.path == "/v1/messages"
    assert req.headers["x-api-key"].startswith("sk-ant-")
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    body = json.loads(req.content)
    assert body["model"] == "claude-opus-5-5"
    assert body["stream"] is True
    assert body["system"] == "Sos KAI"
    assert body["messages"] == [{"role": "user", "content": "hola"}]
    assert body["output_config"] == {"effort": "low"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default"
    assert "thinking" not in body and "temperature" not in body


async def test_wire_degrades_when_optional_features_rejected():
    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "fallbacks" in body:
            return httpx2.Response(400, json={"type": "error", "error": {
                "type": "invalid_request_error", "message": "fallbacks: unexpected field"}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=_message_stream(["ok"]))

    p = _provider(handler)
    events = await _run(p)
    assert isinstance(events[-1], Completed)
    assert "fallbacks" in bodies[0] and "fallbacks" not in bodies[1] and "cache_control" not in bodies[1]
    # La siguiente solicitud ya va sin las funciones opcionales (no repite el 400)
    await _run(p)
    assert len(bodies) == 3 and "fallbacks" not in bodies[2]


async def test_wire_refusal_stop_reason():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=_message_stream([], stop_reason="refusal"))

    events = await _run(_provider(handler))
    assert isinstance(events[-1], Completed) and events[-1].stop_reason == "refusal"


async def test_wire_validate_lists_models():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/models"
        return httpx2.Response(200, json={"data": [{"type": "model", "id": "claude-opus-5-5",
                                                    "display_name": "Claude Opus 5.5",
                                                    "created_at": "2026-01-01T00:00:00Z"}],
                                          "has_more": False, "first_id": "claude-opus-5-5",
                                          "last_id": "claude-opus-5-5"})

    result = await _provider(handler).validate()
    assert result.ok and "claude-opus-5-5" in result.message


async def test_wire_auth_error_is_reported():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error",
                                                                     "message": "invalid x-api-key"}})

    result = await _provider(handler).validate()
    assert result.ok is False and "401" in result.message
