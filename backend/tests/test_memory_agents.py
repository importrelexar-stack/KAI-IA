"""Fase 3: memoria persistente, proyectos, orquestador con herramientas y migraciones."""

from __future__ import annotations

import sqlite3

from app.agents.tools import TOOLS, inline_schema
from app.memory.store import search_terms
from tests.conftest import parse_sse


def _chat(c, msg, **kw):
    r = c.post("/api/v1/chat", json={"message": msg, "stream": False, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_memory_crud_and_search(client):
    r = client.post("/api/v1/memory", json={"kind": "fact", "content": "Vende repuestos de autos en Mercado Libre"})
    assert r.status_code == 201 and r.json()["status"] == "active"
    mid = r.json()["id"]
    client.post("/api/v1/memory", json={"kind": "preference", "content": "Prefiere respuestas con conclusiones"})
    found = client.get("/api/v1/memory/search", params={"q": "¿qué vendo en mercado libre?"}).json()
    assert [m["id"] for m in found] == [mid]
    # sin acentos / mayúsculas también encuentra
    assert client.get("/api/v1/memory/search", params={"q": "REPUESTOS"}).json()[0]["id"] == mid
    r = client.patch(f"/api/v1/memory/{mid}", json={"content": "Vende repuestos de motos"})
    assert r.json()["content"] == "Vende repuestos de motos"
    assert client.get("/api/v1/memory/search", params={"q": "autos"}).json() == []
    assert client.get("/api/v1/memory/search", params={"q": "motos"}).json()[0]["id"] == mid
    assert client.delete(f"/api/v1/memory/{mid}").status_code == 204
    assert client.get("/api/v1/memory/search", params={"q": "motos"}).json() == []
    assert client.delete("/api/v1/memory").status_code == 428
    assert client.delete("/api/v1/memory?confirm=true").json() == {"deleted": 1}


def test_memory_rejects_secrets(client):
    for content in ["mi contraseña: hunter2", "clave=abc123", "tarjeta 4509123412341234", "sk-ant-api03-abcdefghijk"]:
        r = client.post("/api/v1/memory", json={"kind": "fact", "content": content})
        assert r.status_code == 422 and r.json()["error"]["code"] == "sensitive_memory", content


def test_relevant_memory_and_preferences_reach_the_model(client, providers):
    client.post("/api/v1/memory", json={"kind": "fact", "content": "El depósito queda en Avellaneda"})
    client.post("/api/v1/memory", json={"kind": "preference", "content": "Tratarlo de vos y sin rodeos"})
    _chat(client, "¿Dónde queda el depósito?")
    call = providers[-1].calls[-1]
    assert "Tratarlo de vos y sin rodeos" in call["system"]
    last = call["turns"][-1].content
    assert isinstance(last, list) and "Avellaneda" in last[0]["text"] and "<memoria_relevante>" in last[0]["text"]
    assert last[1]["text"] == "¿Dónde queda el depósito?"
    used = client.get("/api/v1/memory", params={"kind": "fact"}).json()[0]
    assert used["use_count"] == 1
    # con la memoria desactivada no se envía
    client.put("/api/v1/settings", json={"memory_enabled": False})
    _chat(client, "¿Dónde queda el depósito?")
    call = providers[-1].calls[-1]
    assert isinstance(call["turns"][-1].content, str) and "sin rodeos" not in call["system"]


def test_proposed_memories_are_not_used_until_approved(make_client, providers):
    script = [("guardar_memoria", {"contenido": "Trabaja con tres cuentas de Mercado Libre", "tipo": "fact"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        out = _chat(c, "Acordate que tengo tres cuentas")
        assert out["assistant_message"]["tool_events"][0]["name"] == "guardar_memoria"
        assert "pendiente de aprobación" in providers[-1].tool_results[0].content
        proposed = c.get("/api/v1/memory", params={"status": "proposed"}).json()
        assert len(proposed) == 1 and proposed[0]["source"] == "kai"
        assert c.get("/api/v1/memory/search", params={"q": "cuentas"}).json() == []
        c.post(f"/api/v1/memory/{proposed[0]['id']}/approve")
        assert c.get("/api/v1/memory/search", params={"q": "cuentas"}).json()[0]["status"] == "active"


def test_planner_creates_tasks_with_dependencies(make_client, providers):
    plan = {"objetivo": "Lanzar la tienda nueva", "pasos": [
        {"titulo": "Definir catálogo"},
        {"titulo": "Cargar publicaciones", "depende_de": [1], "prioridad": 1},
        {"titulo": "Activar publicidad", "depende_de": [2], "requiere_autorizacion": True},
    ]}
    with make_client(provider_kwargs={"tool_script": [("crear_plan", plan)]}) as c:
        events = parse_sse(c.post("/api/v1/chat", json={"message": "Armá un plan para lanzar la tienda"}).text)
        tool = [e for e in events if e["type"] == "tool"]
        assert tool and tool[0]["ok"] and "3 tareas" in tool[0]["summary"]
        tasks = {t["title"]: t for t in c.get("/api/v1/tasks").json()}
        assert set(tasks) == {"Definir catálogo", "Cargar publicaciones", "Activar publicidad"}
        assert tasks["Cargar publicaciones"]["depends_on"] == [tasks["Definir catálogo"]["id"]]
        assert tasks["Activar publicidad"]["requires_approval"] and tasks["Activar publicidad"]["created_by"] == "kai"
        # no se puede ejecutar antes que su dependencia
        r = c.post(f"/api/v1/tasks/{tasks['Cargar publicaciones']['id']}/transition", json={"status": "running"})
        assert r.status_code == 409
        first = tasks["Definir catálogo"]["id"]
        c.post(f"/api/v1/tasks/{first}/transition", json={"status": "running"})
        c.post(f"/api/v1/tasks/{first}/transition", json={"status": "completed"})
        r = c.post(f"/api/v1/tasks/{tasks['Cargar publicaciones']['id']}/transition", json={"status": "running"})
        assert r.status_code == 200
        assert "agent.tool" in [a["action"] for a in c.get("/api/v1/audit").json()]


def test_invalid_tool_input_is_reported_not_executed(make_client, providers):
    bad_plan = {"objetivo": "x" * 5, "pasos": [{"titulo": "A", "depende_de": [2]}, {"titulo": "B"}]}
    script = [("crear_plan", bad_plan), ("crear_tarea", {"titulo": "ok", "rm -rf": True}), ("borrar_todo", {})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        out = _chat(c, "hacé cosas raras")
        events = out["assistant_message"]["tool_events"]
        assert [e["ok"] for e in events] == [False, False, False]
        assert "pasos anteriores" in providers[-1].tool_results[0].content
        assert "Entrada inválida" in providers[-1].tool_results[1].content
        assert "no existe" in providers[-1].tool_results[2].content
        assert c.get("/api/v1/tasks").json() == []


def test_projects_and_project_tools(make_client, providers):
    script = [
        ("crear_proyecto", {"nombre": "Tienda Motos", "objetivo": "Vender 100 unidades por mes"}),
        ("registrar_en_proyecto", {"proyecto": "tienda motos", "tipo": "decision", "texto": "Usar envío Full",
                                   "proximos_pasos": "Cargar stock en Full"}),
        ("crear_tarea", {"titulo": "Enviar stock a Full", "proyecto": "Tienda"}),
        ("ver_proyecto", {"proyecto": "Tienda Motos"}),
    ]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _chat(c, "Arrancamos el proyecto de motos")
        projects = c.get("/api/v1/projects").json()
        assert len(projects) == 1
        p = c.get(f"/api/v1/projects/{projects[0]['id']}").json()
        assert p["next_steps"] == "Cargar stock en Full"
        assert p["log"][0]["kind"] == "decision" and p["log"][0]["by"] == "kai"
        assert [t["title"] for t in p["tasks"]] == ["Enviar stock a Full"]
        assert "Usar envío Full" in providers[-1].tool_results[3].content
        # API manual de proyectos
        r = c.post(f"/api/v1/projects/{p['id']}/log", json={"kind": "progress", "text": "Primer envío listo"})
        assert r.json()["log"][-1]["by"] == "user"
        assert c.patch(f"/api/v1/projects/{p['id']}", json={"status": "done"}).json()["status"] == "done"
        assert c.delete(f"/api/v1/projects/{p['id']}").status_code == 204
        assert c.get("/api/v1/tasks").json()[0]["project_id"] is None  # la tarea se conserva


def test_agents_can_be_disabled(client, providers):
    client.put("/api/v1/settings", json={"agents_enabled": False})
    _chat(client, "hola")
    call = providers[-1].calls[-1]
    assert call["tools"] is None and "Herramientas:" not in call["system"]
    client.put("/api/v1/settings", json={"agents_enabled": True, "web_search_enabled": True, "max_tool_iterations": 3})
    _chat(client, "hola")
    call = providers[-1].calls[-1]
    assert {t["name"] for t in call["tools"]} == {t.name for t in TOOLS}
    assert call["options"].web_search is True and call["options"].max_tool_iterations == 3
    status = {a["id"]: a["status"] for a in client.get("/api/v1/agents").json()}
    assert status["research"] == "active"


def test_tool_schemas_are_self_contained():
    for t in TOOLS:
        d = t.definition()
        text = str(d)
        assert "$ref" not in text and "$defs" not in text, t.name
        assert d["input_schema"]["type"] == "object" and d["input_schema"].get("additionalProperties") is False
    plan = next(t for t in TOOLS if t.name == "crear_plan").definition()["input_schema"]
    assert plan["properties"]["pasos"]["items"]["properties"]["titulo"]["type"] == "string"
    assert inline_schema({"$defs": {"A": {"type": "string", "title": "A"}}, "properties": {"x": {"$ref": "#/$defs/A"}}}) \
        == {"properties": {"x": {"type": "string"}}}


def test_search_terms():
    assert search_terms("¿Qué tareas tengo para la tienda de Mercado Libre?") == ["tareas", "tienda", "mercado", "libre"]
    assert search_terms("a b") == []


def test_migration_from_phase1_database(make_settings, data_dir):
    """Una base creada por la Fase 1 (sin columnas nuevas) se actualiza sin perder datos."""
    data_dir.mkdir(parents=True)
    con = sqlite3.connect(data_dir / "kai.db")
    con.executescript("""
        CREATE TABLE conversations (id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(64), title VARCHAR(200),
            created_at DATETIME, updated_at DATETIME);
        CREATE TABLE messages (id VARCHAR(32) PRIMARY KEY, conversation_id VARCHAR(32), seq INTEGER, role VARCHAR(16),
            content TEXT, model VARCHAR(64), stop_reason VARCHAR(32), input_tokens INTEGER, output_tokens INTEGER,
            created_at DATETIME);
        CREATE TABLE tasks (id VARCHAR(32) PRIMARY KEY, user_id VARCHAR(64), title VARCHAR(200), description TEXT,
            status VARCHAR(32), priority INTEGER, requires_approval BOOLEAN, tools_used JSON, result TEXT, error TEXT,
            approvals JSON, history JSON, created_at DATETIME, updated_at DATETIME);
        INSERT INTO conversations VALUES ('c1', 'local', 'Vieja', '2026-10-01 10:00:00', '2026-10-01 10:00:00');
        INSERT INTO messages VALUES ('m1', 'c1', 1, 'user', 'hola de antes', NULL, NULL, 0, 0, '2026-10-01 10:00:00');
        INSERT INTO tasks VALUES ('t1', 'local', 'Tarea vieja', '', 'pending', 2, 0, '[]', NULL, NULL, '[]', '[]',
            '2026-10-01 10:00:00', '2026-10-01 10:00:00');
    """)
    con.commit()
    con.close()
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.security.secrets import SecretStore
    from tests.conftest import FakeProvider

    app = create_app(make_settings(), provider_factory=lambda k: FakeProvider("k"),
                     secrets=SecretStore("sk-ant-test-0000000000000000000000", use_keyring=False),
                     configure_logging=False)
    with TestClient(app) as c:
        conv = c.get("/api/v1/conversations/c1").json()
        assert conv["messages"][0]["content"] == "hola de antes"
        assert c.get("/api/v1/tasks").json()[0]["depends_on"] == []
        assert c.post("/api/v1/chat", json={"message": "seguimos", "conversation_id": "c1", "stream": False}).status_code == 200
        assert c.get("/api/v1/system/status").json()["database"]["fts5"] is True


def test_unexpected_tool_error_does_not_break_the_answer(make_client, providers, monkeypatch):
    from app.agents import tools as tools_mod

    def boom(c, a):
        raise RuntimeError("falla interna")

    spec = tools_mod.TOOLS_BY_NAME["listar_proyectos"]
    monkeypatch.setitem(tools_mod.TOOLS_BY_NAME, "listar_proyectos",
                        tools_mod.ToolSpec(spec.name, spec.agent, spec.description, spec.input_model, boom))
    with make_client(provider_kwargs={"tool_script": [("listar_proyectos", {})]}) as c:
        out = _chat(c, "¿qué proyectos tengo?")
        assert out["assistant_message"]["tool_events"] == [
            {"name": "listar_proyectos", "summary": "listar_proyectos: error interno", "ok": False}]
        assert out["assistant_message"]["content"].strip() == "Hola, soy KAI."
