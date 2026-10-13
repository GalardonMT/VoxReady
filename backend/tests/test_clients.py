"""Contratos locales de validacion, autorizacion y persistencia de clientes."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import client_store


CLIENT_COLUMNS = (
    "id", "name", "status", "createdAt", "updatedAt", "isDeleted", "deletedAt",
)


class ClientCursor:
    def __init__(self):
        self.role = "master_config"
        self.actor_id = str(uuid.uuid4())
        self.actor_client_id = None
        self.description = []
        self.clients = {}
        self.mode = None
        self.insert_count = 0
        self.client_query_count = 0

    def execute(self, sql, *params):
        normalized = " ".join(sql.split()).lower()
        if "from dbo.app_user" in normalized:
            self.mode = "profile"
        elif normalized.startswith("insert into dbo.client"):
            client_id, name, status = params
            now = datetime.now(timezone.utc)
            self.clients[client_id] = (client_id, name, status, now, now, False, None)
            self.insert_count += 1
            self.mode = "insert"
        elif "from dbo.client where id=?" in normalized:
            self.description = [(column,) for column in CLIENT_COLUMNS]
            self.selected_id = params[0]
            self.client_query_count += 1
            self.mode = "client"
        elif "from dbo.client where is_deleted=0" in normalized:
            self.description = [(column,) for column in CLIENT_COLUMNS]
            requested_status = params[0] if params else None
            values = list(self.clients.values())
            if requested_status:
                values = [row for row in values if row[2] == requested_status]
            self.selected_clients = sorted(values, key=lambda row: (row[1].casefold(), row[0]))
            self.client_query_count += 1
            self.mode = "clients"
        else:
            raise AssertionError(f"SQL inesperado: {sql}")
        return self

    def fetchone(self):
        if self.mode == "profile":
            return self.actor_id, self.actor_client_id, self.role
        if self.mode == "client":
            return self.clients.get(self.selected_id)
        return None

    def fetchall(self):
        return list(self.selected_clients) if self.mode == "clients" else []


@contextmanager
def _database(cursor):
    yield cursor


def _api(monkeypatch, cursor):
    monkeypatch.setattr(main.master_store, "database", lambda _connection: _database(cursor))
    main.app.dependency_overrides[main.verify_token] = lambda: {
        "sub": cursor.actor_id,
        "role": "master_config",  # No es confiable; resolve_user usa app_user.
    }
    return TestClient(main.app)


def test_master_creates_and_lists_persisted_client(monkeypatch):
    cursor = ClientCursor()
    try:
        with _api(monkeypatch, cursor) as api:
            created = api.post("/v1/api/master/clients", json={
                "name": "  Empresa Persistente  ", "status": "suspended",
            })
            assert created.status_code == 201, created.text
            payload = created.json()
            assert uuid.UUID(payload["id"])
            assert payload["name"] == "Empresa Persistente"
            assert payload["status"] == "suspended"
            assert payload["isDeleted"] is False
        # Un cliente nuevo de API representa un reinicio sin limpiar el almacen persistente.
        with _api(monkeypatch, cursor) as restarted_api:
            listed = restarted_api.get("/v1/api/master/clients?status=all")
            assert listed.status_code == 200, listed.text
            assert listed.json()["items"] == [payload]
            assert listed.json()["total"] == 1
        assert cursor.insert_count == 1
    finally:
        main.app.dependency_overrides.clear()


def test_client_validation_rejects_invalid_payloads_before_writing(monkeypatch):
    cursor = ClientCursor()
    try:
        with _api(monkeypatch, cursor) as api:
            assert main.MasterClientRequest(name="Empresa").status == "active"
            for body in (
                {"name": "   ", "status": "active"},
                {"name": "x" * 151, "status": "active"},
                {"name": "Empresa", "status": "archived"},
            ):
                response = api.post("/v1/api/master/clients", json=body)
                assert response.status_code == 422, response.text
            assert api.get("/v1/api/master/clients?status=unknown").status_code == 422
        assert cursor.insert_count == 0
    finally:
        main.app.dependency_overrides.clear()


def test_database_role_denies_spokesperson_and_client_admin(monkeypatch):
    cursor = ClientCursor()
    cursor.actor_client_id = str(uuid.uuid4())
    try:
        with _api(monkeypatch, cursor) as api:
            for role in ("spokesperson", "client_admin"):
                cursor.role = role
                assert api.get("/v1/api/master/clients?status=all").status_code == 403
                denied = api.post("/v1/api/master/clients", json={
                    "name": "No autorizada", "status": "active", "role": "master_config",
                })
                assert denied.status_code == 403
        assert cursor.insert_count == 0
        assert cursor.client_query_count == 0
    finally:
        main.app.dependency_overrides.clear()


def test_client_migration_is_idempotent_and_never_replaces_or_deletes_the_table():
    sql = " ".join(client_store.CLIENT_SCHEMA_DDL.lower().split())
    assert "object_id(n'dbo.client', n'u') is null" in sql
    assert "falta la tabla existente dbo.client" in sql
    assert "alter table dbo.client add created_at" in sql
    assert "alter table dbo.client with check add constraint ck_client_status" in sql
    assert "alter table dbo.client with check add constraint ck_client_name" in sql
    assert "create table" not in sql
    assert "drop table" not in sql
    assert "delete from" not in sql
