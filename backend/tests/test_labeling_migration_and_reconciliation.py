"""Local deterministic checks for labeling schema and reconciliation.

These tests use simulated cursors. They prove local control flow and generated
SQL properties, not successful execution against Azure SQL.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import labeling_migration
from scripts import reconcile_labeling_cases as reconciliation


AREAS = json.dumps(
    [
        {"areaId": "a1", "areaKey": "expression", "value": 80},
        {"areaId": "a2", "areaKey": "voice", "value": 82},
        {"areaId": "a3", "areaKey": "coherence", "value": 78},
        {"areaId": "a4", "areaKey": "empathy", "value": 81},
    ]
)
GOVERNANCE = json.dumps(
    [
        {
            "metricKey": "gov.borderline_delta",
            "thresholdsJson": json.dumps({"halfWidth": 5}),
        },
        {
            "metricKey": "gov.disparity_delta",
            "thresholdsJson": json.dumps({"auditAt": 25}),
        },
    ]
)


def make_row(**overrides):
    values = [
        "10000000-0000-4000-8000-000000000001",
        datetime(2026, 10, 29, tzinfo=timezone.utc),
        0,
        "20000000-0000-4000-8000-000000000001",
        1,
        "30000000-0000-4000-8000-000000000001",
        80,
        "40000000-0000-4000-8000-000000000001",
        "50000000-0000-4000-8000-000000000001",
        "50000000-0000-4000-8000-000000000001",
        "10000000-0000-4000-8000-000000000001",
        "40000000-0000-4000-8000-000000000001",
        1,
        json.dumps({"reportId": "30000000-0000-4000-8000-000000000001"}),
        AREAS,
        GOVERNANCE,
        None,
    ]
    positions = {
        "is_deleted": 2,
        "current_reports": 4,
        "report_id": 5,
        "job_id": 9,
        "job_session_id": 10,
        "job_rubric_id": 11,
        "fusion_count": 12,
        "fusion_json": 13,
        "areas_json": 14,
        "existing_case_id": 16,
    }
    for key, value in overrides.items():
        values[positions[key]] = value
    return tuple(values)


class MigrationCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, *params):
        self.statements.append(statement)
        return self


class VerifyCursor:
    def __init__(self, missing_index=None):
        self.missing_index = missing_index
        self.rows = []
        self.row = None

    def execute(self, statement, *params):
        if "FROM sys.columns" in statement:
            table = str(params[0]).split(".")[-1]
            self.rows = [(name,) for name in labeling_migration.REQUIRED_TABLE_COLUMNS[table]]
        elif "FROM sys.indexes" in statement:
            table = str(params[0]).split(".")[-1]
            filters = {
                "UQ_report_labeling_current": "([is_current]=(1))",
                "UQ_analysis_pipeline_result_fusion": "([pipeline]=N'fusion')",
                "UQ_labeling_review_current": "([is_current]=(1))",
            }
            self.rows = [
                (name, unique, False, name in filters, filters.get(name))
                for name, unique in labeling_migration.REQUIRED_INDEXES[table].items()
                if name != self.missing_index
            ]
        elif "FROM sys.foreign_keys" in statement:
            self.rows = [(name, False, False) for name in labeling_migration.REQUIRED_FOREIGN_KEYS]
        elif "FROM sys.check_constraints" in statement:
            self.rows = [(name, False, False) for name in labeling_migration.REQUIRED_CHECKS]
        elif "duplicated_cases" in statement:
            self.row = (0, 0, 0)
        else:
            raise AssertionError(statement)
        return self

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def fetchone(self):
        row, self.row = self.row, None
        return row


class ReconciliationCursor:
    def __init__(self, rows):
        self.source_rows = list(rows)
        self.cases = set()
        self.rows = []
        self.row = None
        self.insert_attempts = 0

    def execute(self, statement, *params):
        if "OBJECT_ID(N'dbo.labeling_case'" in statement:
            self.row = (1,)
        elif "AS completed_sessions" in statement:
            self.row = (
                len(self.source_rows),
                sum(bool(row[2]) for row in self.source_rows),
                sum(int(row[4] or 0) for row in self.source_rows),
                len(self.cases),
                max(0, len(self.source_rows) - len(self.cases)),
            )
        elif "SELECT TOP (?)" in statement:
            batch = int(params[0])
            materialized = []
            for source in self.source_rows[:batch]:
                row = list(source)
                row[16] = "case-id" if str(row[5]) in self.cases else None
                materialized.append(tuple(row))
            self.rows = materialized
        elif "INSERT INTO dbo.labeling_case" in statement:
            self.insert_attempts += 1
            report_id = str(params[-1])
            inserted = report_id not in self.cases
            self.cases.add(report_id)
            self.row = (1 if inserted else 0,)
        else:
            raise AssertionError(statement)
        return self

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def fetchone(self):
        row, self.row = self.row, None
        return row


def test_schema_migration_is_guarded_and_caller_owned_on_double_execution():
    cursor = MigrationCursor()
    labeling_migration.migrate(cursor)
    labeling_migration.migrate(cursor)

    assert len(cursor.statements) == 2 * len(labeling_migration.LABELING_SCHEMA_STEPS)
    assert all("IF " in statement for statement in cursor.statements)
    combined = "\n".join(cursor.statements).upper()
    assert "DROP TABLE" not in combined
    assert "INSERT INTO" not in combined
    assert "COMMIT" not in combined


def test_schema_migration_preserves_legacy_tables_before_creating_v2():
    steps = labeling_migration.LABELING_SCHEMA_STEPS
    combined = "\n".join(steps[:2]).lower()

    assert "labeling_case_legacy_v1" in combined
    assert "labeling_correction_legacy_v1" in combined
    assert "sp_rename" in combined
    assert steps.index(labeling_migration.LABELING_TABLE_STEPS[0]) == 2


def test_structural_verify_checks_tables_indexes_constraints_and_integrity():
    result = labeling_migration.verify(VerifyCursor())
    assert result == {"tables": 4, "indexes": 17, "foreignKeys": 14, "checks": 20}


def test_structural_verify_rejects_missing_index():
    try:
        labeling_migration.verify(
            VerifyCursor(missing_index="UQ_labeling_case_report"), ValueError
        )
    except ValueError as error:
        assert "UQ_labeling_case_report" in str(error)
    else:
        raise AssertionError("La verificación debía fallar.")


def test_anomalies_are_recorded_and_excluded_without_repair():
    deleted = make_row(is_deleted=1)
    duplicate_report = make_row(current_reports=2)
    missing_fusion = make_row(fusion_count=0)

    assert "session_deleted" in reconciliation._anomaly_codes(deleted)
    assert reconciliation._anomaly_codes(duplicate_report) == ["current_report_multiple"]
    assert reconciliation._anomaly_codes(missing_fusion) == ["fusion_missing"]


def test_backfill_is_idempotent_when_repeated():
    cursor = ReconciliationCursor([make_row()])
    first = reconciliation.reconcile(cursor, batch_size=10, limit=None, apply=True)
    second = reconciliation.reconcile(cursor, batch_size=10, limit=None, apply=True)

    assert first.created == 1
    assert first.eligible == 1
    assert second.created == 0
    assert second.already_materialized == 1
    assert cursor.insert_attempts == 1
    assert first.estimate["completeInventory"] is True


def test_dry_run_never_attempts_an_insert():
    cursor = ReconciliationCursor([make_row()])
    summary = reconciliation.reconcile(cursor, batch_size=10, limit=None, apply=False)

    assert summary.eligible == 1
    assert summary.created == 0
    assert summary.write_blocked is True
    assert cursor.insert_attempts == 0


class MainCursor:
    def execute(self, *_args, **_kwargs):
        return self


class MainConnection:
    def __init__(self):
        self.timeout = None
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return MainCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_failure_rolls_back_and_never_commits(monkeypatch):
    connection = MainConnection()
    monkeypatch.setattr(reconciliation, "_connect", lambda: connection)
    monkeypatch.setattr(
        reconciliation,
        "reconcile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert reconciliation.main(["--dry-run"]) == 1
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.closed is True


def test_prepare_verify_only_includes_labeling_verification():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "prepare_azure_database.py"
    ).read_text(encoding="utf-8")
    assert "verify_labeling(cursor, SeedError)" in source
