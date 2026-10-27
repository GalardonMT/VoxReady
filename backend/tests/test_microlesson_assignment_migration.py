"""Contract tests for the additive, tenant-safe assignment migration."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microlesson_assignment_migration import ASSIGNMENT_SCHEMA_STEPS, verify_assignment_schema


class SchemaError(Exception):
    pass


def normalized(sql):
    return re.sub(r"\s+", " ", sql).lower()


def test_migration_is_additive_idempotent_and_enforces_tenant_and_active_uniqueness():
    sql = normalized("\n".join(ASSIGNMENT_SCHEMA_STEPS))
    assert "object_id(n'dbo.microlesson_assignment', n'u') is null" in sql
    assert "create table dbo.microlesson_assignment" in sql
    assert "status in ('assigned','in_progress','completed','revoked')" in sql
    assert "create unique index uq_microlesson_assignment_active" in sql
    assert "where status in ('assigned','in_progress')" in sql
    assert "foreign key (microlesson_id,client_id) references dbo.microlesson(id,client_id)" in sql
    assert "foreign key (user_id,client_id) references dbo.app_user(id,client_id)" in sql
    assert "foreign key (assigned_by) references dbo.app_user(id)" in sql
    assert "drop " not in sql
    assert "delete " not in sql
    assert "insert " not in sql
    assert "update " not in sql


class MetadataCursor:
    def __init__(self, *, missing_column=None, bad_index=None, bad_fk=None, bad_check=None, bad_shape=None):
        self.missing_column = missing_column
        self.bad_index = bad_index
        self.bad_fk = bad_fk
        self.bad_check = bad_check
        self.bad_shape = bad_shape
        self.row = None
        self.rows = []

    def execute(self, sql, *params):
        query = normalized(sql)
        if "col_length" in query:
            self.row = (None if params[1] == self.missing_column else 16,)
        elif "from sys.columns" in query:
            column = params[-1]
            sql_type = (
                "nvarchar" if column == "status" else
                "int" if column == "sort_order" else
                "datetime2" if column.endswith("_at") else
                "uniqueidentifier"
            )
            self.row = (sql_type, column in {"started_at", "completed_at", "revoked_at"})
        elif "from sys.key_constraints" in query:
            self.rows = [("id",)]
        elif "from sys.indexes" in query and "from sys.indexes i" not in query:
            name = params[-1]
            filtered = name == "UQ_microlesson_assignment_active"
            unique = not name.startswith("IX_")
            self.row = (unique, 0, filtered, "[status] IN ('assigned','in_progress')" if filtered else None)
            if name == self.bad_index:
                self.row = (not unique, 0, filtered, self.row[3])
        elif "from sys.foreign_keys fk" in query:
            name = params[-1]
            mapping = {
                "FK_microlesson_assignment_client": [("client", "client_id", "id")],
                "FK_microlesson_assignment_lesson_client": [("microlesson", "microlesson_id", "id"), ("microlesson", "client_id", "client_id")],
                "FK_microlesson_assignment_user_client": [("app_user", "user_id", "id"), ("app_user", "client_id", "client_id")],
                "FK_microlesson_assignment_assigned_by": [("app_user", "assigned_by", "id")],
            }
            self.rows = mapping[name]
            if name == self.bad_shape:
                self.rows = [("client", "wrong", "id")]
        elif "from sys.indexes i" in query:
            name = params[-1]
            mapping = {
                "UQ_microlesson_id_client": [("id",), ("client_id",)],
                "UQ_app_user_id_client": [("id",), ("client_id",)],
                "UQ_microlesson_assignment_active": [("client_id",), ("user_id",), ("microlesson_id",)],
            }
            self.rows = mapping[name]
            if name == self.bad_shape:
                self.rows = [("wrong",)]
        elif "from sys.foreign_keys" in query:
            self.row = (0, 0) if params[-1] != self.bad_fk else None
        elif "from sys.check_constraints" in query:
            self.row = (0, 0) if params[-1] != self.bad_check else None
        else:
            raise AssertionError(f"Unexpected verification SQL: {sql}")
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_verify_rejects_missing_column_index_and_untrusted_constraints():
    verify_assignment_schema(MetadataCursor(), SchemaError)

    with pytest.raises(SchemaError, match="sort_order"):
        verify_assignment_schema(MetadataCursor(missing_column="sort_order"), SchemaError)
    with pytest.raises(SchemaError, match="UQ_microlesson_assignment_active"):
        verify_assignment_schema(MetadataCursor(bad_index="UQ_microlesson_assignment_active"), SchemaError)
    with pytest.raises(SchemaError, match="FK_microlesson_assignment_user_client"):
        verify_assignment_schema(MetadataCursor(bad_fk="FK_microlesson_assignment_user_client"), SchemaError)
    with pytest.raises(SchemaError, match="CK_microlesson_assignment_status"):
        verify_assignment_schema(MetadataCursor(bad_check="CK_microlesson_assignment_status"), SchemaError)
    with pytest.raises(SchemaError, match="Las columnas de FK_microlesson_assignment_user_client"):
        verify_assignment_schema(MetadataCursor(bad_shape="FK_microlesson_assignment_user_client"), SchemaError)


def test_prepare_wires_assignment_steps_and_verification():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "prepare_azure_database.py").read_text(encoding="utf-8")
    assert "from microlesson_assignment_migration import ASSIGNMENT_SCHEMA_STEPS, verify_assignment_schema" in source
    assert "for ddl in ASSIGNMENT_SCHEMA_STEPS:" in source
    assert "verify_assignment_schema(cursor, SeedError)" in source
