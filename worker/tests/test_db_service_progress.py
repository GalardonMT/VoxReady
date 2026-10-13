"""Persistencia atómica de informe, progreso y agenda vinculada."""
from pathlib import Path
import sys
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.db_service import DatabaseService, USER_AREA_PROGRESS_REFRESH_DML


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()

    def cursor(self):
        return self.cursor_value


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
