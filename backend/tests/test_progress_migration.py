"""Pruebas de contrato para la migración aditiva de Mi Progreso.

Estas pruebas validan el SQL generado sin sustituir la verificación real contra
Azure SQL que ejecuta ``prepare_azure_database.py --verify-only``.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts import prepare_azure_database as prepare


def _normalized(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_schema_migration_is_additive_idempotent_and_guards_duplicates():
    sql = _normalized(prepare.PROGRESS_SCHEMA_DDL)

    assert "col_length(n'dbo.schedule', n'session_id') is null" in sql
    assert "alter table dbo.schedule add session_id uniqueidentifier null" in sql
    assert "references dbo.session(id)" in sql
    assert "throw" in sql
    assert "group by user_id, rubric_area_id" in sql
    assert "having count_big(*) > 1" in sql
    assert "create unique index uq_user_area_progress_user_area" in sql
    assert "create unique index uq_schedule_session" in sql
    assert "where session_id is not null" in sql
    assert "create index ix_schedule_client_user_date" in sql
    assert "drop " not in sql
    assert "delete " not in sql


def test_backfill_uses_completed_current_reports_and_previous_area_score():
    sql = _normalized(prepare.USER_AREA_PROGRESS_BACKFILL_DML)

    assert "s.status = n'completed'" in sql
    assert "s.is_deleted = 0" in sql
    assert "r.is_current = 1" in sql
    assert "partition by r.session_id" in sql
    assert "order by r.generated_at desc, r.id desc" in sql
    assert "partition by a.report_id, ra.area_key" in sql
    assert "r.report_position = 1" in sql
    assert "a.score_position = 1" in sql
    assert "partition by s.user_id, a.area_key" in sql
    assert "lead(a.value) over" in sql
    assert "scored.value - scored.previous_value" in sql
    assert "count_big(distinct s.id)" in sql
    assert "merge dbo.user_area_progress" in sql
    assert "when matched and" in sql
    assert "when not matched then" in sql
    assert "delete " not in sql


class VerificationCursor:
    def __init__(self, missing_column=None, bad_index=None, missing_fk=False, bad_shape=None):
        self.missing_column = missing_column
        self.bad_index = bad_index
        self.missing_fk = missing_fk
        self.bad_shape = bad_shape
        self._row = None
        self._rows = []

    def execute(self, sql, *params):
        normalized = _normalized(sql)
        if "select col_length" in normalized:
            table = params[0].removeprefix("dbo.")
            column = params[1]
            self._row = (None if (table, column) == self.missing_column else 16,)
        elif "from sys.columns" in normalized and "is_nullable" in normalized:
            if "microlesson" in normalized:
                col = params[0] if params else ("video_blob_path" if "video_blob_path" in normalized else "scenario_id")
                self._row = (True,) if col == "video_blob_path" else (False,)
            else:
                self._row = (True, "uniqueidentifier") if "session_id" in normalized else (True,)
        elif "from sys.key_constraints" in normalized or "sys.key_constraints" in normalized:
            self._rows = [("id",)]
            self._row = (1,)
        elif "sys.index_columns" in normalized:
            index = params[-1]
            shapes = {
                "UQ_schedule_session": [("session_id", 1, False, 1)],
                "IX_schedule_client_user_date": [
                    ("client_id", 1, False, 1),
                    ("user_id", 2, False, 2),
                    ("scheduled_date", 3, False, 3),
                    ("status", 4, False, 4),
                    ("scenario_id", 0, True, 5),
                    ("session_id", 0, True, 6),
                    ("updated_at", 0, True, 7),
                ],
                "UQ_user_area_progress_user_area": [
                    ("user_id", 1, False, 1),
                    ("rubric_area_id", 2, False, 2),
                ],
            }
            self._rows = list(shapes[index])
            if index == self.bad_shape:
                self._rows[0] = ("wrong_column", 1, False, 1)
        elif "from sys.indexes" in normalized:
            index = params[-1]
            if index in {"idx_microlesson_client_status", "idx_microlesson_scenario"}:
                self._row = (False, 0)
            elif index == "UQ_scenario_id_client":
                self._row = (True, 0)
            else:
                filtered = index in {
                    "UQ_session_external_id", "UQ_session_idempotency", "UQ_schedule_session",
                }
                unique = index != "IX_schedule_client_user_date"
                filter_definition = "[session_id] IS NOT NULL" if index == "UQ_schedule_session" else None
                self._row = ((not unique), 0, filtered, filter_definition) if index == self.bad_index else (unique, 0, filtered, filter_definition)
        elif "from sys.foreign_keys" in normalized or "from sys.check_constraints" in normalized:
            if "microlesson" in normalized:
                self._row = (False, False)
            else:
                self._row = None if self.missing_fk else (False, False, "session_id", "id")
        else:
            raise AssertionError(f"Consulta de verificación inesperada: {sql}")
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)


def test_verify_requires_progress_columns_indexes_and_schedule_foreign_key(monkeypatch):
    monkeypatch.setattr(prepare, "verify_link_schema", lambda cursor: None)
    monkeypatch.setattr(prepare, "verify_assignment_schema", lambda cursor, error_type: None)

    prepare.verify(VerificationCursor())

    with pytest.raises(prepare.SeedError, match=r"schedule\.session_id"):
        prepare.verify(VerificationCursor(missing_column=("schedule", "session_id")))

    with pytest.raises(prepare.SeedError, match="UQ_schedule_session"):
        prepare.verify(VerificationCursor(bad_index="UQ_schedule_session"))

    with pytest.raises(prepare.SeedError, match="FK_schedule_session"):
        prepare.verify(VerificationCursor(missing_fk=True))

    with pytest.raises(prepare.SeedError, match="columnas del índice UQ_schedule_session"):
        prepare.verify(VerificationCursor(bad_shape="UQ_schedule_session"))
