from __future__ import annotations

from app.core.errors import ProviderError
from app.models.entities import Message
from app.services.chat_service import REFUSAL_NOTICE, build_turns
from tests.conftest import parse_sse


def test_chat_without_key_is_unavailable(make_client):
    with make_client(api_key=None) as c:
        r = c.post("/api/v1/chat", json={"message": "hola"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "provider_not_configured"
        assert c.get("/api/v1/conversations").json() == []
        assert c.get("/api/v1/system/status").json()["features"]["chat"] == "needs_api_key"


def test_chat_streaming_events_and_persistence(client, providers):
    r = client.post("/api/v1/chat", json={"message": "Hola KAI"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    types = [e["type"] for e in events]
    assert types[0] == "meta" and types[-1] == "done" and "delta" in types
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text.strip() == "Hola, soy KAI."
    conv_id = events[0]["conversation_id"]

    detail = client.get(f"/api/v1/conversations/{conv_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"].strip() == "Hola, soy KAI."
    assert detail["title"] == "Hola KAI"

    # El prompt de sistema lleva la persona de KAI y las opciones por defecto
    call = providers[-1].calls[-1]
    assert "Sos KAI" in call["system"]
    assert call["options"].model == "claude-opus-5-5"


def test_chat_non_stream_and_context_history(client, providers):
    r1 = client.post("/api/v1/chat", json={"message": "primero", "stream": False})
    assert r1.status_code == 200, r1.text
    conv_id = r1.json()["conversation_id"]
    r2 = client.post("/api/v1/chat", json={"message": "segundo", "stream": False, "conversation_id": conv_id})
    assert r2.status_code == 200
    turns = providers[-1].calls[-1]["turns"]
    assert [t.role for t in turns] == ["user", "assistant", "user"]
    assert turns[0].content == "primero" and turns[-1].content == "segundo"


def test_history_survives_restart(make_client):
    with make_client() as c:
        conv_id = c.post("/api/v1/chat", json={"message": "recordá esto", "stream": False}).json()["conversation_id"]
    with make_client() as c2:  # nueva app, misma carpeta de datos
        convs = c2.get("/api/v1/conversations").json()
        assert [x["id"] for x in convs] == [conv_id]
        assert convs[0]["message_count"] == 2


def test_validation_errors(client):
    assert client.post("/api/v1/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={}).status_code == 422
    r = client.post("/api/v1/chat", json={"message": "x" * 100_001})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_unknown_conversation(client):
    r = client.post("/api/v1/chat", json={"message": "hola", "conversation_id": "noexiste", "stream": False})
    assert r.status_code == 404
    assert client.get("/api/v1/conversations/noexiste").status_code == 404


def test_provider_error_is_reported_and_state_goes_error(make_client):
    err = ProviderError("La clave de API fue rechazada", code="auth_failed", status_code=401)
    with make_client(provider_kwargs={"error": err}) as c:
        events = parse_sse(c.post("/api/v1/chat", json={"message": "hola"}).text)
        assert events[-1]["type"] == "error" and events[-1]["code"] == "auth_failed"
        assert c.get("/api/v1/health").json()["assistant"]["state"] == "error"
        r = c.post("/api/v1/chat", json={"message": "hola", "stream": False})
        assert r.status_code == 401
        actions = [a["action"] for a in c.get("/api/v1/audit").json()]
        assert "chat.error" in actions


def test_refusal_is_stored_as_notice(make_client):
    with make_client(provider_kwargs={"reply": "", "stop_reason": "refusal"}) as c:
        r = c.post("/api/v1/chat", json={"message": "algo", "stream": False}).json()
        assert r["assistant_message"]["content"] == REFUSAL_NOTICE
        assert r["assistant_message"]["stop_reason"] == "refusal"


def test_daily_budget_blocks_requests(client):
    client.put("/api/v1/settings", json={"daily_token_budget": 10})
    assert client.post("/api/v1/chat", json={"message": "uno", "stream": False}).status_code == 200  # usa 15
    r = client.post("/api/v1/chat", json={"message": "dos", "stream": False})
    assert r.status_code == 429 and r.json()["error"]["code"] == "budget_exceeded"
    usage = client.get("/api/v1/system/status").json()["usage_today"]
    assert usage["total_tokens"] == 15 and usage["requests"] == 1


def test_rate_limit(make_client):
    with make_client(KAI_CHAT_RATE_LIMIT=2) as c:
        for _ in range(2):
            assert c.post("/api/v1/chat", json={"message": "x", "stream": False}).status_code == 200
        assert c.post("/api/v1/chat", json={"message": "x", "stream": False}).status_code == 429


def test_rename_and_delete(client):
    conv_id = client.post("/api/v1/chat", json={"message": "hola", "stream": False}).json()["conversation_id"]
    assert client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Proyecto X"}).json()["title"] == "Proyecto X"
    assert client.get("/api/v1/conversations?q=proyecto").json()[0]["id"] == conv_id
    assert client.delete(f"/api/v1/conversations/{conv_id}").status_code == 204
    assert client.get("/api/v1/conversations").json() == []


def test_delete_all_requires_confirmation(client):
    client.post("/api/v1/chat", json={"message": "a", "stream": False})
    client.post("/api/v1/chat", json={"message": "b", "stream": False})
    assert client.delete("/api/v1/conversations").status_code == 428
    assert client.delete("/api/v1/conversations?confirm=true").json() == {"deleted": 2}
    assert client.get("/api/v1/conversations").json() == []


def test_demo_mode_works_without_key(make_client):
    with make_client(api_key=None, KAI_DEMO_MODE=True) as c:
        r = c.post("/api/v1/chat", json={"message": "hola", "stream": False})
        assert r.status_code == 200
        assert r.json()["assistant_message"]["content"].startswith("[MODO DEMOSTRACIÓN")
        assert c.get("/api/v1/system/status").json()["usage_today"]["requests"] == 0


def _msg(role: str, content: str, seq: int) -> Message:
    return Message(role=role, content=content, seq=seq, conversation_id="c")


def test_build_turns_merges_and_starts_with_user():
    msgs = [_msg("assistant", "huérfano", 1), _msg("user", "a", 2), _msg("user", "b", 3),
            _msg("assistant", "c", 4), _msg("user", "d", 5)]
    turns = build_turns(msgs, window=50)
    assert [(t.role, t.content) for t in turns] == [("user", "a\n\nb"), ("assistant", "c"), ("user", "d")]
    assert [t.content for t in build_turns(msgs, window=2)] == ["d"]
