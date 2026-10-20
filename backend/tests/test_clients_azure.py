"""Integracion opt-in con Azure SQL; toda la prueba se revierte al terminar."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import main

pytestmark = pytest.mark.skipif(
    os.getenv("VOXREADY_TEST_AZURE_SQL") != "1",
    reason="Azure SQL integration is opt-in",
)


@pytest.fixture
def azure_clients(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "seed", BACKEND / "scripts" / "seed_master_topics.py",
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    connection = seed.connect()
    cursor = connection.cursor()
    cursor.execute("SET XACT_ABORT OFF; IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
    cursor.execute("SELECT TOP 1 id FROM dbo.client WHERE is_deleted=0 ORDER BY id")
    existing_client_id = str(cursor.fetchone()[0])
    users = {
        key: str(uuid.uuid4())
        for key in ("master_config", "spokesperson", "client_admin", "eligible_one", "eligible_two", "eligible_three")
    }
    user_records = (
        ("master_config", "master_config", None),
        ("spokesperson", "spokesperson", existing_client_id),
        ("client_admin", "client_admin", existing_client_id),
        ("eligible_one", "spokesperson", None),
        ("eligible_two", "spokesperson", None),
        ("eligible_three", "spokesperson", None),
    )
    for key, role, client_id in user_records:
        user_id = users[key]
        cursor.execute(
            """INSERT INTO dbo.app_user(id,client_id,email,display_name,role)
               VALUES(?,?,?,?,?)""",
            user_id,
            client_id,
            f"{user_id}@example.invalid",
            f"Prueba clientes {key}",
            role,
        )

    current = {"role": "master_config"}

    @contextmanager
    def transactional_database(_connection_string):
        request_cursor = connection.cursor()
        request_cursor.execute("SAVE TRANSACTION test_clients_request")
        try:
            yield request_cursor
        except Exception:
            request_cursor.execute("ROLLBACK TRANSACTION test_clients_request")
            raise
        finally:
            request_cursor.close()

    monkeypatch.setattr(main.master_store, "database", transactional_database)
    main.app.dependency_overrides[main.verify_token] = lambda: {
        "sub": users[current["role"]],
        "role": "master_config",
    }
    try:
        yield connection, cursor, current, users, existing_client_id
    finally:
        main.app.dependency_overrides.clear()
        connection.rollback()
        connection.close()


def test_client_creation_persists_across_api_restart_and_preserves_user_membership(azure_clients):
    _connection, cursor, current, users, existing_client_id = azure_clients
    with TestClient(main.app) as api:
        response = api.post("/v1/api/master/clients", json={
            "name": "  Empresa integración reinicio  ",
            "status": "active",
        })
        assert response.status_code == 201, response.text
        created = response.json()
        assert created["name"] == "Empresa integración reinicio"
        assert created["status"] == "active"

    # Un segundo TestClient reinicia el ciclo de vida HTTP, conservando la fila SQL.
    with TestClient(main.app) as restarted_api:
        listed = restarted_api.get("/v1/api/master/clients?status=all")
        assert listed.status_code == 200, listed.text
        assert any(item["id"].lower() == created["id"].lower() for item in listed.json()["items"])

        for role in ("spokesperson", "client_admin"):
            current["role"] = role
            assert restarted_api.get("/v1/api/master/clients?status=all").status_code == 403
            assert restarted_api.post("/v1/api/master/clients", json={
                "name": "Prohibida", "status": "active",
            }).status_code == 403

    cursor.execute("SELECT id,name,status,is_deleted FROM dbo.client WHERE id=?", created["id"])
    stored = cursor.fetchone()
    assert stored is not None
    assert stored[1:] == ("Empresa integración reinicio", "active", False)
    cursor.execute(
        "SELECT role,client_id FROM dbo.app_user WHERE id IN (?,?) ORDER BY role",
        users["spokesperson"], users["client_admin"],
    )
    memberships = cursor.fetchall()
    assert len(memberships) == 2
    assert all(str(row[1]).lower() == existing_client_id.lower() for row in memberships)


def test_azure_endpoint_rejects_invalid_client_values_without_rows(azure_clients):
    _connection, cursor, current, _users, _existing_client_id = azure_clients
    current["role"] = "master_config"
    before_name = "No debe persistir"
    with TestClient(main.app) as api:
        for body in (
            {"name": "  ", "status": "active"},
            {"name": "x" * 151, "status": "active"},
            {"name": before_name, "status": "archived"},
        ):
            assert api.post("/v1/api/master/clients", json=body).status_code == 422
    cursor.execute("SELECT COUNT(*) FROM dbo.client WHERE name=?", before_name)
    assert cursor.fetchone()[0] == 0


def test_azure_create_and_later_link_spokespersons_are_persistent_and_idempotent(azure_clients):
    _connection, cursor, current, users, _existing_client_id = azure_clients
    current["role"] = "master_config"
    with TestClient(main.app) as api:
        created_response = api.post("/v1/api/master/clients", json={
            "name": "Empresa integración con voceros",
            "status": "active",
            "spokespersonIds": [users["eligible_one"], users["eligible_two"]],
        })
        assert created_response.status_code == 201, created_response.text
        client_id = created_response.json()["id"]

    # Otro ciclo HTTP debe leer los vínculos desde Azure SQL, no desde memoria.
    with TestClient(main.app) as restarted_api:
        candidates = restarted_api.get(f"/v1/api/master/spokespersons?clientId={client_id}")
        assert candidates.status_code == 200, candidates.text
        states = {item["id"].lower(): item["linkState"] for item in candidates.json()["items"]}
        assert states[users["eligible_one"].lower()] == "linked"
        assert states[users["eligible_two"].lower()] == "linked"
        assert states[users["eligible_three"].lower()] == "available"
        assert states[users["spokesperson"].lower()] == "assigned_elsewhere"

        linked = restarted_api.post(f"/v1/api/master/clients/{client_id}/spokespersons", json={
            "spokespersonIds": [users["eligible_one"], users["eligible_three"]],
        })
        assert linked.status_code == 200, linked.text
        repeated = restarted_api.post(f"/v1/api/master/clients/{client_id}/spokespersons", json={
            "spokespersonIds": [users["eligible_one"], users["eligible_three"]],
        })
        assert repeated.status_code == 200, repeated.text

    cursor.execute(
        "SELECT id,client_id FROM dbo.app_user WHERE id IN (?,?,?)",
        users["eligible_one"], users["eligible_two"], users["eligible_three"],
    )
    memberships = {str(row[0]).lower(): str(row[1]).lower() for row in cursor.fetchall()}
    assert set(memberships) == {
        users["eligible_one"].lower(), users["eligible_two"].lower(), users["eligible_three"].lower(),
    }
    assert set(memberships.values()) == {client_id.lower()}


def test_azure_link_conflict_and_failed_create_leave_no_partial_rows(azure_clients):
    _connection, cursor, current, users, _existing_client_id = azure_clients
    current["role"] = "master_config"
    target_name = f"Rollback vínculos {uuid.uuid4()}"
    with TestClient(main.app) as api:
        target = api.post("/v1/api/master/clients", json={"name": "Destino conflictos"})
        assert target.status_code == 201, target.text
        target_id = target.json()["id"]

        conflict = api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
            "spokespersonIds": [users["eligible_one"], users["spokesperson"]],
        })
        assert conflict.status_code == 409, conflict.text

        failed_create = api.post("/v1/api/master/clients", json={
            "name": target_name,
            "spokespersonIds": [users["eligible_two"], users["spokesperson"]],
        })
        assert failed_create.status_code == 409, failed_create.text

    cursor.execute("SELECT client_id FROM dbo.app_user WHERE id=?", users["eligible_one"])
    assert cursor.fetchone()[0] is None
    cursor.execute("SELECT client_id FROM dbo.app_user WHERE id=?", users["eligible_two"])
    assert cursor.fetchone()[0] is None
    cursor.execute("SELECT COUNT(*) FROM dbo.client WHERE name=?", target_name)
    assert cursor.fetchone()[0] == 0


def test_azure_non_master_roles_cannot_read_or_link_spokespersons(azure_clients):
    _connection, _cursor, current, users, existing_client_id = azure_clients
    with TestClient(main.app) as api:
        for role in ("spokesperson", "client_admin"):
            current["role"] = role
            assert api.get(f"/v1/api/master/spokespersons?clientId={existing_client_id}").status_code == 403
            assert api.post(f"/v1/api/master/clients/{existing_client_id}/spokespersons", json={
                "spokespersonIds": [users["eligible_one"]],
            }).status_code == 403
