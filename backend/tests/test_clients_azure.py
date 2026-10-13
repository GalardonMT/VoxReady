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
    users = {role: str(uuid.uuid4()) for role in ("master_config", "spokesperson", "client_admin")}
    for role, user_id in users.items():
        cursor.execute(
            """INSERT INTO dbo.app_user(id,client_id,email,display_name,role)
               VALUES(?,?,?,?,?)""",
            user_id,
            None if role == "master_config" else existing_client_id,
            f"{user_id}@example.invalid",
            "Prueba clientes",
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
