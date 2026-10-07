"""Pruebas locales del seed; no sustituyen --verify-only contra Azure SQL.

El adaptador SQLite conserva PK/FK/UNIQUE y traduce únicamente el dialecto.
La creación y metadatos de la tabla Azure se prueban por separado al desplegar.
"""
import importlib.util
from pathlib import Path
import re
import sqlite3

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_master_topics.py"
spec = importlib.util.spec_from_file_location("seed_master_topics", SCRIPT)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class SqlAdapter:
    def __init__(self, include_sort_order=False):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.schema = {table: {column: ("uniqueidentifier" if column.endswith("id") else "nvarchar", "YES")
                               for column in columns} for table, columns in seed.REQUIRED_COLUMNS.items()}
        for table in ("topic", "question", "scenario"):
            self.schema[table]["is_deleted"] = ("bit", "YES")
        if include_sort_order:
            self.schema["question"]["sort_order"] = ("int", "YES")
        self.schema["scenario_question"] = {column: ("uniqueidentifier", "YES") for column in ("id", "scenario_id", "question_id", "sequence_no", "created_at")}
        for table, columns in self.schema.items():
            definitions = [f'[{column}] ' + ("INTEGER" if column in {"sort_order", "in_bank", "is_deleted", "sequence_no", "estimated_minutes", "question_count"} else "TEXT") + (" PRIMARY KEY" if column == "id" else "") for column in columns]
            if table == "scenario_question":
                definitions += ["UNIQUE(scenario_id, question_id)", "UNIQUE(scenario_id, sequence_no)", "FOREIGN KEY(scenario_id) REFERENCES scenario(id)", "FOREIGN KEY(question_id) REFERENCES question(id)"]
            self.db.execute(f"CREATE TABLE [{table}] ({', '.join(definitions)})")
        self.db.execute("INSERT INTO client(id,name,status) VALUES (?,?,?)", (seed.DEMO_CLIENT_ID, "Cliente Demo VoxReady", "active"))
        self.db.commit()

    def cursor(self):
        return self

    def execute(self, sql, *parameters):
        self.statements.append(sql)
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            self.rows = [(table, column, *metadata) for table, columns in self.schema.items() for column, metadata in columns.items()]
        elif "sys.key_constraints" in sql:
            self.rows = [("UQ_scenario_question",), ("UQ_scenario_sequence",)]
        elif "sys.foreign_keys" in sql:
            self.rows = [("FK_scenario_question_scenario",), ("FK_scenario_question_question",)]
        elif "sys.indexes" in sql and "CREATE" not in sql:
            self.rows = [("idx_scenario_question_lookup",)]
        elif "SET XACT_ABORT" in sql:
            self.db.execute("BEGIN")
            self.rows = []
        elif "sp_getapplock" in sql or sql == seed.SCENARIO_QUESTION_DDL:
            self.rows = []
        elif sql.startswith("ALTER TABLE"):
            table = re.search(r"dbo\.\[(\w+)\]", sql).group(1)
            self.schema[table]["client_id"] = ("uniqueidentifier", "YES")
            self.rows = []
        else:
            translated = sql.replace("dbo.", "").replace("SYSUTCDATETIME()", "CURRENT_TIMESTAMP")
            translated = re.sub(r"CONVERT\(varchar\(36\), ([\w.]+)\)", r"\1", translated)
            params = parameters[0] if len(parameters) == 1 and isinstance(parameters[0], tuple) else parameters
            self.rows = self.db.execute(translated, params).fetchall()
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def commit(self):
        self.commits += 1
        self.db.commit()

    def rollback(self):
        self.rollbacks += 1
        self.db.rollback()

    def close(self):
        self.closed = True


@pytest.mark.parametrize("sort_order", [False, True])
def test_seed_contents_order_and_repeat_execution(sort_order):
    db = SqlAdapter(sort_order)
    topics = seed.load_seed()
    expected = {"topic": 3, "topic_key_message": 6, "topic_red_line": 6,
                "question": 24, "scenario": 3, "scenario_question": 24}
    assert seed.run_seed(db, topics) == expected
    assert db.commits == 1
    assert seed.run_seed(db, topics) == dict.fromkeys(expected, 0)
    assert db.commits == 2
    for table, count in expected.items():
        assert db.db.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0] == count
    assert not any(re.search(r"\b(?:DELETE|TRUNCATE|DROP|UPDATE)\b", sql, re.I) for sql in db.statements)
    assert seed.run_seed(db, topics, verify_only=True) == {}
    assert db.commits == 2
    assert db.rollbacks == 1


def test_preserves_unrelated_data():
    db = SqlAdapter()
    db.db.execute("INSERT INTO topic(id,name,status) VALUES ('customer-topic', 'Tema anterior', 'archived')")
    db.db.commit()
    seed.run_seed(db, seed.load_seed())
    assert db.db.execute("SELECT name,status FROM topic WHERE id='customer-topic'").fetchone() == ("Tema anterior", "archived")


def test_rolls_back_entire_seed_if_existing_topic_was_edited():
    db = SqlAdapter()
    db.db.execute("INSERT INTO topic(id,name,status) VALUES (?, 'Edición manual', 'archived')", (seed.seed_id("topic-1"),))
    db.db.commit()
    with pytest.raises(seed.SeedError, match="Se conservan"):
        seed.run_seed(db, seed.load_seed())
    assert db.commits == 0 and db.rollbacks == 1 and db.closed
    assert db.db.execute("SELECT COUNT(*) FROM scenario").fetchone()[0] == 0
    assert db.db.execute("SELECT COUNT(*) FROM question").fetchone()[0] == 0
    assert db.db.execute("SELECT name,status FROM topic").fetchall() == [("Edición manual", "archived")]


def test_missing_demo_client_prevents_writes():
    db = SqlAdapter()
    db.db.execute("UPDATE client SET status='archived'")
    db.db.commit()
    with pytest.raises(seed.SeedError, match="no existe o no está activo"):
        seed.run_seed(db, seed.load_seed())
    assert not any(sql.startswith("INSERT") or sql == seed.SCENARIO_QUESTION_DDL for sql in db.statements)


def test_verify_only_does_not_create_missing_seed():
    db = SqlAdapter()
    with pytest.raises(seed.SeedError, match="ausente"):
        seed.run_seed(db, seed.load_seed(), verify_only=True)
    assert not any("INSERT" in sql or "CREATE" in sql or "sp_getapplock" in sql for sql in db.statements)
    assert db.commits == 0


def test_incompatible_global_schema_is_rejected():
    db = SqlAdapter()
    db.schema["question"]["client_id"] = ("uniqueidentifier", "NO")
    with pytest.raises(seed.SeedError, match="debe aceptar NULL"):
        seed.run_seed(db, seed.load_seed(), verify_only=True)
    assert db.commits == 0


def test_non_nullable_tenant_columns_migrate_for_global_catalog():
    db = SqlAdapter()
    for table in ("topic", "question"):
        db.schema[table]["client_id"] = ("uniqueidentifier", "NO")
    seed.run_seed(db, seed.load_seed())
    assert db.commits == 1
    assert sum(sql.startswith("ALTER TABLE") for sql in db.statements) == 2
    assert all(db.schema[t]["client_id"][1] == "YES" for t in ("topic", "question"))


def test_wrong_question_order_is_detected():
    db = SqlAdapter()
    topics = seed.load_seed()
    seed.run_seed(db, topics)
    db.db.execute("UPDATE scenario_question SET sequence_no=99 WHERE id=?", (seed.seed_id("topic-1/assignment/1"),))
    db.db.commit()
    with pytest.raises(seed.SeedError, match="orden incorrectos"):
        seed.run_seed(db, topics, verify_only=True)


def test_dry_run_never_connects(monkeypatch, capsys):
    def forbidden():
        raise AssertionError("dry-run must not connect")
    monkeypatch.setattr(seed, "connect", forbidden)
    assert seed.main(["--dry-run"]) == 0
    assert "LOCAL" in capsys.readouterr().out


def test_exact_technical_dictionary_and_unicode():
    topics = seed.load_seed()
    assert [t["optics"] for t in topics] == ["empathetic", "technical", "formal"]
    assert [t["audience"] for t in topics] == ["leadership", "frontline", "leadership"]
    assert [t["scenario"]["category"] for t in topics] == ["health", "operational", "reputational"]
    assert [t["scenario"]["difficulty"] for t in topics] == ["hard", "intermediate", "intermediate"]
    assert [t["scenario"]["estimatedMinutes"] for t in topics] == [15, 10, 12]
    assert topics[0]["questions"][0].startswith("¿Cuál")
    assert len({seed.seed_id(f"{t['key']}/questions/{i}") for t in topics for i in range(1, 9)}) == 24
