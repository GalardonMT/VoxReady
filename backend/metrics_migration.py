"""Additive, idempotent rubric metrics schema and approved initial publication."""

import json
from decimal import Decimal

from metrics_catalog import METRICS
from metrics_store import clone_published


SCHEMA_STEPS = (
    """IF OBJECT_ID(N'dbo.rubric_metric_definition',N'U') IS NULL
       CREATE TABLE dbo.rubric_metric_definition (
         metric_key NVARCHAR(80) NOT NULL PRIMARY KEY,
         category NVARCHAR(30) NOT NULL,
         label NVARCHAR(120) NOT NULL,
         description NVARCHAR(500) NOT NULL,
         unit NVARCHAR(30) NOT NULL,
         min_value DECIMAL(12,4) NOT NULL,
         max_value DECIMAL(12,4) NOT NULL,
         step_value DECIMAL(12,4) NOT NULL,
         control NVARCHAR(20) NOT NULL,
         threshold_keys NVARCHAR(300) NOT NULL,
         sort_order INT NOT NULL UNIQUE,
         CONSTRAINT CK_rubric_metric_definition_bounds CHECK
           (min_value<max_value AND step_value>0)
       );""",
    """IF OBJECT_ID(N'dbo.rubric_metric_value',N'U') IS NULL
       CREATE TABLE dbo.rubric_metric_value (
         rubric_version_id UNIQUEIDENTIFIER NOT NULL,
         metric_key NVARCHAR(80) NOT NULL,
         thresholds_json NVARCHAR(1000) NOT NULL,
         CONSTRAINT PK_rubric_metric_value PRIMARY KEY(rubric_version_id,metric_key),
         CONSTRAINT FK_rubric_metric_value_version FOREIGN KEY(rubric_version_id)
           REFERENCES dbo.rubric_version(id),
         CONSTRAINT FK_rubric_metric_value_definition FOREIGN KEY(metric_key)
           REFERENCES dbo.rubric_metric_definition(metric_key),
         CONSTRAINT CK_rubric_metric_value_json CHECK(ISJSON(thresholds_json)=1)
       );""",
    """IF OBJECT_ID(N'dbo.rubric_metric_draft',N'U') IS NULL
       CREATE TABLE dbo.rubric_metric_draft (
         id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
         source_version_id UNIQUEIDENTIFIER NOT NULL,
         version_label NVARCHAR(20) NOT NULL,
         revision INT NOT NULL CONSTRAINT DF_rubric_metric_draft_revision DEFAULT 1,
         draft_slot TINYINT NOT NULL CONSTRAINT DF_rubric_metric_draft_slot DEFAULT 1,
         created_at DATETIME2 NOT NULL CONSTRAINT DF_rubric_metric_draft_created DEFAULT SYSUTCDATETIME(),
         CONSTRAINT FK_rubric_metric_draft_source FOREIGN KEY(source_version_id)
           REFERENCES dbo.rubric_version(id),
         CONSTRAINT CK_rubric_metric_draft_slot CHECK(draft_slot=1),
         CONSTRAINT UQ_rubric_metric_draft_slot UNIQUE(draft_slot)
       );""",
    """IF OBJECT_ID(N'dbo.rubric_metric_draft_value',N'U') IS NULL
       CREATE TABLE dbo.rubric_metric_draft_value (
         draft_id UNIQUEIDENTIFIER NOT NULL,
         metric_key NVARCHAR(80) NOT NULL,
         thresholds_json NVARCHAR(1000) NOT NULL,
         CONSTRAINT PK_rubric_metric_draft_value PRIMARY KEY(draft_id,metric_key),
         CONSTRAINT FK_rubric_metric_draft_value_draft FOREIGN KEY(draft_id)
           REFERENCES dbo.rubric_metric_draft(id),
         CONSTRAINT FK_rubric_metric_draft_value_definition FOREIGN KEY(metric_key)
           REFERENCES dbo.rubric_metric_definition(metric_key),
         CONSTRAINT CK_rubric_metric_draft_value_json CHECK(ISJSON(thresholds_json)=1)
       );""",
)


def migrate(cursor):
    """Must run inside caller's transaction and schema migration lock."""
    for step in SCHEMA_STEPS:
        cursor.execute(step)
    cursor.execute("SELECT metric_key FROM dbo.rubric_metric_definition")
    existing = {row[0] for row in cursor.fetchall()}
    approved = {metric[0] for metric in METRICS}
    if existing - approved:
        raise RuntimeError("El catálogo SQL contiene métricas no aprobadas; no se modificó.")
    for position, metric in enumerate(METRICS, 1):
        key, category, label, description, unit, minimum, maximum, step, control, thresholds = metric
        if key in existing:
            continue
        cursor.execute("""INSERT INTO dbo.rubric_metric_definition
                          (metric_key,category,label,description,unit,min_value,max_value,
                           step_value,control,threshold_keys,sort_order)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       key, category, label, description, unit, minimum, maximum, step,
                       control, json.dumps(list(thresholds)), position)
    cursor.execute("SELECT COUNT(*) FROM dbo.rubric_metric_value")
    if cursor.fetchone()[0]:
        return
    cursor.execute("""SELECT TOP 1 id FROM dbo.rubric_version WHERE status='published'
                      ORDER BY published_at DESC,created_at DESC,id DESC""")
    source = cursor.fetchone()
    if not source:
        raise RuntimeError("No existe una rúbrica publicada para inicializar las métricas.")
    version_id = clone_published(cursor, str(source[0]), notes="Intervalos iniciales aprobados para español.")
    for metric in METRICS:
        cursor.execute("""INSERT INTO dbo.rubric_metric_value
                          (rubric_version_id,metric_key,thresholds_json) VALUES(?,?,?)""",
                       version_id, metric[0], json.dumps(metric[-1], sort_keys=True))


def verify(cursor):
    for table in ("rubric_metric_definition", "rubric_metric_value",
                  "rubric_metric_draft", "rubric_metric_draft_value"):
        cursor.execute("SELECT OBJECT_ID(?,N'U')", "dbo." + table)
        if cursor.fetchone()[0] is None:
            raise RuntimeError(f"Falta dbo.{table}.")
    for constraint in ("FK_rubric_metric_value_version", "FK_rubric_metric_value_definition",
                       "FK_rubric_metric_draft_source", "FK_rubric_metric_draft_value_draft",
                       "FK_rubric_metric_draft_value_definition"):
        cursor.execute("""SELECT is_disabled,is_not_trusted FROM sys.foreign_keys
                          WHERE name=? AND parent_object_id IN
                            (OBJECT_ID(N'dbo.rubric_metric_value'),OBJECT_ID(N'dbo.rubric_metric_draft'),
                             OBJECT_ID(N'dbo.rubric_metric_draft_value'))""", constraint)
        row = cursor.fetchone()
        if not row or row[0] or row[1]:
            raise RuntimeError(f"Clave foránea ausente o inválida: {constraint}.")
    cursor.execute("""SELECT metric_key,category,label,description,unit,min_value,max_value,
                           step_value,control,threshold_keys,sort_order
                    FROM dbo.rubric_metric_definition""")
    actual = {row[0]: row for row in cursor.fetchall()}
    if set(actual) != {item[0] for item in METRICS}:
        raise RuntimeError("El catálogo de métricas no contiene exactamente 16 entradas.")
    for position, metric in enumerate(METRICS, 1):
        key, category, label, description, unit, minimum, maximum, step, control, thresholds = metric
        row = actual[key]
        if (tuple(row[1:5]) != (category, label, description, unit)
                or tuple(Decimal(str(value)) for value in row[5:8]) !=
                tuple(Decimal(str(value)) for value in (minimum, maximum, step))
                or row[8] != control or json.loads(row[9]) != list(thresholds)
                or row[10] != position):
            raise RuntimeError(f"Metadatos fijos de {key} no coinciden con la especificación aprobada.")
    cursor.execute("""SELECT TOP 1 v.id,COUNT(m.metric_key) FROM dbo.rubric_version v
                      LEFT JOIN dbo.rubric_metric_value m ON m.rubric_version_id=v.id
                      WHERE v.status='published'
                      GROUP BY v.id,v.published_at,v.created_at
                      ORDER BY v.published_at DESC,v.created_at DESC,v.id DESC""")
    row = cursor.fetchone()
    if not row or row[1] != 16:
        raise RuntimeError("La última versión publicada no tiene las 16 métricas.")
