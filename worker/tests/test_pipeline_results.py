"""Pruebas focalizadas de persistencia idempotente de pipelines."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.pipeline_results import is_transient_sql_error, persist_pipeline_results


class FakeCursor:
    def __init__(self, state, execute_error=None):
        self.state = state
        self.execute_error = execute_error
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.execute_error:
            raise self.execute_error
        if "sp_getapplock" in sql:
            return self
        job_id, pipeline, _, _, summary_json = params
        values = self.state.setdefault((job_id, pipeline), [])
        if len(values) > 1:
            raise RuntimeError("duplicate pipeline results")
        if not values:
            values.append(summary_json)
        return self


class FakeConnection:
    def __init__(self, state, *, commit_error=None, execute_error=None):
        self.cursor_value = FakeCursor(state, execute_error=execute_error)
        self.commit_error = commit_error
        self.commit_calls = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commit_calls += 1
        if self.commit_error:
            raise self.commit_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeDatabaseService:
    def __init__(self, connections):
        self.connections = list(connections)
        self.opened = 0

    def get_connection(self):
        connection = self.connections[self.opened]
        self.opened += 1
        return connection


def test_insert_once_is_keyed_by_job_and_pipeline_and_uses_serializable_locking():
    state = {}
    connection = FakeConnection(state)
    service = FakeDatabaseService([connection])

    persist_pipeline_results(service, "job-1", {"fusion": {"score": 80}})

    lock_sql, lock_resource = connection.cursor_value.calls[0]
    sql, params = connection.cursor_value.calls[1]
    assert "IF @@TRANCOUNT = 0" in lock_sql
    assert "BEGIN TRANSACTION" in lock_sql
    assert "sp_getapplock" in lock_sql
    assert lock_resource == "analysis_pipeline_result:job-1"
    assert "WITH (UPDLOCK, HOLDLOCK)" in sql
    assert "WHERE analysis_job_id = ? AND pipeline = ?" in sql
    assert "IF @existing_count > 1" in sql
    assert "IF @existing_count = 0" in sql
    assert "UPDATE dbo.analysis_pipeline_result" not in sql
    assert params[:2] == ("job-1", "fusion")
    assert list(state) == [("job-1", "fusion")]


def test_job_lock_is_acquired_before_any_pipeline_write():
    state = {}
    connection = FakeConnection(state)
    service = FakeDatabaseService([connection])

    persist_pipeline_results(
        service,
        "job-1",
        {"vision": {}, "fusion": {}},
    )

    calls = connection.cursor_value.calls
    assert "sp_getapplock" in calls[0][0]
    assert "analysis_pipeline_result" in calls[1][0]
    assert "analysis_pipeline_result" in calls[2][0]


def test_retry_after_uncertain_commit_does_not_create_duplicate_key():
    state = {}
    transient = RuntimeError("08S01", "connection lost while committing")
    first = FakeConnection(state, commit_error=transient)
    second = FakeConnection(state)
    service = FakeDatabaseService([first, second])
    sleeps = []

    persist_pipeline_results(
        service,
        "job-1",
        {"fusion": {"score": 80}},
        sleep_fn=sleeps.append,
    )

    assert service.opened == 2
    assert sleeps == [0.25]
    assert list(state) == [("job-1", "fusion")]


def test_redelivery_with_different_json_preserves_first_write():
    state = {}
    first = FakeConnection(state)
    second = FakeConnection(state)
    service = FakeDatabaseService([first, second])

    persist_pipeline_results(service, "job-1", {"fusion": {"score": 80}})
    first_value = state[("job-1", "fusion")][0]
    persist_pipeline_results(service, "job-1", {"fusion": {"score": 10}})

    assert state[("job-1", "fusion")] == [first_value]
    assert '"score": 80' in first_value


def test_existing_duplicate_rows_fail_instead_of_choosing_one():
    state = {("job-1", "fusion"): ["first", "second"]}
    service = FakeDatabaseService([FakeConnection(state)])

    with pytest.raises(RuntimeError, match="duplicate pipeline results"):
        persist_pipeline_results(service, "job-1", {"fusion": {"score": 80}})


def test_non_transient_sql_error_is_not_retried():
    state = {}
    invalid_data = RuntimeError("23000", "integrity constraint violation")
    connection = FakeConnection(state, execute_error=invalid_data)
    service = FakeDatabaseService([connection])
    sleeps = []

    try:
        persist_pipeline_results(
            service,
            "job-1",
            {"fusion": {}},
            sleep_fn=sleeps.append,
        )
    except RuntimeError as error:
        assert error is invalid_data
    else:
        raise AssertionError("El error no transitorio debia propagarse.")

    assert service.opened == 1
    assert sleeps == []


def test_transient_sql_retries_are_bounded():
    state = {}
    transient = RuntimeError("08S01", "connection unavailable")
    connections = [
        FakeConnection(state, execute_error=transient),
        FakeConnection(state, execute_error=transient),
        FakeConnection(state, execute_error=transient),
    ]
    service = FakeDatabaseService(connections)
    sleeps = []

    try:
        persist_pipeline_results(
            service,
            "job-1",
            {"fusion": {}},
            sleep_fn=sleeps.append,
        )
    except RuntimeError as error:
        assert error is transient
    else:
        raise AssertionError("El ultimo error transitorio debia propagarse.")

    assert service.opened == 3
    assert sleeps == [0.25, 0.5]


def test_only_expected_sql_errors_are_classified_as_transient():
    assert is_transient_sql_error(RuntimeError("40001", "deadlock victim"))
    assert is_transient_sql_error(RuntimeError("HYT00", "timeout"))
    assert is_transient_sql_error(RuntimeError("42000", "Azure code 40501"))
    assert not is_transient_sql_error(RuntimeError("23000", "constraint"))
    assert not is_transient_sql_error(RuntimeError("42000", "syntax error"))
