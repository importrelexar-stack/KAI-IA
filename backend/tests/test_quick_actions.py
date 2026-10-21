from __future__ import annotations

import pytest

from app.automation import apps_catalog as ac
from app.services import quick_actions as qa
from tests.conftest import parse_sse

APPS = [ac.InstalledApp("Excel", app_id="Microsoft.Office.EXCEL.EXE.15"),
        ac.InstalledApp("Calculadora", app_id="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
        ac.InstalledApp("Visual Studio Code", app_id="Code"), ac.InstalledApp("Visual Studio 2022", app_id="VS")]


@pytest.fixture
def opened(monkeypatch):
    cat = ac.AppCatalog()
    monkeypatch.setattr(cat, "apps", lambda: APPS)
    monkeypatch.setattr(ac, "catalog", cat)
    launched: list[str] = []
    monkeypatch.setattr(ac, "launch", lambda app: launched.append(app.name) or f"Abrí «{app.name}».")
    return launched


@pytest.mark.parametrize("text,name", [
    ("abrí Excel", "Excel"), ("Abrime la calculadora", "calculadora"), ("abrir excel por favor", "excel"),
    ("Hey KAI, abrí el programa Excel.", "Excel"), ("iniciá la app de Excel", "Excel"),
    ("abre visual studio code", "visual studio code"),
])
def test_detects_open_app(text, name):
    assert qa.app_name_in(text) == name


@pytest.mark.parametrize("text", [
    "abrí Excel y armá una planilla de ventas", "abrí el archivo informe.pdf", "abrí la carpeta Descargas",
    "¿cómo abro Excel?", "abrí C:\\datos\\x.xlsx", "contame un chiste", "abrí la página de mercado libre",
])
def test_ignores_other_requests(text):
    assert qa.app_name_in(text) is None


def test_chat_opens_app_without_calling_the_model(client, providers, opened):
    r = client.post("/api/v1/chat", json={"message": "abrí Excel"})
    events = parse_sse(r.text)
    assert opened == ["Excel"]
    assert [e["type"] for e in events] == ["meta", "tool", "delta", "done"]
    assert events[-1]["assistant_message"]["content"] == "Listo, abrí «Excel»."
    assert all(not p.calls for p in providers)  # no se consultó al modelo


def test_ambiguous_or_unknown_goes_to_the_model(client, providers, opened):
    client.post("/api/v1/chat", json={"message": "abrí visual studio", "stream": False})
    client.post("/api/v1/chat", json={"message": "abrí photoshop", "stream": False})
    assert opened == [] and sum(len(p.calls) for p in providers) == 2


def test_respects_ask_level(client, providers, opened):
    perms = client.get("/api/v1/automation/permissions").json()
    client.put("/api/v1/automation/permissions", json={**perms, "levels": {"abrir_aplicacion": "ask"}})
    client.post("/api/v1/chat", json={"message": "abrí Excel", "stream": False})
    assert opened == [] and sum(len(p.calls) for p in providers) == 1
