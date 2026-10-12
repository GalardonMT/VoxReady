#!/usr/bin/env python3
"""Fase 1: seed transaccional, idempotente y sin eliminaciones para Azure SQL.

Desde la raíz: python backend/scripts/seed_master_topics.py
Verificar sin escribir: añadir --verify-only. Validar sin conectar: --dry-run.
Los datos de la sección 5 del plan viven junto a este script en JSON UTF-8.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_CLIENT_ID = "7D8C0575-196C-40D1-AD7C-08AA2843B4C3"
SEED_NAMESPACE = uuid.UUID("f126b3bf-f626-47cd-9990-ae2b533c32eb")

SCENARIO_QUESTION_DDL = """
IF OBJECT_ID(N'dbo.scenario_question', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.scenario_question (
        id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        scenario_id UNIQUEIDENTIFIER NOT NULL,
        question_id UNIQUEIDENTIFIER NOT NULL,
        sequence_no INT NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_scenario_question_scenario FOREIGN KEY (scenario_id) REFERENCES dbo.scenario(id),
        CONSTRAINT FK_scenario_question_question FOREIGN KEY (question_id) REFERENCES dbo.question(id),
        CONSTRAINT UQ_scenario_question UNIQUE (scenario_id, question_id),
        CONSTRAINT UQ_scenario_sequence UNIQUE (scenario_id, sequence_no)
    );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.scenario_question')
               AND name = N'idx_scenario_question_lookup')
    CREATE INDEX idx_scenario_question_lookup ON dbo.scenario_question(scenario_id, sequence_no);
"""

REQUIRED_COLUMNS = {
    "client": {"id", "name", "status"},
    "topic": {"id", "client_id", "name", "context", "optics", "audience", "status", "created_at", "updated_at"},
    "topic_key_message": {"id", "topic_id", "text", "sort_order"},
    "topic_red_line": {"id", "topic_id", "text", "sort_order"},
    "question": {"id", "topic_id", "client_id", "text", "source", "base_language", "in_bank", "status", "created_at", "updated_at"},
    "scenario": {"id", "topic_id", "client_id", "title", "category", "difficulty", "estimated_minutes", "question_count", "status", "created_at", "updated_at"},
}


class SeedError(Exception):
    """Error seguro para consola; nunca incluye credenciales."""


def seed_id(key):
    return str(uuid.uuid5(SEED_NAMESPACE, key))


def load_seed():
    topics = json.loads((SCRIPT_DIR / "master_topics_seed.json").read_text(encoding="utf-8"))
    if len(topics) != 3 or len({t["key"] for t in topics}) != 3:
        raise SeedError("La semilla debe contener los tres temas de la sección 5.")
    for topic in topics:
        scenario = topic["scenario"]
        if topic["optics"] not in {"empathetic", "formal", "technical"}:
            raise SeedError("Óptica fuera del diccionario técnico.")
        if topic["audience"] not in {"leadership", "frontline", "technical"}:
            raise SeedError("Público fuera del diccionario técnico.")
        if scenario["category"] not in {"health", "operational", "reputational"}:
            raise SeedError("Categoría fuera del diccionario técnico.")
        if scenario["difficulty"] not in {"basic", "intermediate", "hard"}:
            raise SeedError("Dificultad fuera del diccionario técnico.")
        if not isinstance(scenario["estimatedMinutes"], int) or scenario["estimatedMinutes"] <= 0:
            raise SeedError("Duración inválida.")
        if not topic["name"].strip() or not topic["context"].strip() or not scenario["title"].strip():
            raise SeedError("Nombre, contexto y título son obligatorios.")
        if len(topic["name"]) > 150 or len(scenario["title"]) > 150:
            raise SeedError("Nombre o título exceden NVARCHAR(150).")
        # Ocho es el tamaño de esta semilla, no un límite del banco de preguntas.
        if len(topic["questions"]) != 8 or len(topic["keyMessages"]) != 2 or len(topic["redLines"]) != 2:
            raise SeedError("Los ejemplos deben incluir 8 preguntas, 2 mensajes y 2 líneas rojas.")
        for text in topic["questions"] + topic["keyMessages"] + topic["redLines"]:
            if not text.strip() or len(text) > 500:
                raise SeedError("Texto vacío o superior a NVARCHAR(500).")
    return topics


def connect():
    try:
        import pyodbc
        from dotenv import load_dotenv
    except ImportError:
        raise SeedError("Instala backend/requirements.txt antes de conectar.") from None
    # Ruta explícita: funciona desde cualquier directorio. El entorno tiene prioridad.
    load_dotenv(SCRIPT_DIR.parent / ".env", override=False)
    connection_string = os.getenv("SQL_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise SeedError("Falta SQL_CONNECTION_STRING en el entorno o backend/.env.")
    if "DRIVER=" not in connection_string.upper():
        connection_string = "DRIVER={ODBC Driver 18 for SQL Server};" + connection_string
    if "ODBC Driver 18 for SQL Server" in connection_string and "ODBC Driver 18 for SQL Server" not in pyodbc.drivers():
        raise SeedError("Falta Microsoft ODBC Driver 18 for SQL Server. Instálalo o usa la imagen backend/Dockerfile.")
    if "ENCRYPT=" not in connection_string.upper():
        connection_string += ";Encrypt=yes;TrustServerCertificate=no;"
    try:
        return pyodbc.connect(connection_string, timeout=30, autocommit=False)
    except pyodbc.Error as error:
        # Los mensajes del driver pueden contener información de conexión.
        state = str(error.args[0]) if error.args else "desconocido"
        raise SeedError(f"No se pudo conectar a Azure SQL (SQLSTATE {state}). Revisa driver, red y credenciales.") from None


def inspect_schema(cursor, allow_global_migration=False):
    cursor.execute("""SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                      FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo'""")
    schema = {}
    for table, column, data_type, nullable in cursor.fetchall():
        schema.setdefault(table, {})[column] = (data_type, nullable)
    for table, required in REQUIRED_COLUMNS.items():
        missing = required - schema.get(table, {}).keys()
        if missing:
            raise SeedError(f"Esquema incompatible: dbo.{table} carece de {', '.join(sorted(missing))}.")
        if schema[table]["id"][0] != "uniqueidentifier":
            raise SeedError(f"Esquema incompatible: dbo.{table}.id debe ser UNIQUEIDENTIFIER.")
    for table in ("topic", "question"):
        if schema[table]["client_id"][0] != "uniqueidentifier":
            raise SeedError(f"dbo.{table}.client_id debe ser UNIQUEIDENTIFIER.")
        if schema[table]["client_id"][1] != "YES" and not allow_global_migration:
            raise SeedError(f"dbo.{table}.client_id debe aceptar NULL para el catálogo maestro global.")
    deleted_filter = " AND (is_deleted IS NULL OR is_deleted = 0)" if "is_deleted" in schema["client"] else ""
    cursor.execute("SELECT name FROM dbo.client WHERE id = ? AND status = 'active'" + deleted_filter, DEMO_CLIENT_ID)
    if not cursor.fetchone():
        raise SeedError("El Cliente Demo VoxReady del plan no existe o no está activo. No se creará ni modificará un cliente.")
    return schema


def verify_link_schema(cursor):
    cursor.execute("""SELECT name FROM sys.key_constraints
                      WHERE parent_object_id = OBJECT_ID(N'dbo.scenario_question') AND type = 'UQ'""")
    names = {row[0] for row in cursor.fetchall()}
    if not {"UQ_scenario_question", "UQ_scenario_sequence"} <= names:
        raise SeedError("scenario_question no tiene las dos restricciones únicas del plan.")
    cursor.execute("""SELECT name FROM sys.foreign_keys
                      WHERE parent_object_id = OBJECT_ID(N'dbo.scenario_question')
                      AND is_disabled = 0 AND is_not_trusted = 0 AND delete_referential_action = 0""")
    names = {row[0] for row in cursor.fetchall()}
    if not {"FK_scenario_question_scenario", "FK_scenario_question_question"} <= names:
        raise SeedError("scenario_question no tiene las claves foráneas activas y sin borrado en cascada del plan.")
    cursor.execute("""SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.scenario_question')
                      AND name = 'idx_scenario_question_lookup' AND is_disabled = 0""")
    if not cursor.fetchone():
        raise SeedError("Falta el índice de búsqueda de scenario_question.")


def insert_missing(cursor, schema, table, values):
    """Solo inserta IDs propios ausentes. Nunca sobrescribe, reactiva o borra."""
    cursor.execute(f"SELECT id FROM dbo.[{table}] WHERE id = ?", values["id"])
    if cursor.fetchone():
        return False
    values = dict(values)
    if "is_deleted" in schema.get(table, {}):
        values["is_deleted"] = 0
    columns = list(values)
    placeholders = ["?"] * len(columns)
    for timestamp in ("created_at", "updated_at"):
        if timestamp in schema.get(table, {}):
            columns.append(timestamp)
            placeholders.append("SYSUTCDATETIME()")
    cursor.execute(
        f"INSERT INTO dbo.[{table}] ({', '.join('[' + c + ']' for c in columns)}) "
        f"VALUES ({', '.join(placeholders)})", tuple(values.values())
    )
    return True


def insert_seed(cursor, schema, topics):
    counts = {t: 0 for t in ("topic", "topic_key_message", "topic_red_line", "question", "scenario", "scenario_question")}

    def add(table, **values):
        counts[table] += int(insert_missing(cursor, schema, table, values))

    for topic in topics:
        key = topic["key"]
        topic_id = seed_id(key)
        add("topic", id=topic_id, client_id=None, name=topic["name"], context=topic["context"],
            optics=topic["optics"], audience=topic["audience"], status="active")
        for table, field in (("topic_key_message", "keyMessages"), ("topic_red_line", "redLines")):
            for position, text in enumerate(topic[field], 1):
                add(table, id=seed_id(f"{key}/{field}/{position}"), topic_id=topic_id, text=text, sort_order=position)
        question_ids = []
        for position, text in enumerate(topic["questions"], 1):
            question_id = seed_id(f"{key}/questions/{position}")
            question_ids.append(question_id)
            values = dict(id=question_id, topic_id=topic_id, client_id=None, text=text,
                          source="master", base_language="es", in_bank=1, status="active")
            if "sort_order" in schema["question"]:
                values["sort_order"] = position
            add("question", **values)
        scenario = topic["scenario"]
        scenario_id = seed_id(f"{key}/scenario")
        add("scenario", id=scenario_id, topic_id=topic_id, client_id=DEMO_CLIENT_ID,
            title=scenario["title"], category=scenario["category"], difficulty=scenario["difficulty"],
            estimated_minutes=scenario["estimatedMinutes"], question_count=len(question_ids), status="active")
        for position, question_id in enumerate(question_ids, 1):
            add("scenario_question", id=seed_id(f"{key}/assignment/{position}"), scenario_id=scenario_id,
                question_id=question_id, sequence_no=position)
    return counts


def verify_seed(cursor, schema, topics):
    """Verificación por IDs propios y contenido, sin contar datos ajenos."""
    for topic in topics:
        key = topic["key"]
        topic_id = seed_id(key)
        topic_filter = " AND (is_deleted IS NULL OR is_deleted = 0)" if "is_deleted" in schema["topic"] else ""
        cursor.execute("SELECT name, context, optics, audience, status, client_id FROM dbo.topic WHERE id = ?" + topic_filter, topic_id)
        row = cursor.fetchone()
        expected = (topic["name"], topic["context"], topic["optics"], topic["audience"], "active", None)
        if not row or tuple(row) != expected:
            raise SeedError(f"Tema {key} ausente o diferente de la semilla. Se conservan los datos existentes; no se sobrescriben.")
        for table, field in (("topic_key_message", "keyMessages"), ("topic_red_line", "redLines")):
            cursor.execute(f"SELECT text, sort_order FROM dbo.[{table}] WHERE topic_id = ? ORDER BY sort_order", topic_id)
            if [tuple(r) for r in cursor.fetchall()] != [(text, i) for i, text in enumerate(topic[field], 1)]:
                raise SeedError(f"Mensajes o líneas rojas de {key} no coinciden con el plan.")
        scenario_id = seed_id(f"{key}/scenario")
        scenario_filter = " AND (is_deleted IS NULL OR is_deleted = 0)" if "is_deleted" in schema["scenario"] else ""
        cursor.execute("""SELECT title, category, difficulty, estimated_minutes, question_count, status,
                          CONVERT(varchar(36), client_id), CONVERT(varchar(36), topic_id)
                          FROM dbo.scenario WHERE id = ?""" + scenario_filter, scenario_id)
        row = cursor.fetchone()
        s = topic["scenario"]
        expected = (s["title"], s["category"], s["difficulty"], s["estimatedMinutes"], len(topic["questions"]), "active")
        if not row or tuple(row[:6]) != expected or str(row[6]).lower() != DEMO_CLIENT_ID.lower() or str(row[7]).lower() != topic_id:
            raise SeedError(f"Escenario de {key} ausente o diferente del plan.")
        cursor.execute("SELECT COUNT(*) FROM dbo.question WHERE topic_id = ?", topic_id)
        if cursor.fetchone()[0] != len(topic["questions"]):
            raise SeedError(f"El banco de {key} no coincide con la semilla de 8 preguntas.")
        question_filter = " AND (q.is_deleted IS NULL OR q.is_deleted = 0)" if "is_deleted" in schema["question"] else ""
        cursor.execute("""SELECT sq.sequence_no, q.text, q.source, q.base_language, q.in_bank, q.status,
                          CONVERT(varchar(36), q.topic_id), q.client_id, CONVERT(varchar(36), q.id)
                          FROM dbo.scenario_question sq JOIN dbo.question q ON q.id = sq.question_id
                          WHERE sq.scenario_id = ?""" + question_filter + " ORDER BY sq.sequence_no", scenario_id)
        rows = cursor.fetchall()
        if len(rows) != len(topic["questions"]):
            raise SeedError(f"Escenario de {key} no tiene las 8 preguntas asignadas.")
        for position, (row, text) in enumerate(zip(rows, topic["questions"]), 1):
            if tuple(row[:6]) != (position, text, "master", "es", True, "active") or str(row[6]).lower() != topic_id or row[7] is not None or str(row[8]).lower() != seed_id(f"{key}/questions/{position}"):
                raise SeedError(f"Pregunta {position} de {key}: datos, pertenencia u orden incorrectos.")


def run_seed(connection, topics, verify_only=False):
    try:
        cursor = connection.cursor()
        if not verify_only:
            cursor.execute("SET XACT_ABORT ON; IF @@TRANCOUNT = 0 BEGIN TRANSACTION;")
            # Serializa dos ejecuciones simultáneas, incluyendo la creación de tabla.
            cursor.execute("""DECLARE @result int;
                EXEC @result = sys.sp_getapplock @Resource = N'voxready-master-topics-seed-v1',
                     @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 30000;
                IF @result < 0 THROW 51000, 'No se pudo adquirir el bloqueo del seed', 1;""")
        schema = inspect_schema(cursor, allow_global_migration=not verify_only)
        if not verify_only:
            for table in ("topic", "question"):
                if schema[table]["client_id"][1] != "YES":
                    cursor.execute(f"ALTER TABLE dbo.[{table}] ALTER COLUMN client_id UNIQUEIDENTIFIER NULL")
            schema = inspect_schema(cursor)
            cursor.execute(SCENARIO_QUESTION_DDL)
        verify_link_schema(cursor)
        counts = {} if verify_only else insert_seed(cursor, schema, topics)
        verify_seed(cursor, schema, topics)
        if verify_only:
            connection.rollback()
        else:
            connection.commit()
        return counts
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validar archivos locales sin conexión ni escrituras")
    mode.add_argument("--verify-only", action="store_true", help="Verificar Azure SQL sin DDL ni inserciones")
    args = parser.parse_args(argv)
    try:
        topics = load_seed()
        if args.dry_run:
            print("Validación LOCAL correcta; Azure SQL no fue consultado.")
        else:
            counts = run_seed(connect(), topics, args.verify_only)
            print("Azure SQL: estructura, contenido, cliente y orden de preguntas verificados.")
            if counts:
                print("Registros NUEVOS: " + ", ".join(f"{table}={count}" for table, count in counts.items()))
        print("Semilla: 3 temas globales, 6 mensajes, 6 líneas rojas, 24 preguntas, 3 escenarios, 24 asignaciones.")
        print("Cliente: " + DEMO_CLIENT_ID + ". Sin eliminaciones ni modificaciones de registros existentes.")
        return 0
    except SeedError as error:
        print(f"ERROR: {error}", file=sys.stderr)
    except Exception as error:
        print(f"ERROR: falló la operación ({type(error).__name__}); no se confirmaron cambios. Revisa el esquema y los permisos de Azure SQL.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
