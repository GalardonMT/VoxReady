"""Contratos locales de validacion, autorizacion y persistencia de clientes."""
from contextlib import contextmanager
import copy
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
        self.rowcount = -1

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
        elif normalized.startswith("select id,name from dbo.client"):
            self.selected_id = params[0]
            self.mode = "required_client"
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
        if self.mode == "required_client":
            row = self.clients.get(self.selected_id)
            return (row[0], row[1]) if row else None
        return None

    def fetchall(self):
        return list(self.selected_clients) if self.mode == "clients" else []


@contextmanager
def _database(cursor):
    clients = copy.deepcopy(cursor.clients)
    users = copy.deepcopy(getattr(cursor, "users", None))
    try:
        yield cursor
    except Exception:
        cursor.clients = clients
        if users is not None:
            cursor.users = users
        raise


class MembershipCursor(ClientCursor):
    USER_COLUMNS = ("id", "displayName", "email", "clientId", "clientName")

    def __init__(self):
        super().__init__()
        self.users = {}
        self.force_update_conflict = False
        self.executed_sql = []

    def add_user(self, *, role="spokesperson", client_id=None, name="Vocero", email=None):
        user_id = str(uuid.uuid4())
        self.users[user_id] = {
            "id": user_id,
            "role": role,
            "client_id": client_id,
            "name": name,
            "email": email or f"{user_id}@example.invalid",
        }
        return user_id

    def execute(self, sql, *params):
        normalized = " ".join(sql.split()).lower()
        self.executed_sql.append(normalized)
        self.rowcount = -1
        if normalized.startswith("select u.id,u.display_name as displayname"):
            search = str(params[0]).casefold()
            rows = []
            for user in self.users.values():
                if user["role"] != "spokesperson":
                    continue
                if search and search not in user["name"].casefold() and search not in user["email"].casefold():
                    continue
                client = self.clients.get(user["client_id"])
                rows.append((user["id"], user["name"], user["email"], user["client_id"], client[1] if client else None))
            self.description = [(column,) for column in self.USER_COLUMNS]
            self.selected_users = sorted(rows, key=lambda row: (row[1].casefold(), row[2].casefold(), row[0]))
            self.mode = "candidate_users"
            return self
        if normalized.startswith("select id,role,client_id,display_name,email from dbo.app_user"):
            self.selected_user_id = params[0]
            self.mode = "locked_user"
            return self
        if normalized.startswith("update dbo.app_user set client_id="):
            client_id, user_id = params
            user = self.users.get(user_id)
            if self.force_update_conflict:
                self.rowcount = 0
            elif user and user["role"] == "spokesperson" and user["client_id"] is None:
                user["client_id"] = client_id
                self.rowcount = 1
            else:
                self.rowcount = 0
            self.mode = "update_user"
            return self
        return super().execute(sql, *params)

    def fetchone(self):
        if self.mode == "locked_user":
            user = self.users.get(self.selected_user_id)
            if not user:
                return None
            return user["id"], user["role"], user["client_id"], user["name"], user["email"]
        return super().fetchone()

    def fetchall(self):
        if self.mode == "candidate_users":
            return list(self.selected_users)
        return super().fetchall()


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


def _add_client(cursor, name="Empresa existente"):
    client_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    cursor.clients[client_id] = (client_id, name, "active", now, now, False, None)
    return client_id


def test_master_creates_client_with_multiple_eligible_spokespersons(monkeypatch):
    cursor = MembershipCursor()
    first = cursor.add_user(name="Ana Vocera", email="ana@example.invalid")
    second = cursor.add_user(name="Bea Vocera", email="bea@example.invalid")
    try:
        with _api(monkeypatch, cursor) as api:
            response = api.post("/v1/api/master/clients", json={
                "name": "Empresa con voceros",
                "status": "active",
                "spokespersonIds": [first, second],
            })
            assert response.status_code == 201, response.text
            client_id = response.json()["id"]
            assert cursor.users[first]["client_id"].lower() == client_id.lower()
            assert cursor.users[second]["client_id"].lower() == client_id.lower()
        # Un nuevo ciclo HTTP conserva los vinculos en el almacen persistente.
        with _api(monkeypatch, cursor) as restarted_api:
            candidates = restarted_api.get(f"/v1/api/master/spokespersons?clientId={client_id}")
            assert candidates.status_code == 200, candidates.text
            states = {item["id"]: item["linkState"] for item in candidates.json()["items"]}
            assert states[first] == "linked"
            assert states[second] == "linked"
    finally:
        main.app.dependency_overrides.clear()


def test_master_lists_candidates_and_links_after_client_creation(monkeypatch):
    cursor = MembershipCursor()
    target_id = _add_client(cursor, "Destino")
    other_id = _add_client(cursor, "Otra empresa")
    available = cursor.add_user(name="Disponible", email="disponible@example.invalid")
    linked = cursor.add_user(client_id=target_id, name="Ya vinculado")
    elsewhere = cursor.add_user(client_id=other_id, name="No trasladable")
    try:
        with _api(monkeypatch, cursor) as api:
            candidates = api.get(f"/v1/api/master/spokespersons?clientId={target_id}")
            assert candidates.status_code == 200, candidates.text
            states = {item["id"]: item["linkState"] for item in candidates.json()["items"]}
            assert states == {available: "available", elsewhere: "assigned_elsewhere", linked: "linked"}

            linked_response = api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
                "spokespersonIds": [linked, available, available],
            })
            assert linked_response.status_code == 200, linked_response.text
            assert cursor.users[available]["client_id"] == target_id
            # Repetir exactamente la operacion es idempotente.
            repeated = api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
                "spokespersonIds": [linked, available],
            })
            assert repeated.status_code == 200, repeated.text
            assert set(repeated.json()["spokespersonIds"]) == {linked, available}
    finally:
        main.app.dependency_overrides.clear()


def test_link_rejects_missing_wrong_role_and_other_client_without_partial_writes(monkeypatch):
    for invalid_kind in ("missing", "wrong_role", "other_client"):
        cursor = MembershipCursor()
        target_id = _add_client(cursor, "Destino")
        other_id = _add_client(cursor, "Origen")
        eligible = cursor.add_user(name="Elegible")
        if invalid_kind == "missing":
            invalid = str(uuid.uuid4())
        elif invalid_kind == "wrong_role":
            invalid = cursor.add_user(role="client_admin", client_id=target_id, name="Administrador")
        else:
            invalid = cursor.add_user(client_id=other_id, name="Vocero ocupado")
        try:
            with _api(monkeypatch, cursor) as api:
                response = api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
                    "spokespersonIds": [eligible, invalid],
                })
                assert response.status_code == 409, response.text
                assert cursor.users[eligible]["client_id"] is None
        finally:
            main.app.dependency_overrides.clear()


def test_failed_create_rolls_back_client_and_memberships(monkeypatch):
    cursor = MembershipCursor()
    other_id = _add_client(cursor, "Empresa original")
    eligible = cursor.add_user(name="Elegible")
    unavailable = cursor.add_user(client_id=other_id, name="Ya asignado")
    before_clients = set(cursor.clients)
    try:
        with _api(monkeypatch, cursor) as api:
            response = api.post("/v1/api/master/clients", json={
                "name": "No debe quedar",
                "spokespersonIds": [eligible, unavailable],
            })
            assert response.status_code == 409, response.text
        assert set(cursor.clients) == before_clients
        assert cursor.users[eligible]["client_id"] is None
        assert cursor.users[unavailable]["client_id"] == other_id
    finally:
        main.app.dependency_overrides.clear()


def test_conditional_update_conflict_rolls_back_and_sql_uses_sql_server_locks(monkeypatch):
    cursor = MembershipCursor()
    target_id = _add_client(cursor)
    eligible = cursor.add_user()
    cursor.force_update_conflict = True
    try:
        with _api(monkeypatch, cursor) as api:
            response = api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
                "spokespersonIds": [eligible],
            })
            assert response.status_code == 409, response.text
        assert cursor.users[eligible]["client_id"] is None
        sql = " ".join(cursor.executed_sql)
        assert "with (updlock,holdlock)" in sql
        assert "role='spokesperson' and client_id is null" in sql
    finally:
        main.app.dependency_overrides.clear()


def test_non_master_roles_cannot_list_candidates_or_link(monkeypatch):
    cursor = MembershipCursor()
    target_id = _add_client(cursor)
    candidate = cursor.add_user()
    cursor.actor_client_id = target_id
    try:
        with _api(monkeypatch, cursor) as api:
            for role in ("spokesperson", "client_admin"):
                cursor.role = role
                assert api.get(f"/v1/api/master/spokespersons?clientId={target_id}").status_code == 403
                assert api.post(f"/v1/api/master/clients/{target_id}/spokespersons", json={
                    "spokespersonIds": [candidate],
                }).status_code == 403
        assert cursor.users[candidate]["client_id"] is None
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
