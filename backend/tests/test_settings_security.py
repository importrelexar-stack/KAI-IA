from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.logging import redact
from app.main import create_app
from app.security.access import RateLimiter
from app.security.secrets import SecretStore, mask_key
from tests.conftest import FAKE_KEY


def test_settings_roundtrip(client):
    s = client.get("/api/v1/settings").json()
    assert s["preferences"]["model"] == "claude-opus-5-5"
    assert s["api_key"]["configured"] is True
    assert FAKE_KEY not in str(s)  # la clave nunca se devuelve
    r = client.put("/api/v1/settings", json={"effort": "medium", "user_name": "Leo"})
    assert r.status_code == 200
    assert r.json()["preferences"]["effort"] == "medium"
    assert client.get("/api/v1/settings").json()["preferences"]["user_name"] == "Leo"


def test_settings_validation(client):
    assert client.put("/api/v1/settings", json={"model": "gpt-4"}).status_code == 422
    assert client.put("/api/v1/settings", json={"effort": "turbo"}).status_code == 422
    assert client.put("/api/v1/settings", json={"max_tokens": 10}).status_code == 422


def test_preferences_are_used_by_chat(client, providers):
    client.put("/api/v1/settings", json={"model": "claude-sonnet-5-5", "effort": "high",
                                         "custom_instructions": "Respondé en viñetas."})
    client.post("/api/v1/chat", json={"message": "hola", "stream": False})
    call = providers[-1].calls[-1]
    assert call["options"].model == "claude-sonnet-5-5" and call["options"].effort == "high"
    assert "Respondé en viñetas." in call["system"]


def test_api_key_set_and_delete_without_keyring(make_client, providers):
    with make_client(api_key=None) as c:
        bad = c.put("/api/v1/settings/api-key", json={"api_key": "no-es-una-clave-valida-xx"})
        assert bad.status_code == 422
        r = c.put("/api/v1/settings/api-key", json={"api_key": FAKE_KEY})
        assert r.status_code == 200
        body = r.json()
        assert body == {"configured": True, "source": "memory", "masked": mask_key(FAKE_KEY),
                        "keyring_available": False, "persisted": False}
        # el proveedor se reconstruye con la nueva clave
        assert c.post("/api/v1/chat", json={"message": "hola", "stream": False}).status_code == 200
        assert providers[-1].api_key == FAKE_KEY
        assert c.post("/api/v1/settings/api-key/test").json()["ok"] is True
        assert c.delete("/api/v1/settings/api-key").json()["configured"] is False
        assert c.post("/api/v1/chat", json={"message": "hola"}).status_code == 503
        actions = [a["action"] for a in c.get("/api/v1/audit").json()]
        assert "settings.api_key.set" in actions and "settings.api_key.delete" in actions
        assert FAKE_KEY not in str(c.get("/api/v1/audit").json())


def test_secret_store_env_has_priority():
    store = SecretStore("sk-ant-env-key-123456789", use_keyring=False)
    store.set_api_key("sk-ant-other-key-123456789")
    assert store.get_api_key() == ("sk-ant-env-key-123456789", "env")


def test_mask_and_redact():
    assert mask_key(None) is None
    assert FAKE_KEY not in mask_key(FAKE_KEY)
    assert "sk-ant-***" in redact(f"error con {FAKE_KEY}")
    assert "secret" not in redact('x-api-key: "secret"')


def test_foreign_origin_and_host_are_blocked(client):
    r = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_origin"
    assert client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code == 403


def test_remote_client_needs_token(make_settings, data_dir):
    app = create_app(make_settings(), secrets=SecretStore(None, use_keyring=False), configure_logging=False)
    remote = TestClient(app, client=("192.168.1.50", 5000))
    assert remote.get("/api/v1/health").status_code == 401
    token = (data_dir / "access_token").read_text().strip()
    assert len(token) >= 32
    assert remote.get("/api/v1/health", headers={"X-KAI-Token": token}).status_code == 200


def test_rate_limiter_window():
    rl = RateLimiter(limit=2, window_seconds=60)
    assert rl.check("a") and rl.check("a") and not rl.check("a")
    assert rl.check("b")
    assert RateLimiter(limit=0).check("x")


def test_config_parses_origins(make_settings):
    s = make_settings(KAI_ALLOWED_ORIGINS="http://a.test, http://b.test")
    assert s.allowed_origins == ["http://a.test", "http://b.test"]
    assert make_settings().host == "127.0.0.1"


def test_own_port_origin_is_always_allowed(make_client):
    with make_client(KAI_PORT=8899, KAI_ALLOWED_ORIGINS="http://otro.test") as c:
        assert c.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:8899"}).status_code == 200
        assert c.get("/api/v1/health", headers={"Origin": "http://otro.test"}).status_code == 200
        assert c.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 403
