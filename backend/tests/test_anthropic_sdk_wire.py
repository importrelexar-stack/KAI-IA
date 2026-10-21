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


def _tool_use_stream(tool_id: str, name: str, args: dict) -> bytes:
    return _sse([
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_t", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 50, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "Reviso tus tareas."}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {
            "type": "tool_use", "id": tool_id, "name": name, "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                 "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                           "usage": {"output_tokens": 20}}),
        ("message_stop", {"type": "message_stop"}),
    ])


async def test_wire_tool_loop():
    from app.providers.base import ToolActivity, ToolCall, ToolResult

    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            content = _tool_use_stream("toolu_1", "listar_tareas", {"estado": "pending"})
        else:
            content = _message_stream(["Tenés 2 tareas."])
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=content)

    calls: list[ToolCall] = []

    async def executor(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(content='[{"titulo": "A"}, {"titulo": "B"}]', summary="Consultó tareas: 2")

    tools = [{"name": "listar_tareas", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    p = _provider(handler)
    events = [ev async for ev in p.stream_chat(
        system="s", turns=[ChatTurn("user", "¿qué tengo?")],
        options=GenerationOptions(model="claude-opus-5-5", effort="low"), tools=tools, executor=executor)]

    assert calls == [ToolCall(id="toolu_1", name="listar_tareas", input={"estado": "pending"})]
    assert [type(e).__name__ for e in events if not isinstance(e, TextDelta)] == ["ToolActivity", "Completed"]
    assert isinstance(events[-1], Completed) and events[-1].stop_reason == "end_turn"
    assert events[-1].usage.input_tokens == 50 + 21
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "Reviso tus tareas.\n\nTenés 2 tareas."
    assert any(isinstance(e, ToolActivity) and e.summary == "Consultó tareas: 2" for e in events)

    assert bodies[0]["tools"] == tools
    second = bodies[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assistant = second[1]["content"]
    assert assistant[0] == {"type": "text", "text": "Reviso tus tareas."} or assistant[0]["text"] == "Reviso tus tareas."
    assert assistant[1]["type"] == "tool_use" and assistant[1]["id"] == "toolu_1"
    assert assistant[1]["input"] == {"estado": "pending"}
    assert second[2]["content"] == [{"type": "tool_result", "tool_use_id": "toolu_1",
                                     "content": '[{"titulo": "A"}, {"titulo": "B"}]'}]


async def test_wire_tool_loop_stops_at_limit():
    from app.providers.base import ToolCall, ToolResult

    n = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal n
        n += 1
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=_tool_use_stream(f"toolu_{n}", "listar_tareas", {}))

    async def executor(call: ToolCall) -> ToolResult:
        return ToolResult(content="[]", summary="ok")

    events = [ev async for ev in _provider(handler).stream_chat(
        system="s", turns=[ChatTurn("user", "x")],
        options=GenerationOptions(model="claude-opus-5-5", max_tool_iterations=2),
        tools=[{"name": "listar_tareas", "description": "d", "input_schema": {"type": "object"}}],
        executor=executor)]
    assert n == 3  # 2 rondas de herramientas + la llamada final que se corta
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "límite de pasos" in text
    assert isinstance(events[-1], Completed)


async def test_wire_web_tools_are_declared():
    bodies: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, content=_message_stream(["ok"]), headers={"content-type": "text/event-stream"})

    await _run(_provider(handler), web_search=True, web_fetch=True)
    tools = {t["name"]: t for t in bodies[0]["tools"]}
    assert tools["web_search"]["type"] == "web_search_20260209"
    assert tools["web_fetch"]["type"] == "web_fetch_20260209" and tools["web_fetch"]["max_uses"] == 5


async def test_wire_fast_mode_and_rate_limit_fallback():
    bodies: list[dict] = []
    betas: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        bodies.append(body)
        betas.append(request.headers.get("anthropic-beta", ""))
        if body.get("speed") == "fast" and len(bodies) == 1:
            return httpx2.Response(429, json={"type": "error", "error": {"type": "rate_limit_error",
                                                                       "message": "fast limit"}})
        return httpx2.Response(200, content=_message_stream(["ok"]), headers={"content-type": "text/event-stream"})

    events = await _run(_provider(handler), fast=True)
    assert bodies[0]["speed"] == "fast" and "fast-mode-2026-02-01" in betas[0]
    # Al agotarse el límite del modo rápido, se responde igual a velocidad normal
    assert "speed" not in bodies[1] and "fast-mode-2026-02-01" not in betas[1]
    assert isinstance(events[-1], Completed) and "".join(e.text for e in events if isinstance(e, TextDelta)) == "ok"

    plain: list[dict] = []
    await _run(_provider(lambda r: (plain.append(json.loads(r.content)), httpx2.Response(
        200, content=_message_stream(["ok"]), headers={"content-type": "text/event-stream"}))[1]))
    assert "speed" not in plain[0]
