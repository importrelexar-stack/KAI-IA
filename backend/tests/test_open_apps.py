from __future__ import annotations

import pytest

from app.agents import automation_tools as at
from app.automation import apps_catalog as ac
from app.automation.permissions import AppEntry, Permissions
from app.core.errors import KaiError

APPS = [ac.InstalledApp("Calculadora", app_id="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
        ac.InstalledApp("Excel", app_id="Microsoft.Office.EXCEL.EXE.15"),
        ac.InstalledApp("Google Chrome", app_id="Chrome"),
        ac.InstalledApp("Bloc de notas", app_id="{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\notepad.exe"),
        ac.InstalledApp("Visual Studio Code", app_id="Microsoft.VisualStudioCode"),
        ac.InstalledApp("Visual Studio 2022", app_id="VisualStudio.2022")]


@pytest.fixture
def catalog(monkeypatch):
    cat = ac.AppCatalog()
    monkeypatch.setattr(cat, "apps", lambda: APPS)
    monkeypatch.setattr(ac, "catalog", cat)
    launched = []
    monkeypatch.setattr(ac, "launch", lambda app: launched.append(app) or f"Abrí «{app.name}».")
    return launched


def test_find_by_name_alias_and_accents(catalog):
    assert ac.catalog.find("excel").name == "Excel"
    assert ac.catalog.find("CALCULADORA").name == "Calculadora"
    assert ac.catalog.find("calculator").name == "Calculadora"  # alias en inglés
    assert ac.catalog.find("chrome").name == "Google Chrome"
    assert ac.catalog.find("bloc de notas").name == "Bloc de notas"
    with pytest.raises(KaiError) as e:
        ac.catalog.find("visual studio")
    assert e.value.code == "ambiguous" and "Visual Studio Code" in e.value.message
    with pytest.raises(KaiError) as e:
        ac.catalog.find("photoshop")
    assert e.value.code == "app_not_found"


def test_tool_opens_start_menu_app_without_asking(catalog, client):
    perms = Permissions()
    assert perms.start_menu_apps and perms.level("abrir_aplicacion") == "allow"
    ok, msg = at.execute("abrir_aplicacion", {"nombre": "excel"}, perms, [])
    assert ok and catalog[0].name == "Excel" and "Excel" in msg


def test_registered_app_wins_and_toggle_off_blocks(catalog, monkeypatch):
    monkeypatch.setattr(at, "resolve_app", lambda a: "C:/apps/mi-excel.exe")
    monkeypatch.setattr(at.fs, "launch_app", lambda exe: f"Aplicación iniciada: {exe}")
    perms = Permissions(apps=[AppEntry(name="excel", command="C:/apps/mi-excel.exe")], start_menu_apps=False)
    assert at.execute("abrir_aplicacion", {"nombre": "Excel"}, perms, [])[1].endswith("mi-excel.exe")
    with pytest.raises(KaiError) as e:
        at.execute("abrir_aplicacion", {"nombre": "chrome"}, perms, [])
    assert e.value.code == "disabled" and not catalog


def test_permissions_roundtrip_and_endpoint(client, catalog):
    r = client.get("/api/v1/automation/permissions").json()
    assert r["start_menu_apps"] is True and r["levels"]["abrir_aplicacion"] == "allow"
    r = client.put("/api/v1/automation/permissions", json={"folders": [], "apps": [], "scripts": [], "levels": {},
                                                           "start_menu_apps": False})
    assert r.status_code == 200 and r.json()["start_menu_apps"] is False
    assert client.get("/api/v1/automation/permissions").json()["start_menu_apps"] is False
    apps = client.get("/api/v1/automation/installed-apps?q=visual").json()
    assert apps["apps"] == ["Visual Studio Code", "Visual Studio 2022"]


def test_unsafe_app_ids_are_dropped(monkeypatch):
    import json
    import subprocess

    rows = [{"Name": "Bien", "AppID": "Chrome"}, {"Name": "Mal", "AppID": 'x" & calc'}]
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(rows), ""))
    assert [a.name for a in ac._from_start_apps()] == ["Bien"]
