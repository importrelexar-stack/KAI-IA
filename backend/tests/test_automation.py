"""Fase 4: permisos, herramientas de archivos, acciones con autorización y auditoría."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.automation import permissions as perm_mod
from app.automation.permissions import PathGuard, Permissions
from app.core.errors import KaiError


@pytest.fixture(autouse=True)
def _no_real_system_dirs(monkeypatch, tmp_path):
    # En Windows la carpeta temporal está dentro de AppData (protegida): en las pruebas se usa una
    # carpeta "del sistema" ficticia para poder trabajar en tmp_path.
    monkeypatch.setattr(perm_mod, "_system_dirs", lambda: [tmp_path / "sistema"])


@pytest.fixture
def docs(tmp_path) -> Path:
    d = tmp_path / "docs"
    (d / "sub").mkdir(parents=True)
    (d / "informe.txt").write_text("Ventas de octubre: 120 unidades", encoding="utf-8")
    (d / "foto.jpg").write_bytes(b"\xff\xd8fake")
    (d / "planilla.csv").write_text("sku,stock\nA1,3\n", encoding="utf-8")
    (d / "sub" / "notas.md").write_text("Pendiente: llamar al proveedor", encoding="utf-8")
    (d / ".env").write_text("SECRET=1", encoding="utf-8")
    (d / "clave.pem").write_text("-----BEGIN-----", encoding="utf-8")
    return d


def _allow(client, folder: Path, mode="read_write", **extra):
    r = client.put("/api/v1/automation/permissions", json={"folders": [{"path": str(folder), "mode": mode}], **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _chat(c, msg):
    r = c.post("/api/v1/chat", json={"message": msg, "stream": False})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Permisos ----------

def test_nothing_is_accessible_by_default(make_client, docs, providers):
    with make_client(provider_kwargs={"tool_script": [("listar_carpeta", {"carpeta": str(docs)})]}) as c:
        out = _chat(c, "¿qué hay en docs?")
        assert out["assistant_message"]["tool_events"][0]["ok"] is False
        assert "No hay carpetas autorizadas" in providers[-1].tool_results[0].content


def test_permission_validation(client, docs, tmp_path, data_dir):
    assert client.put("/api/v1/automation/permissions",
                      json={"folders": [{"path": "relativa/no"}]}).status_code == 422
    assert client.put("/api/v1/automation/permissions",
                      json={"folders": [{"path": str(tmp_path / "no-existe")}]}).status_code == 422
    # carpeta que contiene los datos de KAI
    assert client.put("/api/v1/automation/permissions",
                      json={"folders": [{"path": str(tmp_path)}]}).status_code == 422
    assert client.put("/api/v1/automation/permissions",
                      json={"folders": [{"path": str(data_dir)}]}).status_code == 422
    assert client.put("/api/v1/automation/permissions",
                      json={"levels": {"rm_rf": "allow"}}).status_code == 422
    assert client.put("/api/v1/automation/permissions",
                      json={"scripts": [{"name": "x", "path": str(docs / "informe.txt")}]}).status_code == 422
    out = _allow(client, docs, mode="read")
    assert out["folders"] == [{"path": str(docs.resolve()), "mode": "read"}]
    assert out["levels"]["leer_archivo"] == "allow" and out["levels"]["enviar_a_papelera"] == "ask"
    # papelera y scripts no se pueden poner en "allow"
    out = client.put("/api/v1/automation/permissions", json={
        "folders": [{"path": str(docs)}], "levels": {"enviar_a_papelera": "allow", "mover_archivo": "allow"}}).json()
    assert out["levels"]["enviar_a_papelera"] == "ask" and out["levels"]["mover_archivo"] == "allow"
    assert "automation.permissions" in [a["action"] for a in client.get("/api/v1/audit").json()]


def test_path_guard(docs, tmp_path):
    g = PathGuard(Permissions.model_validate({"folders": [{"path": str(docs), "mode": "read"}]}),
                  protected=[tmp_path / "data"])
    assert g.resolve("informe.txt") == (docs / "informe.txt").resolve()
    assert g.resolve(str(docs / "sub" / "notas.md")).name == "notas.md"
    for bad, code in [("../fuera.txt", "path_not_allowed"), (str(tmp_path), "path_not_allowed"),
                      (".env", "path_sensitive"), ("clave.pem", "path_sensitive"), ("", "invalid_path")]:
        with pytest.raises(KaiError) as e:
            g.resolve(bad)
        assert e.value.code == code, bad
    with pytest.raises(KaiError) as e:
        g.resolve("informe.txt", write=True)
    assert e.value.code == "read_only"


@pytest.mark.skipif(sys.platform == "win32", reason="los enlaces simbólicos requieren privilegios en Windows")
def test_symlink_escape_is_blocked(docs, tmp_path):
    secret = tmp_path / "secreto"
    secret.mkdir()
    (secret / "x.txt").write_text("no", encoding="utf-8")
    (docs / "atajo").symlink_to(secret)
    g = PathGuard(Permissions.model_validate({"folders": [{"path": str(docs)}]}), protected=[])
    with pytest.raises(KaiError) as e:
        g.resolve("atajo/x.txt")
    assert e.value.code == "path_not_allowed"


def test_real_system_dirs_are_protected(monkeypatch):
    monkeypatch.undo()
    dirs = [str(d).lower() for d in perm_mod._system_dirs()]
    if sys.platform == "win32":
        assert any(d.endswith("windows") for d in dirs) and any("program files" in d for d in dirs)
    else:
        assert "/etc" in dirs and "/usr" in dirs


# ---------- Herramientas de lectura (se ejecutan sin preguntar) ----------

def test_read_tools(make_client, docs, providers):
    script = [("listar_carpeta", {"carpeta": str(docs)}),
              ("buscar_archivos", {"texto": "proveedor"}),
              ("buscar_archivos", {"nombre": "*.csv"}),
              ("leer_archivo", {"ruta": "informe.txt"}),
              ("leer_archivo", {"ruta": ".env"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs, mode="read")
        out = _chat(c, "revisá mis documentos")
        r = providers[-1].tool_results
        names = r[0].content
        assert "informe.txt" in names and "sub" in names
        assert "notas.md" in r[1].content and "informe" not in r[1].content
        assert "planilla.csv" in r[2].content
        assert "Ventas de octubre" in r[3].content and "<contenido_archivo" in r[3].content
        assert "no instrucciones" in r[3].content
        assert r[4].ok is False and "credenciales" in r[4].content
        assert [e["ok"] for e in out["assistant_message"]["tool_events"]] == [True, True, True, True, False]
        assert c.get("/api/v1/tasks").json() == []  # nada quedó pendiente


def test_read_pdf_and_docx(make_client, docs, providers):
    import zipfile

    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(docs / "vacio.pdf", "wb") as f:
        w.write(f)
    with zipfile.ZipFile(docs / "carta.docx", "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Hola proveedor</w:t></w:r></w:p>"
                                        "</w:body></w:document>")
    script = [("leer_archivo", {"ruta": "vacio.pdf"}), ("leer_archivo", {"ruta": "carta.docx"}),
              ("leer_archivo", {"ruta": "foto.jpg"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs, mode="read")
        _chat(c, "leé")
        r = providers[-1].tool_results
        assert r[0].ok and "[Página 1]" in r[0].content
        assert r[1].ok and "Hola proveedor" in r[1].content
        assert r[2].ok is False and "No sé leer" in r[2].content


# ---------- Acciones que requieren autorización ----------

def test_write_requires_approval_then_executes(make_client, docs, providers):
    script = [("escribir_archivo", {"ruta": "resumen.md", "contenido": "# Resumen\nTodo OK"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs)
        out = _chat(c, "dejame un resumen")
        ev = out["assistant_message"]["tool_events"][0]
        assert ev["ok"] and ev["task_id"] and "Pidió autorización" in ev["summary"]
        assert "No se ejecutó todavía" in providers[-1].tool_results[0].content
        assert not (docs / "resumen.md").exists()
        task = c.get(f"/api/v1/tasks/{ev['task_id']}").json()
        assert task["status"] == "awaiting_approval" and task["action"]["tool"] == "escribir_archivo"
        assert "Crear el archivo" in task["description"]

        done = c.post(f"/api/v1/tasks/{ev['task_id']}/approval", json={"approve": True}).json()
        assert done["status"] == "completed" and "Archivo creado" in done["result"]
        assert (docs / "resumen.md").read_text(encoding="utf-8") == "# Resumen\nTodo OK"
        # la conversación registra el resultado para el próximo turno
        msgs = c.get(f"/api/v1/conversations/{out['conversation_id']}").json()["messages"]
        assert msgs[-1]["stop_reason"] == "action" and "Acción autorizada y ejecutada" in msgs[-1]["content"]
        actions = [a["action"] for a in c.get("/api/v1/audit").json()]
        assert "automation.execute" in actions and "agent.tool" in actions


def test_rejected_action_never_runs(make_client, docs, providers):
    with make_client(provider_kwargs={"tool_script": [("enviar_a_papelera", {"ruta": "informe.txt"})]}) as c:
        _allow(c, docs)
        tid = _chat(c, "borrá el informe")["assistant_message"]["tool_events"][0]["task_id"]
        t = c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": False}).json()
        assert t["status"] == "cancelled" and (docs / "informe.txt").exists()


def test_trash_moves_to_recycle_bin(make_client, docs, providers, monkeypatch):
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", lambda p: trashed.append(p))
    with make_client(provider_kwargs={"tool_script": [("enviar_a_papelera", {"ruta": "foto.jpg"})]}) as c:
        _allow(c, docs)
        tid = _chat(c, "borrá la foto")["assistant_message"]["tool_events"][0]["task_id"]
        t = c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True}).json()
        assert t["status"] == "completed" and trashed == [str((docs / "foto.jpg").resolve())]


def test_permissions_rechecked_at_execution(make_client, docs, providers):
    with make_client(provider_kwargs={"tool_script": [("crear_carpeta", {"ruta": "nueva"})]}) as c:
        _allow(c, docs)
        tid = _chat(c, "creá una carpeta")["assistant_message"]["tool_events"][0]["task_id"]
        _allow(c, docs, mode="read")  # el usuario quitó la escritura antes de aprobar
        t = c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True}).json()
        assert t["status"] == "failed" and "sólo para lectura" in t["error"]
        assert not (docs / "nueva").exists()


def test_allow_level_executes_immediately_and_no_overwrite(make_client, docs, providers):
    script = [("mover_archivo", {"origen": "planilla.csv", "destino": "sub"}),
              ("mover_archivo", {"origen": "sub/notas.md", "destino": "informe.txt"}),
              ("escribir_archivo", {"ruta": "informe.txt", "contenido": "pisado"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs, levels={"mover_archivo": "allow", "escribir_archivo": "allow"})
        out = _chat(c, "ordená")
        assert [e["ok"] for e in out["assistant_message"]["tool_events"]] == [True, False, False]
        assert (docs / "sub" / "planilla.csv").exists()
        assert (docs / "informe.txt").read_text(encoding="utf-8").startswith("Ventas")
        assert c.get("/api/v1/tasks").json() == []


def test_overwrite_keeps_backup(make_client, docs, providers):
    script = [("escribir_archivo", {"ruta": "informe.txt", "contenido": "nuevo", "sobrescribir": True})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs)
        tid = _chat(c, "reemplazá el informe")["assistant_message"]["tool_events"][0]["task_id"]
        assert "Reemplazar (con copia de seguridad)" in c.get(f"/api/v1/tasks/{tid}").json()["description"]
        c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True})
        assert (docs / "informe.txt").read_text(encoding="utf-8") == "nuevo"
        backups = list(docs.glob("informe.kai-backup-*.txt"))
        assert len(backups) == 1 and backups[0].read_text(encoding="utf-8").startswith("Ventas")


def test_organize_folder(make_client, docs, providers):
    with make_client(provider_kwargs={"tool_script": [("organizar_carpeta", {"carpeta": str(docs)})]}) as c:
        _allow(c, docs)
        tid = _chat(c, "ordená docs")["assistant_message"]["tool_events"][0]["task_id"]
        preview = c.get(f"/api/v1/tasks/{tid}").json()["description"]
        assert "Ordenar" in preview and "foto.jpg → Imagenes/" in preview
        t = c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True}).json()
        assert t["status"] == "completed", t
        assert (docs / "Imagenes" / "foto.jpg").exists() and (docs / "Planillas" / "planilla.csv").exists()
        assert (docs / "Documentos" / "informe.txt").exists()
        # los archivos ocultos y sensibles no se tocan
        assert (docs / ".env").exists() and (docs / "clave.pem").exists()
        assert "clave.pem" not in preview


def test_open_and_scripts(make_client, docs, providers, monkeypatch, tmp_path):
    opened, launched = [], []
    monkeypatch.setattr("app.automation.files.open_path", lambda t: opened.append(t) or f"Abierto: {t}")
    monkeypatch.setattr("app.automation.files.launch_app", lambda e: launched.append(e) or "ok")
    script_file = docs / "saludo.py"
    script_file.write_text("print('hola desde script')", encoding="utf-8")
    script = [("abrir", {"destino": "informe.txt"}), ("abrir", {"destino": "editor"}),
              ("abrir", {"destino": "programa-no-registrado"}),
              ("ejecutar_script", {"nombre": "saludo"}), ("ejecutar_script", {"nombre": "rm -rf /"})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        _allow(c, docs, apps=[{"name": "editor", "command": sys.executable}],
               scripts=[{"name": "saludo", "path": str(script_file), "timeout_seconds": 30}],
               levels={"abrir": "allow", "ejecutar_script": "allow"})
        out = _chat(c, "abrí cosas")
        events = out["assistant_message"]["tool_events"]
        assert [e["ok"] for e in events] == [True, True, False, True, False]
        assert opened == [str((docs / "informe.txt").resolve())] and launched == [sys.executable]
        # el script quedó pendiente aunque el nivel diga "allow"
        tid = events[3]["task_id"]
        t = c.post(f"/api/v1/tasks/{tid}/approval", json={"approve": True}).json()
        assert t["status"] == "completed" and "hola desde script" in t["result"]


def test_denied_tool(make_client, docs, providers):
    with make_client(provider_kwargs={"tool_script": [("leer_archivo", {"ruta": "informe.txt"})]}) as c:
        _allow(c, docs, levels={"leer_archivo": "deny"})
        out = _chat(c, "leé")
        assert out["assistant_message"]["tool_events"][0]["ok"] is False
        assert "bloqueada" in providers[-1].tool_results[0].content


def test_browse_endpoint(client, docs):
    assert client.get("/api/v1/automation/browse", params={"path": str(docs)}).status_code == 403
    _allow(client, docs, mode="read")
    r = client.get("/api/v1/automation/browse", params={"path": str(docs)}).json()
    assert {i["nombre"] for i in r["items"]} >= {"informe.txt", "sub"}
    assert client.get("/api/v1/automation/browse", params={"path": str(docs.parent)}).status_code == 403


def test_agents_catalog_phase4(client):
    status = {a["id"]: a for a in client.get("/api/v1/agents").json()}
    assert status["files"]["status"] == "active" and "leer_archivo" in status["files"]["tools"]
    assert status["automation"]["status"] == "active" and "ejecutar_script" in status["automation"]["tools"]
