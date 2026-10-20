from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.models.entities import Routine
from app.routines import schedule as sched
from app.routines.runner import run_due

AR = ZoneInfo("America/Argentina/Buenos_Aires")
NY = ZoneInfo("America/New_York")


def test_next_run_daily_weekly_interval():
    friday_noon = datetime(2026, 10, 23, 12, 0, tzinfo=AR)
    weekdays = sched.parse({"type": "weekly", "days": [0, 1, 2, 3, 4], "time": "08:00"})
    assert sched.next_run(weekdays, friday_noon, AR) == datetime(2026, 10, 26, 8, 0, tzinfo=AR)
    daily = sched.parse({"type": "daily", "time": "08:00"})
    assert sched.next_run(daily, datetime(2026, 10, 23, 7, 59, tzinfo=AR), AR) == datetime(2026, 10, 23, 8, 0, tzinfo=AR)
    assert sched.next_run(daily, datetime(2026, 10, 23, 8, 0, tzinfo=AR), AR) == datetime(2026, 10, 24, 8, 0, tzinfo=AR)
    every = sched.parse({"type": "interval", "minutes": 90})
    assert sched.next_run(every, friday_noon, AR) == friday_noon + timedelta(minutes=90)
    # Cambio de horario (Nueva York, 1/11/2026): las 8:00 siguen siendo las 8:00 locales
    nxt = sched.next_run(daily, datetime(2026, 10, 31, 9, 0, tzinfo=NY), NY)
    assert nxt.astimezone(NY).hour == 8 and nxt.astimezone(NY).utcoffset() == timedelta(hours=-5)
    assert sched.describe(weekdays) == "de lunes a viernes a las 08:00"
    assert sched.describe(every) == "cada 1 h 30 min"


def test_schedule_validation():
    for bad in ({"type": "daily", "time": "25:00"}, {"type": "interval", "minutes": 5},
                {"type": "weekly", "days": [7], "time": "08:00"}, {"type": "cron", "expr": "* * * * *"}):
        with pytest.raises(ValidationError):
            sched.parse(bad)


def test_routine_crud_and_run_now(make_client, providers):
    with make_client(provider_kwargs={"reply": "Tenés 2 tareas."}) as c:
        r = c.post("/api/v1/routines", json={"name": "Resumen", "prompt": "Resumime mis tareas pendientes",
                                               "schedule": {"type": "daily", "time": "08:00"}})
        assert r.status_code == 201, r.text
        rt = r.json()
        assert rt["schedule_text"] == "todos los días a las 08:00" and rt["next_run_at"]
        assert c.post("/api/v1/routines/" + rt["id"] + "/run").status_code == 202
        for _ in range(50):
            got = c.get("/api/v1/routines").json()[0]
            if got["last_status"] == "ok":
                break
            time.sleep(0.1)
        assert got["last_status"] == "ok" and got["run_count"] == 1 and got["conversation_id"]
        conv = c.get(f"/api/v1/conversations/{got['conversation_id']}").json()
        assert conv["messages"][0]["content"].startswith("[Rutina programada «Resumen»")
        assert conv["title"] == "Rutina: Resumen"
        assert conv["messages"][-1]["content"].strip() == "Tenés 2 tareas."
        audit = c.get("/api/v1/audit").json()
        assert any(e["action"] == "routine.run" for e in audit)

        r = c.patch(f"/api/v1/routines/{rt['id']}", json={"enabled": False}).json()
        assert r["enabled"] is False and r["next_run_at"] is None
        assert c.delete(f"/api/v1/routines/{rt['id']}").status_code == 204
        assert c.get("/api/v1/routines").json() == []


def test_due_routine_runs_once_and_keeps_approvals_pending(make_client, providers, tmp_path):
    script = [("crear_tarea", {"titulo": "Pagar luz", "requiere_autorizacion": True})]
    with make_client(provider_kwargs={"tool_script": script}) as c:
        rt = c.post("/api/v1/routines", json={"name": "Diaria", "prompt": "Anotá el pago de la luz",
                                                "schedule": {"type": "interval", "minutes": 60}}).json()
        ctx = c.app.state.ctx
        with ctx.db.SessionLocal() as db:  # vencida (como si la PC hubiera estado apagada)
            db.get(Routine, rt["id"]).next_run_at = datetime.now(timezone.utc) - timedelta(days=3)
            db.commit()
        ran = c.portal.call(run_due, ctx)
        assert ran == [rt["id"]]
        assert c.portal.call(run_due, ctx) == []  # no se repite
        got = c.get("/api/v1/routines").json()[0]
        assert got["run_count"] == 1
        assert datetime.fromisoformat(got["next_run_at"]) > datetime.now(timezone.utc) + timedelta(minutes=55)
        assert providers[-1].tool_results[0].ok
        tasks = c.get("/api/v1/tasks").json()
        task = next(t for t in tasks if t["title"] == "Pagar luz")
        assert task["requires_approval"] and task["status"] == "pending" and task["approvals"] == []


def test_routine_validation_and_local_only(client):
    bad = client.post("/api/v1/routines", json={"name": "X", "prompt": "hola", "schedule": {"type": "interval", "minutes": 1}})
    assert bad.status_code == 422
    from fastapi.testclient import TestClient

    client.put("/api/v1/devices/remote", json={"enabled": True})
    code = client.post("/api/v1/devices/pairing").json()["code"]
    remote = TestClient(client.app, client=("192.168.1.50", 5000), base_url="http://192.168.1.10:8765")
    token = remote.post("/api/v1/devices/pair", json={"code": code}).json()["token"]
    assert remote.get("/api/v1/routines", headers={"Authorization": f"Bearer {token}"}).status_code == 403
