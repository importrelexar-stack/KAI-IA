from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest

from app.core import updates
from app.core.errors import KaiError

INSTALLER = b"MZ" + b"\x00" * 4096
URL = updates.RELEASE_PREFIX + "kai-ai-windows/Instalar-KAI-AI.exe"


def _transport(manifest: dict, body: bytes = INSTALLER) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("latest.json"):
            return httpx.Response(200, json=manifest)
        if str(request.url) == URL:
            return httpx.Response(200, content=body, headers={"content-length": str(len(body))})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _manifest(**kw) -> dict:
    return {"version": "9.9.0", "build": 500, "sha256": hashlib.sha256(INSTALLER).hexdigest(), "url": URL,
            "notes": "Prueba", **kw}


def test_is_newer_by_build_and_version():
    assert updates.is_newer({"version": "0.9.0", "build": 12}, "0.9.0", 11)
    assert not updates.is_newer({"version": "0.9.0", "build": 11}, "0.9.0", 11)
    # instalación desde el código (build 0): compara versión
    assert updates.is_newer({"version": "0.10.0", "build": 3}, "0.9.0", 0)
    assert not updates.is_newer({"version": "0.9.0", "build": 3}, "0.9.0", 0)


def test_check_endpoint(client):
    client.app.state.ctx.updater = updates.Updater(_transport(_manifest()))
    r = client.get("/api/v1/system/update")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["available"] is True and data["latest"]["version"] == "9.9.0"
    assert data["can_install"] is False  # las pruebas no corren en la app empaquetada
    r = client.post("/api/v1/system/update/install")
    assert r.status_code == 409 and r.json()["error"]["code"] == "update_not_supported"


def test_check_failure_is_reported(client):
    client.app.state.ctx.updater = updates.Updater(httpx.MockTransport(lambda req: httpx.Response(500)))
    r = client.get("/api/v1/system/update")
    assert r.status_code == 502 and r.json()["error"]["code"] == "update_check_failed"


def test_update_is_local_only(client):
    from fastapi.testclient import TestClient
    remote = TestClient(client.app, client=("192.168.1.50", 5000), base_url="http://192.168.1.10:8765")
    assert remote.get("/api/v1/system/update").status_code in (401, 403)


def test_download_verifies_checksum(tmp_path):
    u = updates.Updater(_transport(_manifest()))
    path = asyncio.run(u.download(URL, hashlib.sha256(INSTALLER).hexdigest(), tmp_path))
    assert path.read_bytes() == INSTALLER and u.state["progress"] == 1.0

    bad = updates.Updater(_transport(_manifest(), body=b"MZ otro archivo"))
    with pytest.raises(KaiError) as e:
        asyncio.run(bad.download(URL, hashlib.sha256(INSTALLER).hexdigest(), tmp_path / "b"))
    assert e.value.code == "update_checksum"
    assert not list((tmp_path / "b").iterdir())


def test_install_rejects_foreign_url(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(updates, "launch_installer", launched.append)
    monkeypatch.setattr(updates.Updater, "can_install", property(lambda self: True))
    u = updates.Updater(_transport(_manifest(url="https://evil.example/kai.exe")))
    asyncio.run(u._install())
    assert u.state["phase"] == "error" and not launched

    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    ok = updates.Updater(_transport(_manifest()))
    asyncio.run(ok._install())
    assert ok.state["phase"] == "launched" and launched and launched[0].name == "Instalar-KAI-AI.exe"


def test_helper_script_waits_closes_installs_and_reopens(tmp_path):
    exe = tmp_path / "kai-desktop.exe"
    exe.write_bytes(b"MZ")
    script = updates.helper_script(tmp_path / "Instalar-KAI-AI.exe", "4321", exe)
    lines = script.split("\r\n")
    assert lines[2].startswith("ping -n")  # pausa compatible sin consola
    assert "taskkill /PID 4321 /F >nul 2>&1" in lines and not any("/T" in ln for ln in lines)
    assert f'"{tmp_path / "Instalar-KAI-AI.exe"}" /S' in lines
    assert lines.index(f'start "" "{exe}"') > lines.index(f'"{tmp_path / "Instalar-KAI-AI.exe"}" /S')
    # sin PID válido no se cierra nada por las dudas
    assert "taskkill" not in updates.helper_script(tmp_path / "x.exe", "abc", tmp_path / "no.exe")


def test_after_launch_shuts_down(monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "launch_installer", lambda p: None)
    monkeypatch.setattr(updates.Updater, "can_install", property(lambda self: True))
    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    real_sleep = asyncio.sleep
    monkeypatch.setattr(updates.asyncio, "sleep", lambda s: real_sleep(0))
    calls = []
    u = updates.Updater(_transport(_manifest()))
    u.after_launch = lambda: calls.append(True)
    asyncio.run(u._install())
    assert calls == [True]


def test_child_env_drops_pyinstaller_state(monkeypatch):
    from app.core.procenv import child_env

    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Users\pc\AppData\Local\Temp\_MEI000095fc2")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\KAI\kai-core.exe")
    monkeypatch.setenv("_MEIPASS2", r"C:\Temp\_MEI1")
    monkeypatch.setenv("KAI_ALGO", "sigue")
    env = child_env()
    assert not any(k.startswith(("_PYI_", "_MEIPASS")) for k in env)
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1" and env["KAI_ALGO"] == "sigue"


def test_installer_helper_gets_clean_env(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "C:/Temp/_MEI1")
    monkeypatch.setattr(updates.subprocess, "Popen", lambda cmd, **kw: calls.append(kw))
    updates.launch_installer(tmp_path / "Instalar-KAI-AI.exe")
    env = calls[-1]["env"]
    assert "_PYI_APPLICATION_HOME_DIR" not in env and env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_auto_update_downloads_waits_idle_and_installs(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(updates, "launch_installer", launched.append)
    monkeypatch.setattr(updates.Updater, "can_install", property(lambda self: True))
    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    real_sleep = asyncio.sleep
    monkeypatch.setattr(updates.asyncio, "sleep", lambda s: real_sleep(0))
    u = updates.Updater(_transport(_manifest()))
    idle_checks = iter([False, False, True])  # KAI en uso dos veces; después, libre

    async def run():
        return await u.auto_once(lambda: True, lambda: next(idle_checks))
    assert asyncio.run(run()) is True
    assert launched and u.state["phase"] == "launched"


def test_auto_update_respects_preference_and_no_news(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(updates, "launch_installer", launched.append)
    monkeypatch.setattr(updates.Updater, "can_install", property(lambda self: True))
    off = updates.Updater(_transport(_manifest()))
    assert asyncio.run(off.auto_once(lambda: False, lambda: True)) is False
    monkeypatch.setattr(updates, "current_build", lambda: (500, "abc"))  # ya tiene la última
    same = updates.Updater(_transport(_manifest()))
    assert asyncio.run(same.auto_once(lambda: True, lambda: True)) is False
    offline = updates.Updater(httpx.MockTransport(lambda r: httpx.Response(503)))
    assert asyncio.run(offline.auto_once(lambda: True, lambda: True)) is False
    assert not launched


def test_auto_update_preference_and_idle(client):
    assert client.get("/api/v1/settings").json()["preferences"]["auto_update"] is True
    ctx = client.app.state.ctx
    ctx.last_activity = float("-inf")
    assert ctx.idle_for(180)
    client.post("/api/v1/chat", json={"message": "hola", "stream": False})
    assert not ctx.idle_for(180)  # recién se usó: no se interrumpe con una actualización
