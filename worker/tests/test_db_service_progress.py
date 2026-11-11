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
    assert any("SET status = 'failed'" in sql for sql in sql_calls)
    connection.close.assert_called_once_with()


def test_create_labeling_case_idempotent_existing():
    cursor = MagicMock()
    # When ensure_labeling_case_for_report checks for existing case:
    cursor.fetchone.return_value = ("existing-case-id",)
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    case_id = service.create_labeling_case_if_needed(
        session_id="00112233-4455-6677-8899-aabbccddeeff",
        rubric_version_id="rubric-id",
        reason="low_confidence",
        report_id="report-id",
    )
    assert case_id == "existing-case-id"


def test_create_labeling_case_fallback_schema():
    cursor = MagicMock()
    # 1. ensure_labeling_case_for_report raises exception (e.g. material missing)
    # 2. Fallback runs:
    #    _resolve_session_id -> ("00112233-4455-6677-8899-aabbccddeeff",)
    #    report query -> ("report-id", "job-id", "rubric-id", "client-id", "2026-11-10T12:00:00")
    #    check existing in fallback -> None
    def execute_side_effect(sql, *params):
        if "HOLDLOCK" in sql:
            raise RuntimeError("simulate canonical failure")
        return cursor

    cursor.execute.side_effect = execute_side_effect
    cursor.fetchone.side_effect = [
        ("00112233-4455-6677-8899-aabbccddeeff",),
        ("report-id", "job-id", "rubric-id", "client-id", "2026-11-10T12:00:00"),
        None,
    ]
    connection = Connection(cursor)
    service = DatabaseService(connection_string="unused")
    service._get_connection = lambda: connection

    case_id = service.create_labeling_case_if_needed(
        session_id="00112233-4455-6677-8899-aabbccddeeff",
        rubric_version_id="rubric-id",
        reason="low_confidence",
        report_id="report-id",
        job_id="job-id",
        evidence={
            "sealedPath": "labeling-evidence/session/job/hash.webm",
            "sha256": "a" * 64,
            "etag": '"etag"',
            "contentType": "video/webm",
            "durationSeconds": 60.0
        }
    )

    assert case_id is not None
    sql_calls = [call.args[0] for call in cursor.execute.call_args_list]
    insert_call = next(sql for sql in sql_calls if "INSERT INTO dbo.labeling_case" in sql)
    assert "queue_reason" in insert_call
    assert " reason," not in insert_call and ", reason," not in insert_call
    assert "ai_snapshot_json" in insert_call
    assert "source_status" in insert_call


import unittest

class DbServiceProgressTest(unittest.TestCase):
    def test_finalize_updates(self):
        test_finalize_updates_progress_and_only_linked_schedule_before_commit()

    def test_finalize_rollback(self):
        test_finalize_rolls_back_report_progress_and_schedule_together_on_failure()

    def test_create_labeling_case_existing(self):
        test_create_labeling_case_idempotent_existing()

    def test_create_labeling_case_fallback(self):
        test_create_labeling_case_fallback_schema()



