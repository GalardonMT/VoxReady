"""La identidad de un analisis sale de la sesion y el job persistidos."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

try:
    import pytest
except ImportError:
    class _PytestMock:
        class raises:
            def __init__(self, expected_exc, match=None):
                self.expected_exc = expected_exc
                self.match = match
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                if exc_type is None:
                    raise AssertionError(f"Expected {self.expected_exc} but no exception was raised.")
                return issubclass(exc_type, self.expected_exc)
    pytest = _PytestMock()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from services.db_service import DatabaseService


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_value


def service_with_cursor(cursor):
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: Connection(cursor)
    return service


def session_row(client_id="client-a", job_rubric="rubric-a"):
    return (
        "session-internal", client_id, "owner-a", "scenario-a", "rubric-a",
        "Escenario A", "Contexto A", "empathetic", "audience-a", "topic-a",
        job_rubric, "session-public",
    )


def test_context_comes_from_exact_job_session_and_tenant():
    cursor = MagicMock()
    cursor.fetchone.return_value = session_row()
    cursor.fetchall.side_effect = [[("Mensaje A",)], [("Línea roja 1",)], [("area-a", "expression", 25)]]

    context = service_with_cursor(cursor).get_session_context("session-public", "job-a")

    sql, job_id, public_id, internal_id = cursor.execute.call_args_list[0].args
    assert "JOIN dbo.session s ON s.id = j.session_id" in sql
    assert "u.client_id = s.client_id" in sql
    assert "sc.client_id = s.client_id" in sql
    assert "t.client_id IS NULL OR t.client_id = s.client_id" in sql
    assert "s.is_deleted = 0" in sql
    assert "TOP 1" not in sql
    assert (job_id, public_id, internal_id) == ("job-a", "session-public", None)
    assert context["client_id"] == "client-a"
    assert context["user_id"] == "owner-a"
    assert context["scenario"]["scenario_id"] == "scenario-a"
    assert context["scenario"]["key_messages"] == ["Mensaje A"]
    assert context["scenario"]["red_lines"] == ["Línea roja 1"]
    assert context["rubric_version_id"] == "rubric-a"
    assert context["rubric_areas"]["expression"]["id"] == "area-a"


def test_unknown_job_or_session_is_rejected_without_fallback():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with pytest.raises(LookupError):
        service_with_cursor(cursor).get_session_context("foreign-session", "foreign-job")
    assert cursor.execute.call_count == 1


def test_job_cannot_use_another_rubric():
    cursor = MagicMock()
    cursor.fetchone.return_value = session_row(job_rubric="rubric-b")
    with pytest.raises(ValueError, match="rubrica"):
        service_with_cursor(cursor).get_session_context("session-public", "job-a")
    assert cursor.execute.call_count == 1


def test_missing_session_never_gets_a_generated_id():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    with pytest.raises(LookupError):
        service_with_cursor(cursor)._resolve_session_id(cursor, "session-that-does-not-exist")
    assert cursor.execute.call_count == 1
