"""Persistencia atómica de informe, progreso y agenda vinculada."""
from pathlib import Path
import sys
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from services.db_service import DatabaseService, USER_AREA_PROGRESS_REFRESH_DML
except ImportError:
    from worker.services.db_service import DatabaseService, USER_AREA_PROGRESS_REFRESH_DML


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()

    def cursor(self):
        return self.cursor_value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_finalize_updates_progress_and_only_linked_schedule_before_commit():
    cursor = MagicMock()
    cursor.fetchone.return_value = ("00112233-4455-6677-8899-aabbccddeeff",)
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    report_id = service.finalize_session_analysis(
        session_id="session-public-1",
        overall_score=81,
        visum_report={
            "desempeno_observado": {
                "fortalezas": ["Claridad"],
                "oportunidades_desarrollo": ["Empatía"],
            },
            "observacion_senal_cruzada": "Coherente",
        },
        area_scores={"expression": 70, "voice": 81},
        rubric_version_id="11112233-4455-6677-8899-aabbccddeeff",
        rubric_areas={
            "expression": {"id": "21112233-4455-6677-8899-aabbccddeeff"},
            "voice": {"id": "31112233-4455-6677-8899-aabbccddeeff"},
        },
    )

    assert report_id
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    session_complete = next(i for i, sql in enumerate(sql_calls) if "SET status = 'completed'" in sql)
    progress_refresh = next(i for i, sql in enumerate(sql_calls) if "MERGE dbo.user_area_progress" in sql)
    schedule_complete = next(i for i, sql in enumerate(sql_calls) if "UPDATE sch" in sql)
    assert session_complete < progress_refresh < schedule_complete
    assert "JOIN target_actor actor" in USER_AREA_PROGRESS_REFRESH_DML
    assert "s.status='completed'" in USER_AREA_PROGRESS_REFRESH_DML
    assert "r.is_current=1" in USER_AREA_PROGRESS_REFRESH_DML
    assert "previous_value" in USER_AREA_PROGRESS_REFRESH_DML
    schedule_sql = sql_calls[schedule_complete]
    assert "sch.session_id = ?" in schedule_sql
    assert "sch.user_id = s.user_id AND sch.client_id = s.client_id" in schedule_sql
    assert "sch.status = 'scheduled'" in schedule_sql
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()


def test_finalize_rolls_back_report_progress_and_schedule_together_on_failure():
    cursor = MagicMock()
    cursor.fetchone.return_value = ("00112233-4455-6677-8899-aabbccddeeff",)

    def execute(sql, *params):
        if "MERGE dbo.user_area_progress" in sql:
            raise RuntimeError("progress failed")
        return cursor

    cursor.execute.side_effect = execute
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    try:
        service.finalize_session_analysis(
            session_id="session-public-1",
            overall_score=81,
            visum_report={},
            area_scores={},
            rubric_version_id="11112233-4455-6677-8899-aabbccddeeff",
            rubric_areas={},
        )
    except RuntimeError as error:
        assert str(error) == "progress failed"
    else:
        raise AssertionError("La falla del progreso debía revertir la transacción.")

    connection.rollback.assert_called_once_with()
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("UPDATE sch" in sql for sql in sql_calls)
    assert not any("SET status = 'failed'" in sql for sql in sql_calls)
    connection.close.assert_called_once_with()


def test_finalize_redelivery_reuses_matching_report_without_reapplying_side_effects():
    cursor = MagicMock()
    session_id = "00112233-4455-6677-8899-aabbccddeeff"
    report_id = "41112233-4455-6677-8899-aabbccddeeff"
    rubric_id = "11112233-4455-6677-8899-aabbccddeeff"
    cursor.fetchone.return_value = (session_id,)
    cursor.fetchall.return_value = [(report_id, session_id, rubric_id)]
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    result = service.finalize_session_analysis(
        session_id="session-public-1",
        overall_score=81,
        visum_report={},
        area_scores={"expression": 70, "voice": 81},
        rubric_version_id=rubric_id,
        rubric_areas={
            "expression": {"id": "21112233-4455-6677-8899-aabbccddeeff"},
            "voice": {"id": "31112233-4455-6677-8899-aabbccddeeff"},
        },
        job_id="51112233-4455-6677-8899-aabbccddeeff",
    )

    assert result == report_id
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    lock_sql = next(sql for sql in sql_calls if "sp_getapplock" in sql)
    assert "IF @@TRANCOUNT=0 BEGIN TRANSACTION" in lock_sql
    assert any("WITH (UPDLOCK,HOLDLOCK)" in sql for sql in sql_calls)
    assert any("finished_at=COALESCE" in sql for sql in sql_calls)
    assert not any("INSERT INTO report" in sql for sql in sql_calls)
    assert not any("MERGE dbo.user_area_progress" in sql for sql in sql_calls)
    assert not any("UPDATE sch" in sql for sql in sql_calls)
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()


def test_has_persisted_report_matches_job_and_resolved_session():
    cursor = MagicMock()
    session_id = "00112233-4455-6677-8899-aabbccddeeff"
    cursor.fetchone.side_effect = [(session_id,), (1,)]
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    exists = service.has_persisted_report(
        "51112233-4455-6677-8899-aabbccddeeff",
        "session-public-1",
    )

    assert exists is True
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    assert "sp_getapplock" in sql_calls[0]
    assert "voxready:analysis-job:" in cursor.execute.call_args_list[0].args[1]
    report_query = next(
        call for call in cursor.execute.call_args_list if "FROM dbo.report" in call.args[0]
    )
    assert "analysis_job_id=? AND session_id=?" in report_query.args[0]
    assert report_query.args[2] == session_id
    connection.commit.assert_called_once_with()


def test_failed_status_never_degrades_a_completed_session():
    cursor = MagicMock()
    session_id = "00112233-4455-6677-8899-aabbccddeeff"
    cursor.fetchone.return_value = (session_id,)
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    service.update_session_status("session-public-1", "failed")

    update_call = next(
        call for call in cursor.execute.call_args_list if "UPDATE session" in call.args[0]
    )
    assert "status <> 'completed'" in update_call.args[0]
    connection.commit.assert_called_once_with()


def test_create_labeling_case_idempotent_existing():
    cursor = MagicMock()
    # When ensure_labeling_case_for_report checks for existing case:
    cursor.fetchone.return_value = ("existing-case-id",)
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    case_id = service.create_labeling_case_if_needed("report-id")
    assert case_id == "existing-case-id"
    connection.commit.assert_called_once_with()


def test_create_labeling_case_does_not_fallback_after_canonical_failure():
    cursor = MagicMock()
    def execute_side_effect(sql, *params):
        if "HOLDLOCK" in sql:
            raise RuntimeError("simulate canonical failure")
        return cursor

    cursor.execute.side_effect = execute_side_effect
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    try:
        service.create_labeling_case_if_needed("report-id")
    except RuntimeError as error:
        assert str(error) == "simulate canonical failure"
    else:
        raise AssertionError("La falla canónica debía propagarse sin fallback.")

    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    assert not any("INSERT INTO dbo.labeling_case" in sql for sql in sql_calls)
    connection.commit.assert_not_called()


import unittest

class DbServiceProgressTest(unittest.TestCase):
    def test_finalize_updates(self):
        test_finalize_updates_progress_and_only_linked_schedule_before_commit()

    def test_finalize_rollback(self):
        test_finalize_rolls_back_report_progress_and_schedule_together_on_failure()

    def test_finalize_redelivery(self):
        test_finalize_redelivery_reuses_matching_report_without_reapplying_side_effects()

    def test_has_report(self):
        test_has_persisted_report_matches_job_and_resolved_session()

    def test_completed_session_is_terminal(self):
        test_failed_status_never_degrades_a_completed_session()

    def test_create_labeling_case_existing(self):
        test_create_labeling_case_idempotent_existing()

    def test_create_labeling_case_canonical_failure(self):
        test_create_labeling_case_does_not_fallback_after_canonical_failure()



