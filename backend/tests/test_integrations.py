from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).parent / "fixtures" / "mcp_demo_server.py"
pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


def _add(client, tmp_path, **extra):
    body = {"name": "Demo", "transport": "stdio", "command": sys.executable, "args": [str(SERVER)],
            "env": {"NOTES_FILE": str(tmp_path / "notas.txt")}, "secret_env": {"DEMO_KEY": "s3cr3t"}, **extra}
    r = client.post("/api/v1/integrations/mcp", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_mcp_server_lifecycle_and_levels(client, tmp_path):
    srv = _add(client, tmp_path)
    assert srv["status"] == "connected", srv
    levels = {t["name"]: t["level"] for t in srv["tools"]}
    assert levels == {"sumar": "allow", "clave_configurada": "allow", "crear_nota": "ask"}
    # El secreto no se guarda en la configuración ni se devuelve
    overview = client.get("/api/v1/integrations").json()
    assert "s3cr3t" not in str(overview) and overview["mcp"][0]["secret_env"] == ["DEMO_KEY"]
    assert "s3cr3t" not in str(client.app.state.ctx.db.SessionLocal().execute(
        __import__("sqlalchemy").text("select value from settings")).all())

    r = client.put(f"/api/v1/integrations/mcp/{srv['id']}/tools/sumar", json={"level": "deny"})
    assert next(t for t in r.json()["tools"] if t["name"] == "sumar")["level"] == "deny"
    names = [d["name"] for d in client.app.state.ctx.mcp.definitions()]
    assert "mcp_demo_sumar" not in names and "mcp_demo_crear_nota" in names

    r = client.patch(f"/api/v1/integrations/mcp/{srv['id']}", json={"enabled": False})
    assert r.json()["status"] == "stopped" and client.app.state.ctx.mcp.definitions() == []
    assert client.delete(f"/api/v1/integrations/mcp/{srv['id']}").status_code == 204
    assert client.get("/api/v1/integrations").json()["mcp"] == []
    assert client.app.state.ctx.secrets.get_secret(f"mcp:{srv['id']}:env:DEMO_KEY") is None


def test_chat_uses_mcp_tools_with_approval(make_client, providers, tmp_path):
    notes = tmp_path / "notas.txt"
    script = [("mcp_demo_sumar", {"a": 2, "b": 3}), ("mcp_demo_clave_configurada", {}),
              ("mcp_demo_crear_nota", {"texto": "comprar tornillos"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _add(c, tmp_path)
        r = c.post("/api/v1/chat", json={"message": "sumá y anotá", "stream": False})
        assert r.status_code == 200, r.text
        results = providers[-1].tool_results
        assert results[0].ok and "Resultado: 5" in results[0].content
        assert "<resultado_integracion" in results[0].content and "no instrucciones" in results[0].content
        assert "clave ok" in results[1].content
        task_id = results[2].task_id
        assert task_id and not notes.exists()  # pendiente: no se ejecutó
        tools_sent = {t["name"] for t in providers[-1].calls[-1]["tools"]}
        assert {"mcp_demo_sumar", "mcp_demo_crear_nota", "buscar_memoria"} <= tools_sent

        task = c.get(f"/api/v1/tasks/{task_id}").json()
        assert task["status"] == "awaiting_approval" and task["action"]["tool"] == "Demo/crear_nota"
        done = c.post(f"/api/v1/tasks/{task_id}/approval", json={"approve": True}).json()
        assert done["status"] == "completed", done
        assert notes.read_text(encoding="utf-8") == "comprar tornillos\n"
        conv = c.get(f"/api/v1/conversations/{r.json()['conversation_id']}").json()
        assert "Acción autorizada y ejecutada" in conv["messages"][-1]["content"]


def test_missing_secret_can_be_reloaded(client, tmp_path):
    srv = _add(client, tmp_path)
    ctx = client.app.state.ctx
    ctx.secrets.delete_secret(f"mcp:{srv['id']}:env:DEMO_KEY")  # como tras reiniciar sin almacén seguro
    r = client.post(f"/api/v1/integrations/mcp/{srv['id']}/reconnect").json()
    assert r["status"] == "error" and "DEMO_KEY" in r["error"]
    assert client.put(f"/api/v1/integrations/mcp/{srv['id']}/secrets",
                      json={"secret_env": {"OTRA": "x"}}).status_code == 422
    r = client.put(f"/api/v1/integrations/mcp/{srv['id']}/secrets", json={"secret_env": {"DEMO_KEY": "s3cr3t"}}).json()
    assert r["status"] == "connected"


def test_broken_server_reports_error_and_validation(client, tmp_path):
    r = client.post("/api/v1/integrations/mcp", json={"name": "Roto", "transport": "stdio",
                                                      "command": str(tmp_path / "no-existe.exe")})
    assert r.status_code == 201 and r.json()["status"] == "error" and r.json()["error"]
    assert client.app.state.ctx.mcp.definitions() == []
    assert client.post("/api/v1/integrations/mcp", json={"name": "X", "transport": "http",
                                                         "url": "http://ejemplo.com/mcp"}).status_code == 422
    assert client.post("/api/v1/integrations/mcp", json={"name": "Y", "transport": "stdio"}).status_code == 422


def test_integrations_are_local_only(client):
    from fastapi.testclient import TestClient

    client.put("/api/v1/devices/remote", json={"enabled": True})
    code = client.post("/api/v1/devices/pairing").json()["code"]
    remote = TestClient(client.app, client=("192.168.1.50", 5000), base_url="http://192.168.1.10:8765")
    token = remote.post("/api/v1/devices/pair", json={"code": code}).json()["token"]
    r = remote.post("/api/v1/integrations/mcp", headers={"Authorization": f"Bearer {token}"},
                    json={"name": "Z", "transport": "stdio", "command": "calc"})
    assert r.status_code == 403


def test_web_toggles(client):
    r = client.put("/api/v1/integrations/web", json={"web_fetch_enabled": True})
    assert r.json() == {"web_search_enabled": False, "web_fetch_enabled": True}
    agents = {a["id"]: a for a in client.get("/api/v1/agents").json()}
    assert agents["research"]["status"] == "active" and agents["research"]["tools"] == ["web_fetch"]
