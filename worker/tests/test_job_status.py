"""Pruebas del modo estricto y best-effort del estado del job."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.job_status import update_analysis_job_status


class FakeCursor:
    def __init__(self, execute_error=None, rowcount=1):
        self.execute_error = execute_error
        self.rowcount = rowcount
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.execute_error:
            raise self.execute_error


class FakeConnection:
    def __init__(self, *, execute_error=None, commit_error=None, rowcount=1):
        self.cursor_value = FakeCursor(execute_error, rowcount=rowcount)
        self.commit_error = commit_error
        self.commits = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeDatabaseService:
    def __init__(self, connection):
        self.connection = connection

    def get_connection(self):
        return self.connection


def test_completed_status_is_strict_and_propagates_commit_failure():
    commit_error = RuntimeError("commit failed")
    service = FakeDatabaseService(FakeConnection(commit_error=commit_error))

    with pytest.raises(RuntimeError) as captured:
        update_analysis_job_status(service, "job-1", "completed")

    assert captured.value is commit_error


def test_failed_cleanup_is_best_effort_and_does_not_raise():
    execute_error = RuntimeError("database unavailable")
    connection = FakeConnection(execute_error=execute_error)
    service = FakeDatabaseService(connection)

    updated = update_analysis_job_status(
        service,
        "job-1",
        "failed",
        failure_reason="original pipeline error",
        best_effort=True,
    )

    assert updated is False
    assert connection.commits == 0


def test_successful_completed_status_commits_and_returns_true():
    connection = FakeConnection()
    service = FakeDatabaseService(connection)

    updated = update_analysis_job_status(service, "job-1", "completed")

    assert updated is True
    assert connection.commits == 1
    sql, params = connection.cursor_value.calls[0]
    assert "status = 'completed'" in sql
    assert "completed_at = COALESCE(completed_at, SYSUTCDATETIME())" in sql
    assert "failure_reason = NULL" in sql
    assert params == "job-1"


def test_failed_status_clears_completed_at():
    connection = FakeConnection()
    service = FakeDatabaseService(connection)

    updated = update_analysis_job_status(
        service,
        "job-1",
        "failed",
        failure_reason="pipeline error",
    )

    assert updated is True
    sql, _params = connection.cursor_value.calls[0]
    assert "completed_at = NULL" in sql
    assert "status <> 'completed'" in sql


def test_missing_job_fails_in_strict_mode_without_commit():
    connection = FakeConnection(rowcount=0)
    service = FakeDatabaseService(connection)

    with pytest.raises(RuntimeError, match="no existe"):
        update_analysis_job_status(service, "missing-job", "completed")

    assert connection.commits == 0


def test_missing_job_returns_false_in_best_effort_mode():
    connection = FakeConnection(rowcount=0)
    service = FakeDatabaseService(connection)

    updated = update_analysis_job_status(
        service,
        "missing-job",
        "failed",
        best_effort=True,
    )

    assert updated is False
    assert connection.commits == 0


def test_late_failed_delivery_cannot_overwrite_completed_job():
    # SQL Server reporta 0 filas porque el WHERE protege el estado terminal.
    connection = FakeConnection(rowcount=0)
    service = FakeDatabaseService(connection)

    updated = update_analysis_job_status(
        service,
        "completed-job",
        "failed",
        failure_reason="late delivery error",
        best_effort=True,
    )

    assert updated is False
    assert connection.commits == 0
    sql, _params = connection.cursor_value.calls[0]
    assert "WHERE id = ? AND status <> 'completed'" in sql


def test_unknown_status_always_fails_even_in_best_effort_mode():
    service = FakeDatabaseService(FakeConnection())

    with pytest.raises(ValueError, match="completed o failed"):
        update_analysis_job_status(
            service,
            "job-1",
            "running",
            best_effort=True,
        )
