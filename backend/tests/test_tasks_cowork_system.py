from __future__ import annotations

from app.cowork.bridge import safe_filename


def test_task_lifecycle(client):
    t = client.post("/api/v1/tasks", json={"title": "Preparar informe", "priority": 1}).json()
    assert t["status"] == "pending"
    t = client.post(f"/api/v1/tasks/{t['id']}/transition", json={"status": "running"}).json()
    t = client.post(f"/api/v1/tasks/{t['id']}/transition", json={"status": "completed", "result": "listo"}).json()
    assert t["status"] == "completed" and t["result"] == "listo"
    assert [h["status"] for h in t["history"]] == ["pending", "running", "completed"]
    r = client.post(f"/api/v1/tasks/{t['id']}/transition", json={"status": "running"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


def test_task_requires_approval(client):
    t = client.post("/api/v1/tasks", json={"title": "Borrar temporales", "requires_approval": True}).json()
    tid = t["id"]
    assert client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "running"}).status_code == 409
    assert client.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True}).status_code == 409  # no espera aún
    client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "awaiting_approval"})
    client.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True})
    t = client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "running"}).json()
    assert t["status"] == "running"
    # un reintento tras fallar exige autorización nueva
    client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "failed", "error": "x"})
    client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "pending"})
    client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "awaiting_approval"})
    assert client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "running"}).status_code == 409


def test_task_rejection_cancels(client):
    tid = client.post("/api/v1/tasks", json={"title": "Instalar programa", "requires_approval": True}).json()["id"]
    client.post(f"/api/v1/tasks/{tid}/transition", json={"status": "awaiting_approval"})
    t = client.post(f"/api/v1/tasks/{tid}/approval", json={"approve": False}).json()
    assert t["status"] == "cancelled"
    assert client.get("/api/v1/tasks?status=cancelled").json()[0]["id"] == tid


def test_tasks_sorted_by_priority(client):
    client.post("/api/v1/tasks", json={"title": "baja", "priority": 3})
    client.post("/api/v1/tasks", json={"title": "alta", "priority": 1})
    assert [t["title"] for t in client.get("/api/v1/tasks").json()] == ["alta", "baja"]


def test_cowork_status_is_honest(client):
    s = client.get("/api/v1/cowork/status").json()
    assert s["adapter"] == "manual" and s["official_api"] is False and s["can_submit"] is False


def test_cowork_full_manual_flow(client):
    conv_id = client.post("/api/v1/chat", json={"message": "Necesito ordenar facturas", "stream": False}).json()[
        "conversation_id"]
    h = client.post("/api/v1/cowork/prepare", json={
        "title": "Ordenar facturas", "objective": "Clasificar las facturas de octubre",
        "deliverables": ["Planilla resumen"], "folders": ["C:\\Users\\yo\\Facturas"],
        "conversation_id": conv_id, "include_messages": 2}).json()
    assert h["status"] == "draft"
    md = h["instructions_md"]
    assert "# Tarea para Claude Cowork: Ordenar facturas" in md
    assert "Planilla resumen" in md and "Necesito ordenar facturas" in md and h["id"] in md
    assert "No elimines ni sobrescribas" in md

    exp = client.get(f"/api/v1/cowork/handoffs/{h['id']}/export")
    assert exp.status_code == 200 and exp.text == md and "attachment" in exp.headers["content-disposition"]

    sent = client.post(f"/api/v1/cowork/handoffs/{h['id']}/sent").json()
    assert sent["handoff"]["status"] == "sent" and sent["guide"]["mode"] == "manual"

    up = client.post(f"/api/v1/cowork/handoffs/{h['id']}/files",
                     files={"file": ("../../evil.txt", b"contenido", "text/plain")})
    assert up.status_code == 201 and up.json()["name"] == "evil.txt"
    up2 = client.post(f"/api/v1/cowork/handoffs/{h['id']}/files", files={"file": ("evil.txt", b"otro", "text/plain")})
    assert up2.json()["name"] != "evil.txt"  # no sobrescribe
    dl = client.get(f"/api/v1/cowork/handoffs/{h['id']}/files/evil.txt")
    assert dl.status_code == 200 and dl.content == b"contenido"
    assert client.get(f"/api/v1/cowork/handoffs/{h['id']}/files/..%2Fkai.db").status_code == 404

    done = client.post(f"/api/v1/cowork/handoffs/{h['id']}/result", json={"text": "Listo: 42 facturas"}).json()
    assert done["status"] == "completed" and len(done["result_files"]) == 2
    assert client.post(f"/api/v1/cowork/handoffs/{h['id']}/cancel").status_code == 409


def test_cowork_upload_limit(make_client):
    with make_client(KAI_MAX_UPLOAD_MB=1) as c:
        hid = c.post("/api/v1/cowork/prepare", json={"title": "t", "objective": "o"}).json()["id"]
        r = c.post(f"/api/v1/cowork/handoffs/{hid}/files", files={"file": ("big.bin", b"0" * (1024 * 1024 + 1))})
        assert r.status_code == 413


def test_safe_filename():
    assert safe_filename("..\\..\\windows\\system32\\x.dll") == "x.dll"
    assert safe_filename("CON.txt").startswith("archivo_")
    assert safe_filename("informe final (v2).pdf") == "informe final (v2).pdf"
    assert "/" not in safe_filename("a/b/c<>|.txt")


def test_system_status_and_agents(client):
    s = client.get("/api/v1/system/status").json()
    assert s["database"]["ok"] is True and s["provider"]["configured"] is True
    assert s["features"]["voice"] == "available" and s["features"]["agents"] == "available"
    agents = client.get("/api/v1/agents").json()
    status = {a["id"]: a["status"] for a in agents}
    assert status["orchestrator"] == status["memory"] == status["planner"] == "active"
    assert status["research"] == "disabled" and status["code"] == "planned"


def test_websocket_receives_state_and_task_events(client):
    with client.websocket_connect("/api/v1/ws/events") as ws:
        assert ws.receive_json()["type"] == "state"
        client.post("/api/v1/tasks", json={"title": "evento"})
        ev = ws.receive_json()
        assert ev["type"] == "task" and ev["title"] == "evento"


def test_websocket_rejects_foreign_origin(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/events", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_openapi_and_root(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/chat" in spec["paths"] and "/api/v1/cowork/prepare" in spec["paths"]
    assert "La interfaz no está compilada" in client.get("/").json()["message"]


def test_shutdown_requires_token(client):
    assert client.post("/api/v1/system/shutdown").status_code == 403  # sin token configurado
    called = []
    client.app.state.shutdown_token = "secreto-123"
    client.app.state.request_shutdown = lambda: called.append(True)
    assert client.post("/api/v1/system/shutdown", headers={"X-KAI-Shutdown": "otro"}).status_code == 403
    r = client.post("/api/v1/system/shutdown", headers={"X-KAI-Shutdown": "secreto-123"})
    assert r.status_code == 200 and called == [True]
