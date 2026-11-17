"""Contrato de lectura de escenarios para el administrador del cliente.

Estas pruebas describen la API de dominio antes de implementar el módulo
``client_scenarios``. No requieren Azure SQL ni modifican datos.
"""

import ast
import importlib
from pathlib import Path
import sys
import uuid

from fastapi import HTTPException, Response
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

CLIENT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_CLIENT_ID = "22222222-2222-4222-8222-222222222222"
SCENARIO_ID = "33333333-3333-4333-8333-333333333333"
QUESTION_ONE_ID = "44444444-4444-4444-8444-444444444444"
QUESTION_TWO_ID = "55555555-5555-4555-8555-555555555555"


def subject():
    """Carga diferida para que el estado RED sea un fallo de prueba legible."""
    return importlib.import_module("client_scenarios")


class ScriptedCursor:
    """Cursor pyodbc mínimo con resultados deterministas por ejecución."""

    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self._rows = []
        self.description = []
        self.executions = []

    def execute(self, sql, *params):
        self.executions.append((" ".join(sql.split()), params))
        if not self._result_sets:
            raise AssertionError("La consulta ejecutó más operaciones de las esperadas.")
        columns, rows = self._result_sets.pop(0)
        self.description = [(column,) for column in columns]
        self._rows = list(rows)
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def result_set(columns, *rows):
    return columns, rows


@pytest.mark.parametrize("role", ["spokesperson", "master_config"])
def test_only_database_resolved_client_admin_is_authorized(role):
    with pytest.raises(HTTPException) as error:
        subject().require_client_admin(
            {"id": "actor", "client_id": CLIENT_ID, "role": role}
        )

    assert error.value.status_code == 403


def test_client_admin_must_have_an_assigned_client():
    with pytest.raises(HTTPException) as error:
        subject().require_client_admin(
            {"id": "actor", "client_id": None, "role": "client_admin"}
        )

    assert error.value.status_code == 403


def test_database_resolved_client_admin_receives_its_tenant_scope():
    client_id = subject().require_client_admin(
        {"id": "actor", "client_id": CLIENT_ID, "role": "client_admin"}
    )

    assert client_id == CLIENT_ID


def test_authenticated_scenario_responses_disable_storage():
    response = Response()

    subject().mark_private_no_store(response)

    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 20), (1, 0), (1, 101)],
    ids=["page-zero", "size-zero", "size-over-limit"],
)
def test_list_rejects_invalid_pagination_before_query(page, page_size):
    cursor = ScriptedCursor([])

    with pytest.raises(HTTPException) as error:
        subject().list_available(cursor, CLIENT_ID, page=page, page_size=page_size)

    assert error.value.status_code == 422
    assert cursor.executions == []


def test_list_returns_only_the_public_summary_contract():
    cursor = ScriptedCursor(
        [
            result_set(("total",), (2,)),
            result_set(
                (
                    "id",
                    "title",
                    "category",
                    "difficulty",
                    "estimatedMinutes",
                    "questionCount",
                    "audience",
                    "optics",
                ),
                (
                    uuid.UUID(SCENARIO_ID),
                    "Interrupción de servicio",
                    "operational",
                    "intermediate",
                    12,
                    2,
                    "technical",
                    "formal",
                ),
            ),
        ]
    )

    response = subject().list_available(cursor, CLIENT_ID, page=1, page_size=20)

    assert response == {
        "items": [
            {
                "id": SCENARIO_ID,
                "title": "Interrupción de servicio",
                "category": "operational",
                "difficulty": "intermediate",
                "estimatedMinutes": 12,
                "questionCount": 2,
                "audience": "technical",
                "optics": "formal",
            }
        ],
        "page": 1,
        "pageSize": 20,
        "total": 2,
    }
    assert set(response["items"][0]) == {
        "id",
        "title",
        "category",
        "difficulty",
        "estimatedMinutes",
        "questionCount",
        "audience",
        "optics",
    }


def test_list_queries_are_read_only_active_and_tenant_scoped():
    cursor = ScriptedCursor(
        [
            result_set(("total",), (0,)),
            result_set(
                (
                    "id",
                    "title",
                    "category",
                    "difficulty",
                    "estimatedMinutes",
                    "questionCount",
                    "audience",
                    "optics",
                )
            ),
        ]
    )

    subject().list_available(cursor, CLIENT_ID, page=2, page_size=10)

    assert len(cursor.executions) == 2
    for sql, params in cursor.executions:
        assert sql.upper().startswith("SELECT")
        assert "s.client_id = ?" in sql
        assert "s.status = 'active'" in sql
        assert "t.status = 'active'" in sql
        assert "c.status = 'active'" in sql
        assert "s.is_deleted = 0" in sql
        assert "t.is_deleted = 0" in sql
        assert "c.is_deleted = 0" in sql
        assert CLIENT_ID in params
        assert OTHER_CLIENT_ID not in params


def test_detail_returns_all_functional_information_in_defined_order():
    cursor = ScriptedCursor(
        [
            result_set(
                (
                    "id",
                    "title",
                    "category",
                    "difficulty",
                    "estimatedMinutes",
                    "questionCount",
                    "audience",
                    "optics",
                    "context",
                ),
                (
                    uuid.UUID(SCENARIO_ID),
                    "Interrupción de servicio",
                    "operational",
                    "intermediate",
                    12,
                    2,
                    "technical",
                    "formal",
                    "Una interrupción afecta los canales de atención.",
                ),
            ),
            result_set(("text",), ("Reconocemos el impacto.",), ("Informaremos avances.",)),
            result_set(("text",), ("No especular sobre la causa.",)),
            result_set(
                ("id", "sequenceNo", "text"),
                (uuid.UUID(QUESTION_ONE_ID), 1, "¿Qué ocurrió?"),
                (uuid.UUID(QUESTION_TWO_ID), 2, "¿Cuándo se resolverá?"),
            ),
        ]
    )

    response = subject().get_available(cursor, CLIENT_ID, SCENARIO_ID)

    assert response == {
        "id": SCENARIO_ID,
        "title": "Interrupción de servicio",
        "category": "operational",
        "difficulty": "intermediate",
        "estimatedMinutes": 12,
        "questionCount": 2,
        "audience": "technical",
        "optics": "formal",
        "context": "Una interrupción afecta los canales de atención.",
        "keyMessages": ["Reconocemos el impacto.", "Informaremos avances."],
        "redLines": ["No especular sobre la causa."],
        "questions": [
            {"sequenceNo": 1, "text": "¿Qué ocurrió?"},
            {"sequenceNo": 2, "text": "¿Cuándo se resolverá?"},
        ],
    }
    assert "clientId" not in response
    assert "topicId" not in response
    assert "status" not in response
    assert "createdAt" not in response
    assert all("id" not in question for question in response["questions"])

    detail_sql, detail_params = cursor.executions[0]
    assert detail_sql.upper().startswith("SELECT")
    assert "s.id = ?" in detail_sql
    assert "s.client_id = ?" in detail_sql
    assert "s.status = 'active'" in detail_sql
    assert "t.status = 'active'" in detail_sql
    assert detail_params == (SCENARIO_ID, CLIENT_ID)
    for sql, params in cursor.executions:
        assert sql.upper().startswith("SELECT")
        assert "s.id = ?" in sql
        assert "s.client_id = ?" in sql
        assert "s.status = 'active'" in sql
        assert "t.status = 'active'" in sql
        assert "c.status = 'active'" in sql
        assert "s.is_deleted = 0" in sql
        assert "t.is_deleted = 0" in sql
        assert "c.is_deleted = 0" in sql
        assert params == (SCENARIO_ID, CLIENT_ID)


def test_detail_is_opaque_for_missing_archived_or_cross_tenant_scenario():
    cursor = ScriptedCursor(
        [
            result_set(
                (
                    "id",
                    "title",
                    "category",
                    "difficulty",
                    "estimatedMinutes",
                    "questionCount",
                    "audience",
                    "optics",
                    "context",
                )
            )
        ]
    )

    with pytest.raises(HTTPException) as error:
        subject().get_available(cursor, CLIENT_ID, SCENARIO_ID)

    assert error.value.status_code == 404
    assert cursor.executions[0][1] == (SCENARIO_ID, CLIENT_ID)


def test_client_scenario_routes_are_get_only_and_have_versioned_aliases():
    tree = ast.parse((BACKEND_ROOT / "main.py").read_text(encoding="utf-8"))
    routes = []
    client_route_handlers = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        function_routes = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner = decorator.func.value
            if not isinstance(owner, ast.Name) or owner.id != "app" or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str):
                routes.append((decorator.func.attr, path.value))
                function_routes.append((decorator.func.attr, path.value))
        if any(
            path.startswith(("/api/client/scenarios", "/v1/api/client/scenarios"))
            for _, path in function_routes
        ):
            client_route_handlers.append(node)

    expected_gets = {
        "/api/client/scenarios",
        "/v1/api/client/scenarios",
        "/api/client/scenarios/{scenario_id}",
        "/v1/api/client/scenarios/{scenario_id}",
    }
    actual_gets = {path for method, path in routes if method == "get"}
    assert expected_gets <= actual_gets
    assert not {
        (method, path)
        for method, path in routes
        if method in {"post", "put", "patch", "delete"}
        and path.startswith(("/api/client/scenarios", "/v1/api/client/scenarios"))
    }
    assert len(client_route_handlers) == 2
    for handler in client_route_handlers:
        called_attributes = {
            call.func.attr
            for call in ast.walk(handler)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        }

        assert any(
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and isinstance(default.args[0], ast.Name)
            and default.args[0].id == "verify_token"
            for default in (*handler.args.defaults, *handler.args.kw_defaults)
        )
        assert "resolve_user" in called_attributes
        assert "require_client_admin" in called_attributes
        assert "mark_private_no_store" in called_attributes
