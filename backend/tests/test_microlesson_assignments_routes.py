"""Public contracts and role-safe request validation for lesson assignments."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import microlessons


def test_assignment_uuid_comparison_accepts_pyodbc_case_variants():
    identifier = "0f7b7d20-3aff-4d28-a0de-8f5b7b1ac00e"
    assert microlessons._same_uid(identifier.upper(), identifier)
    assert not microlessons._same_uid(identifier, "0f7b7d20-3aff-4d28-a0de-8f5b7b1ac00f")


def test_spokesperson_assignment_routes(monkeypatch):
    calls = []

    def invoke(name, *args):
        calls.append((name, args))
        return {"assignmentId": "cycle", "assignmentStatus": name}

    monkeypatch.setattr(main.microlesson_store, "recommendations", lambda *args: {"items": [], "total": 0})
    monkeypatch.setattr(main.microlesson_store, "start_spokesperson", lambda *args: invoke("in_progress", *args))
    monkeypatch.setattr(main.microlesson_store, "complete_spokesperson", lambda *args: invoke("completed", *args))
    monkeypatch.setattr(main.microlesson_store, "restart_spokesperson", lambda *args: invoke("assigned", *args))
    main.app.dependency_overrides[main.verify_token] = lambda: {"sub": "user"}
    try:
        with TestClient(main.app) as client:
            assert client.get("/v1/microlessons/recommendations").json() == {"items": [], "total": 0}
            lesson_id = "00000000-0000-0000-0000-000000000001"
            for action, expected in (("start", "in_progress"), ("complete", "completed"), ("restart", "assigned")):
                response = client.post(f"/v1/microlessons/{lesson_id}/{action}")
                assert response.status_code == 200, response.text
                assert response.json()["assignmentStatus"] == expected
            assert len(calls) == 3
    finally:
        main.app.dependency_overrides.clear()


def test_master_assignment_request_contract(monkeypatch):
    received = []
    monkeypatch.setattr(main.microlesson_store, "assign_master", lambda *args: received.append(args) or {"items": [], "total": 0})
    main.app.dependency_overrides[main.verify_token] = lambda: {"sub": "master"}
    try:
        with TestClient(main.app) as client:
            lesson_id = "00000000-0000-0000-0000-000000000001"
            user_id = "00000000-0000-0000-0000-000000000002"
            path = f"/v1/api/master/microlessons/{lesson_id}/assignments"
            assert client.post(path, json={"userIds": [user_id], "sortOrder": 1}).status_code == 200
            assert received
            assert client.post(path, json={"userIds": [], "sortOrder": 1}).status_code == 422
            assert client.post(path, json={"userIds": [user_id], "sortOrder": 0}).status_code == 422
            assert client.post(path, json={"userIds": [user_id, user_id], "sortOrder": 1}).status_code == 422
    finally:
        main.app.dependency_overrides.clear()
