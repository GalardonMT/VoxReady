"""Contratos HTTP para progreso y agenda del vocero."""
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main
from schemas.schedule import ScheduleCreateRequest, ScheduleUpdateRequest


def _route_methods(path):
    return {
        method
        for route in main.app.routes
        if getattr(route, "path", None) == path
        for method in getattr(route, "methods", set())
    }


def test_progress_route_delegates_authenticated_claims(monkeypatch):
    captured = {}

    def get_progress(connection_string, claims, last_n):
        captured.update(connection_string=connection_string, claims=claims, last_n=last_n)
        return {"sessionsCount": 0}

    monkeypatch.setattr(main.progress_store, "get_progress", get_progress)
    monkeypatch.setattr(main, "SQL_CONN_STR", "azure-test")
    claims = {"sub": "external-user"}

    assert main.get_my_progress(lastN=7, user=claims) == {"sessionsCount": 0}
    assert captured == {
        "connection_string": "azure-test",
        "claims": claims,
        "last_n": 7,
    }
    assert _route_methods("/v1/me/progress") == {"GET"}


def test_schedule_routes_delegate_without_accepting_actor_ids(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "SQL_CONN_STR", "azure-test")
    monkeypatch.setattr(
        main.schedule_store,
        "list_calendar",
        lambda connection, claims, start, end: calls.append(
            ("list", connection, claims, start, end)
        ) or {"schedules": [], "sessions": []},
    )
    monkeypatch.setattr(
        main.schedule_store,
        "create_schedule",
        lambda connection, claims, scheduled_date, scenario_id: calls.append(
            ("create", connection, claims, scheduled_date, str(scenario_id))
        ) or {"id": "schedule-1"},
    )
    monkeypatch.setattr(
        main.schedule_store,
        "update_schedule",
        lambda connection, claims, schedule_id, **changes: calls.append(
            ("update", connection, claims, schedule_id, changes)
        ) or {"id": schedule_id},
    )
    monkeypatch.setattr(
        main.schedule_store,
        "cancel_schedule",
        lambda connection, claims, schedule_id: calls.append(
            ("cancel", connection, claims, schedule_id)
        ) or {"id": schedule_id, "status": "cancelled"},
    )
    monkeypatch.setattr(
        main.schedule_store,
        "start_schedule",
        lambda connection, claims, schedule_id: calls.append(
            ("start", connection, claims, schedule_id)
        ) or {"scheduleId": schedule_id, "sessionId": "session-public-1"},
    )

    claims = {"sub": "external-user"}
    start = date(2026, 10, 1)
    end = date(2026, 10, 31)
    scenario_id = "22112233-4455-6677-8899-aabbccddeeff"
    schedule_id = "33112233-4455-6677-8899-aabbccddeeff"

    assert main.get_my_schedule(fromDate=start, toDate=end, user=claims)["schedules"] == []
    assert main.create_my_schedule(
        payload=ScheduleCreateRequest(date="2026-10-15", scenarioId=scenario_id),
        user=claims,
    ) == {"id": "schedule-1"}
    assert main.update_my_schedule(
        schedule_id=schedule_id,
        payload=ScheduleUpdateRequest(date="2026-10-20"),
        user=claims,
    ) == {"id": schedule_id}
    assert main.cancel_my_schedule(schedule_id=schedule_id, user=claims)["status"] == "cancelled"
    assert main.start_my_scheduled_practice(schedule_id=schedule_id, user=claims)["sessionId"] == "session-public-1"

    assert calls == [
        ("list", "azure-test", claims, start, end),
        ("create", "azure-test", claims, date(2026, 10, 15), scenario_id),
        (
            "update",
            "azure-test",
            claims,
            schedule_id,
            {"scheduled_date": date(2026, 10, 20), "scenario_id": None},
        ),
        ("cancel", "azure-test", claims, schedule_id),
        ("start", "azure-test", claims, schedule_id),
    ]
    assert _route_methods("/v1/me/schedule") == {"GET", "POST"}
    assert _route_methods(f"/v1/me/schedule/{{schedule_id}}") == {"PATCH"}
    assert _route_methods(f"/v1/me/schedule/{{schedule_id}}/cancel") == {"POST"}
    assert _route_methods(f"/v1/me/schedule/{{schedule_id}}/start") == {"POST"}

