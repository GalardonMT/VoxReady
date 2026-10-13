"""Compilación real y reversible de las sentencias de cierre en Azure SQL."""
import os
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.db_service import (
    DatabaseService,
    LINKED_SCHEDULE_COMPLETE_DML,
    USER_AREA_PROGRESS_REFRESH_DML,
)


pytestmark = pytest.mark.skipif(
    os.getenv("VOXREADY_TEST_AZURE_SQL") != "1",
    reason="Azure SQL integration is opt-in",
)


def test_progress_and_linked_schedule_sql_compile_without_persisting():
    connection = DatabaseService(max_retries=1)._get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SET XACT_ABORT ON; IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
        missing_session = str(uuid.uuid4())
        cursor.execute(USER_AREA_PROGRESS_REFRESH_DML, missing_session)
        cursor.execute(LINKED_SCHEDULE_COMPLETE_DML, missing_session)
    finally:
        connection.rollback()
        connection.close()


def test_finalize_refreshes_progress_and_completes_linked_schedule_atomically():
    service = DatabaseService(max_retries=1)
    connection = service._get_connection()
    cursor = connection.cursor()
    cursor.execute("SET XACT_ABORT ON; IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
    try:
        cursor.execute("""SELECT TOP 1 u.id,u.client_id
                          FROM dbo.app_user u JOIN dbo.client c ON c.id=u.client_id
                          WHERE u.role='spokesperson'
                            AND (u.is_deleted IS NULL OR u.is_deleted=0)
                            AND c.status='active' AND c.is_deleted=0
                          ORDER BY u.id""")
        actor = cursor.fetchone()
        if actor is None:
            pytest.skip("No existe un vocero asignado para la prueba transaccional.")
        cursor.execute("""SELECT TOP 1 s.id
                          FROM dbo.scenario s JOIN dbo.topic t ON t.id=s.topic_id
                          WHERE s.client_id=? AND s.status='active' AND s.is_deleted=0
                            AND t.status='active' AND t.is_deleted=0
                          ORDER BY s.id""", actor[1])
        scenario = cursor.fetchone()
        cursor.execute("""SELECT TOP 1 rv.id
                          FROM dbo.rubric_version rv
                          WHERE rv.status='published'
                            AND EXISTS (SELECT 1 FROM dbo.rubric_area ra WHERE ra.rubric_version_id=rv.id)
                          ORDER BY rv.published_at DESC,rv.created_at DESC""")
        rubric = cursor.fetchone()
        if scenario is None or rubric is None:
            pytest.skip("Falta un escenario o una rúbrica publicada para la prueba transaccional.")
        cursor.execute("SELECT id,area_key FROM dbo.rubric_area WHERE rubric_version_id=?", rubric[0])
        rubric_rows = list(cursor.fetchall())
        scores = {str(row[1]): 70 + index for index, row in enumerate(rubric_rows)}
        rubric_areas = {str(row[1]): {"id": str(row[0])} for row in rubric_rows}

        session_id = str(uuid.uuid4())
        schedule_id = str(uuid.uuid4())
        external_id = "worker-test-" + session_id
        cursor.execute("""INSERT INTO dbo.session(
                              id,user_id,client_id,scenario_id,language,status,
                              rubric_version_id,external_session_id)
                          VALUES(?,?,?,?,?,'analyzing',?,?)""",
                       session_id, actor[0], actor[1], scenario[0], "es", rubric[0], external_id)
        cursor.execute("""INSERT INTO dbo.schedule(
                              id,client_id,user_id,scheduled_date,scenario_id,status,session_id,
                              created_at,updated_at)
                          VALUES(?,?,?,CAST(SYSUTCDATETIME() AS date),?,'scheduled',?,
                                 SYSUTCDATETIME(),SYSUTCDATETIME())""",
                       schedule_id, actor[1], actor[0], scenario[0], session_id)

        class TransactionConnection:
            def cursor(self):
                return cursor

            def commit(self):
                return None

            def rollback(self):
                return None

            def close(self):
                return None

        service._get_connection = lambda: TransactionConnection()
        report_id = service.finalize_session_analysis(
            session_id=session_id,
            overall_score=80,
            visum_report={},
            area_scores=scores,
            rubric_version_id=str(rubric[0]),
            rubric_areas=rubric_areas,
        )

        cursor.execute("SELECT status FROM dbo.schedule WHERE id=?", schedule_id)
        assert cursor.fetchone()[0] == "completed"
        cursor.execute("SELECT status FROM dbo.session WHERE id=?", session_id)
        assert cursor.fetchone()[0] == "completed"
        cursor.execute("SELECT COUNT(*) FROM dbo.report WHERE id=?", report_id)
        assert cursor.fetchone()[0] == 1
        cursor.execute("""SELECT COUNT(*)
                          FROM dbo.user_area_progress p
                          JOIN dbo.rubric_area ra ON ra.id=p.rubric_area_id
                          WHERE p.user_id=? AND ra.rubric_version_id=?""", actor[0], rubric[0])
        assert cursor.fetchone()[0] == len(rubric_rows)
    finally:
        connection.rollback()
        connection.close()
