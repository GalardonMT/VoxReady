"""Versioned metric configuration; published rubric versions are immutable."""

import json
import math
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

import master_topics


def _lock(cursor):
    cursor.execute("""DECLARE @result int;
        EXEC @result=sys.sp_getapplock @Resource='voxready-rubric-metrics',
             @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=15000;
        IF @result<0 THROW 51010,'No se pudo bloquear la rúbrica',1;""")


def _catalog(cursor):
    cursor.execute("""SELECT metric_key,category,label,description,unit,min_value,max_value,
                           step_value,control,threshold_keys,sort_order
                    FROM dbo.rubric_metric_definition ORDER BY sort_order""")
    return [dict(zip(("key", "category", "label", "description", "unit", "min", "max",
                      "step", "control", "thresholdKeys", "sortOrder"), row))
            for row in cursor.fetchall()]


def _published_version_number(cursor, version_id):
    cursor.execute("""WITH published_versions AS (
                        SELECT id,ROW_NUMBER() OVER (
                            ORDER BY published_at,created_at,id
                        ) AS version_number
                        FROM dbo.rubric_version
                        WHERE status='published'
                      )
                      SELECT version_number FROM published_versions WHERE id=?""", version_id)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(503, "No se pudo determinar el número de la versión publicada.")
    return int(row[0])


def _version(cursor, version_id, draft=False):
    if not version_id:
        return None
    if draft:
        cursor.execute("""SELECT id,version_label,revision,created_at
                          FROM dbo.rubric_metric_draft WHERE id=?""", version_id)
    else:
        cursor.execute("""SELECT id,version_label,0,created_at,published_at
                          FROM dbo.rubric_version WHERE id=?""", version_id)
    row = cursor.fetchone()
    if not row:
        return None
    version_number = None if draft else _published_version_number(cursor, version_id)
    definition = _catalog(cursor)
    source_table = "rubric_metric_draft_value" if draft else "rubric_metric_value"
    fk = "draft_id" if draft else "rubric_version_id"
    cursor.execute(f"SELECT metric_key,thresholds_json FROM dbo.{source_table} WHERE {fk}=?", version_id)
    values = {key: json.loads(value) for key, value in cursor.fetchall()}
    if len(values) != len(definition) or set(values) != {item["key"] for item in definition}:
        raise HTTPException(503, "La configuración de métricas está incompleta.")
    metrics = []
    for item in definition:
        item["min"] = float(item["min"])
        item["max"] = float(item["max"])
        item["step"] = float(item["step"])
        item["thresholdKeys"] = json.loads(item["thresholdKeys"])
        item.pop("sortOrder")
        item["thresholds"] = values[item["key"]]
        metrics.append(item)
    result = {"id": str(row[0]), "versionLabel": row[1], "status": "draft" if draft else "published",
              "revision": int(row[2]), "createdAt": row[3].isoformat(),
              "publishedAt": None if draft else row[4].isoformat(),
              "versionNumber": version_number, "metrics": metrics}
    return result


def latest_published(cursor):
    cursor.execute("""SELECT TOP 1 id FROM dbo.rubric_version
                      WHERE status='published'
                      ORDER BY published_at DESC,created_at DESC,id DESC""")
    row = cursor.fetchone()
    return _version(cursor, row[0]) if row else None


def current(cursor):
    published = latest_published(cursor)
    cursor.execute("SELECT TOP 1 id FROM dbo.rubric_metric_draft")
    row = cursor.fetchone()
    return {"published": published, "draft": _version(cursor, row[0], draft=True) if row else None}


def create_draft(cursor):
    _lock(cursor)
    cursor.execute("SELECT TOP 1 id FROM dbo.rubric_metric_draft")
    if cursor.fetchone():
        raise HTTPException(409, "Ya existe un borrador de métricas.")
    source = latest_published(cursor)
    if not source:
        raise HTTPException(503, "No hay una versión publicada de métricas.")
    draft_id = str(uuid.uuid4())
    cursor.execute("""INSERT INTO dbo.rubric_metric_draft(id,source_version_id,version_label,revision)
                      VALUES(?,?,?,1)""", draft_id, source["id"], _new_label())
    cursor.execute("""INSERT INTO dbo.rubric_metric_draft_value(draft_id,metric_key,thresholds_json)
                      SELECT ?,metric_key,thresholds_json FROM dbo.rubric_metric_value
                      WHERE rubric_version_id=?""", draft_id, source["id"])
    return _version(cursor, draft_id, draft=True)


def _validate(definitions, metrics):
    expected = {item["key"]: item for item in definitions}
    if len(metrics) != len(expected) or {m.key for m in metrics} != set(expected):
        raise HTTPException(422, "Se requieren exactamente las 16 métricas de la rúbrica.")
    for metric in metrics:
        item = expected[metric.key]
        keys = json.loads(item["thresholdKeys"])
        if set(metric.thresholds) != set(keys):
            raise HTTPException(422, f"Límites incompletos para {metric.key}.")
        low, high, step = map(float, (item["min"], item["max"], item["step"]))
        for value in metric.thresholds.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise HTTPException(422, f"Valor inválido para {metric.key}.")
            if not low <= value <= high or not math.isclose((value-low)/step, round((value-low)/step), abs_tol=1e-7):
                raise HTTPException(422, f"Valor fuera del rango o paso para {metric.key}.")
        values = [metric.thresholds[key] for key in keys]
        if len(values) > 1 and any(a >= b for a, b in zip(values, values[1:])):
            raise HTTPException(422, f"Los límites deben estar en orden para {metric.key}.")
        if metric.key == "gov.borderline_delta" and metric.thresholds["halfWidth"] + 3 > 50:
            raise HTTPException(422, "Ventana de puntaje inválida.")


def _require_draft(cursor, draft_id, revision):
    cursor.execute("""SELECT source_version_id,revision FROM dbo.rubric_metric_draft
                      WITH (UPDLOCK,HOLDLOCK) WHERE id=?""", str(draft_id))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Borrador no encontrado.")
    if row[1] != revision:
        raise HTTPException(409, "El borrador cambió; vuelve a cargarlo.")
    return str(row[0])


def save_draft(cursor, draft_id, revision, metrics):
    _require_draft(cursor, draft_id, revision)
    definitions = _catalog(cursor)
    _validate(definitions, metrics)
    for metric in metrics:
        cursor.execute("""UPDATE dbo.rubric_metric_draft_value SET thresholds_json=?
                          WHERE draft_id=? AND metric_key=?""",
                       json.dumps(metric.thresholds, sort_keys=True), str(draft_id), metric.key)
        if cursor.rowcount != 1:
            raise HTTPException(503, "La configuración de métricas está incompleta.")
    cursor.execute("UPDATE dbo.rubric_metric_draft SET revision=revision+1 WHERE id=?", str(draft_id))
    return _version(cursor, draft_id, draft=True)


def discard_draft(cursor, draft_id, revision):
    _require_draft(cursor, draft_id, revision)
    cursor.execute("DELETE FROM dbo.rubric_metric_draft_value WHERE draft_id=?", str(draft_id))
    cursor.execute("DELETE FROM dbo.rubric_metric_draft WHERE id=?", str(draft_id))


def _new_label():
    # Existing rubric_version.version_label is NVARCHAR(20).
    return "M" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:5]


def clone_published(cursor, source_id, *, notes, label=None):
    """Clone only known rubric columns; new area IDs preserve historical score links."""
    version_id = str(uuid.uuid4())
    cursor.execute("""INSERT INTO dbo.rubric_version(id,version_label,status,notes,published_at,created_at)
                      VALUES(?,?,'published',?,
                        (SELECT CASE WHEN MAX(published_at)>=SYSUTCDATETIME()
                          THEN DATEADD(microsecond,1,MAX(published_at))
                          ELSE SYSUTCDATETIME() END FROM dbo.rubric_version),
                        SYSUTCDATETIME())""",
                   version_id, label or _new_label(), notes)
    cursor.execute("""INSERT INTO dbo.rubric_area
                      (id,rubric_version_id,area_key,name,channel,criteria,weight,sort_order)
                      SELECT NEWID(),?,area_key,name,channel,criteria,weight,sort_order
                      FROM dbo.rubric_area WHERE rubric_version_id=?""", version_id, source_id)
    cursor.execute("SELECT COUNT(*) FROM dbo.rubric_area WHERE rubric_version_id=?", version_id)
    if cursor.fetchone()[0] == 0:
        raise HTTPException(503, "La rúbrica origen no contiene áreas.")
    return version_id


def publish_draft(cursor, draft_id, revision):
    _lock(cursor)
    source_id = _require_draft(cursor, draft_id, revision)
    cursor.execute("""SELECT TOP 1 id FROM dbo.rubric_version WITH (UPDLOCK,HOLDLOCK)
                      WHERE status='published' ORDER BY published_at DESC,created_at DESC,id DESC""")
    latest = cursor.fetchone()
    if not latest or str(latest[0]).lower() != source_id.lower():
        raise HTTPException(409, "La rúbrica publicada cambió; crea un nuevo borrador.")
    definitions = _catalog(cursor)
    cursor.execute("SELECT metric_key,thresholds_json FROM dbo.rubric_metric_draft_value WHERE draft_id=?", str(draft_id))
    from types import SimpleNamespace
    values = [SimpleNamespace(key=key, thresholds=json.loads(raw)) for key, raw in cursor.fetchall()]
    _validate(definitions, values)
    cursor.execute("SELECT version_label FROM dbo.rubric_metric_draft WHERE id=?", str(draft_id))
    version_label = cursor.fetchone()[0]
    version_id = clone_published(cursor, source_id, notes="Intervalos de métricas publicados desde el editor maestro.", label=version_label)
    cursor.execute("""INSERT INTO dbo.rubric_metric_value(rubric_version_id,metric_key,thresholds_json)
                      SELECT ?,metric_key,thresholds_json FROM dbo.rubric_metric_draft_value
                      WHERE draft_id=?""", version_id, str(draft_id))
    cursor.execute("DELETE FROM dbo.rubric_metric_draft_value WHERE draft_id=?", str(draft_id))
    cursor.execute("DELETE FROM dbo.rubric_metric_draft WHERE id=?", str(draft_id))
    return _version(cursor, version_id)
