#!/usr/bin/env python3
"""Reconcile completed sessions into labeling cases in explicit safe batches.

Dry-run is read-only and is the required preflight before any shared write.
Write mode requires both ``--apply`` and an exact confirmation phrase. The
command is never imported or executed by application startup or by
``prepare_azure_database.py``.
"""

import argparse
import json
import math
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labeling_classification import (
    ClassificationError,
    QUEUE_REASONS,
    classify_case,
    rules_from_metric_thresholds,
)
from labeling_migration import verify as verify_labeling


DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 1000
MAX_LIMIT = 100000
MAX_ANOMALY_DETAILS = 100
WRITE_CONFIRMATION = "APPLY_LABELING_BACKFILL"
SOURCE_ISSUE_UNSEALED_RECORDING = "recording:unsealed_historical"


SUMMARY_SQL = """
SELECT
    COUNT_BIG(*) AS completed_sessions,
    SUM(CASE WHEN ISNULL(s.is_deleted,0)=1 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS deleted_sessions,
    (SELECT COUNT_BIG(*)
       FROM dbo.report AS r
       JOIN dbo.[session] AS sx ON sx.id=r.session_id
      WHERE sx.status='completed' AND r.is_current=1) AS completed_current_reports,
    (SELECT COUNT_BIG(*) FROM dbo.labeling_case) AS existing_cases,
    (SELECT COUNT_BIG(*)
       FROM dbo.report AS r
       JOIN dbo.[session] AS sx ON sx.id=r.session_id
      WHERE sx.status='completed' AND r.is_current=1
        AND NOT EXISTS (SELECT 1 FROM dbo.labeling_case AS lc WHERE lc.report_id=r.id)) AS unmaterialized_reports
FROM dbo.[session] AS s
WHERE s.status='completed';
"""


_BASE_BATCH_SQL = """
SELECT TOP (?)
    s.id AS session_id,
    COALESCE(s.finished_at,CONVERT(datetime2(3),'0001-01-01T00:00:00')) AS ordering_finished_at,
    ISNULL(s.is_deleted,0) AS is_deleted,
    s.client_id,
    report_stats.current_report_count,
    r.id AS report_id,
    r.overall_score,
    r.rubric_version_id,
    r.analysis_job_id,
    j.id AS job_id,
    j.session_id AS job_session_id,
    j.rubric_version_id AS job_rubric_version_id,
    fusion_stats.fusion_count,
    fusion_stats.summary_json AS fusion_json,
    (SELECT ra.id AS areaId,ra.area_key AS areaKey,score.value AS [value]
       FROM dbo.area_score AS score
       JOIN dbo.rubric_area AS ra ON ra.id=score.rubric_area_id
      WHERE score.report_id=r.id
      ORDER BY ra.area_key
      FOR JSON PATH) AS areas_json,
    (SELECT mv.metric_key AS metricKey,mv.thresholds_json AS thresholdsJson
       FROM dbo.rubric_metric_value AS mv
      WHERE mv.rubric_version_id=r.rubric_version_id
        AND mv.metric_key IN ('gov.borderline_delta','gov.disparity_delta')
      ORDER BY mv.metric_key
      FOR JSON PATH) AS governance_json,
    lc.id AS existing_case_id
FROM dbo.[session] AS s
OUTER APPLY (
    SELECT COUNT_BIG(*) AS current_report_count
      FROM dbo.report AS counted
     WHERE counted.session_id=s.id AND counted.is_current=1
) AS report_stats
OUTER APPLY (
    SELECT TOP (1)
        selected.id,selected.overall_score,selected.rubric_version_id,selected.analysis_job_id
      FROM dbo.report AS selected
     WHERE selected.session_id=s.id AND selected.is_current=1
     ORDER BY selected.id
) AS r
LEFT JOIN dbo.analysis_job AS j ON j.id=r.analysis_job_id
OUTER APPLY (
    SELECT COUNT_BIG(*) AS fusion_count,MAX(apr.summary_json) AS summary_json
      FROM dbo.analysis_pipeline_result AS apr
     WHERE apr.analysis_job_id=r.analysis_job_id AND apr.pipeline='fusion'
) AS fusion_stats
LEFT JOIN dbo.labeling_case AS lc ON lc.report_id=r.id
WHERE s.status='completed'
{cursor_predicate}
ORDER BY ordering_finished_at ASC,s.id ASC;
"""

FIRST_BATCH_SQL = _BASE_BATCH_SQL.format(cursor_predicate="")
NEXT_BATCH_SQL = _BASE_BATCH_SQL.format(
    cursor_predicate="""AND (
      COALESCE(s.finished_at,CONVERT(datetime2(3),'0001-01-01T00:00:00'))>?
      OR (
          COALESCE(s.finished_at,CONVERT(datetime2(3),'0001-01-01T00:00:00'))=?
          AND s.id>?
      )
  )"""
)


INSERT_CASE_SQL = """
SET NOCOUNT ON;
INSERT INTO dbo.labeling_case (
    id,client_id,session_id,report_id,analysis_job_id,rubric_version_id,
    session_finished_at,queue_reason,reason_detail_json,ai_snapshot_json,
    snapshot_schema_version,source_status,status
)
SELECT ?,?,?,?,?,?,?,?,?,?,1,'ambiguous','pending'
WHERE EXISTS (
    SELECT 1
      FROM dbo.report AS r
      JOIN dbo.[session] AS s ON s.id=r.session_id
      JOIN dbo.analysis_job AS j
        ON j.id=r.analysis_job_id
       AND j.session_id=r.session_id
       AND j.rubric_version_id=r.rubric_version_id
     WHERE r.id=? AND r.session_id=? AND r.analysis_job_id=?
       AND r.rubric_version_id=? AND r.is_current=1
       AND s.status='completed' AND ISNULL(s.is_deleted,0)=0
       AND (SELECT COUNT_BIG(*) FROM dbo.report AS current_report
             WHERE current_report.session_id=r.session_id
               AND current_report.is_current=1)=1
       AND (SELECT COUNT_BIG(*) FROM dbo.analysis_pipeline_result AS apr
             WHERE apr.analysis_job_id=r.analysis_job_id
               AND apr.pipeline='fusion')=1
       AND EXISTS (
            SELECT 1 FROM dbo.analysis_pipeline_result AS apr
             WHERE apr.analysis_job_id=r.analysis_job_id
               AND apr.pipeline='fusion'
               AND ISJSON(apr.summary_json)=1
               AND LOWER(COALESCE(JSON_VALUE(apr.summary_json,'$.reportId'),
                                  JSON_VALUE(apr.summary_json,'$.report_id')))
                   =LOWER(CONVERT(nvarchar(36),r.id))
       )
)
AND NOT EXISTS (
    SELECT 1 FROM dbo.labeling_case WITH (UPDLOCK,HOLDLOCK) WHERE report_id=?
);
SELECT CONVERT(int,@@ROWCOUNT);
"""


class ReconciliationError(RuntimeError):
    """Safe operator-facing reconciliation failure."""


@dataclass
class ReconciliationSummary:
    mode: str
    status: str
    batch_size: int
    limit: int | None
    batches: int = 0
    completed_sessions: int = 0
    deleted_sessions: int = 0
    completed_current_reports: int = 0
    existing_cases: int = 0
    unmaterialized_reports: int = 0
    scanned: int = 0
    eligible: int = 0
    skipped: int = 0
    already_materialized: int = 0
    classification_errors: int = 0
    classification_counts: dict = field(
        default_factory=lambda: {reason: 0 for reason in QUEUE_REASONS}
    )
    anomaly_counts: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)
    anomaly_rows: int = 0
    created: int = 0
    duration_ms: int = 0
    write_blocked: bool = True
    estimate: dict = field(default_factory=dict)

    def add_anomaly(self, row, codes):
        self.anomaly_rows += 1
        for code in codes:
            self.anomaly_counts[code] = self.anomaly_counts.get(code, 0) + 1
        if len(self.anomalies) < MAX_ANOMALY_DETAILS:
            self.anomalies.append(
                {
                    "sessionId": str(row[0]),
                    "reportId": str(row[5]) if row[5] is not None else None,
                    "codes": sorted(codes),
                }
            )

    def finish_estimate(self, *, full_scan):
        lower = self.eligible * 0.020 + self.batches * 0.050
        upper = self.eligible * 0.100 + self.batches * 0.250
        self.estimate = {
            "eligibleCases": self.eligible,
            "lowerBoundSeconds": math.ceil(lower),
            "upperBoundSeconds": math.ceil(upper),
            "completeInventory": bool(full_scan),
            "basis": "20-100ms por insert y 50-250ms por lote; excluye migracion y contencion externa",
        }

    def to_wire(self):
        raw = asdict(self)
        return {
            "mode": raw["mode"],
            "status": raw["status"],
            "batchSize": raw["batch_size"],
            "limit": raw["limit"],
            "batches": raw["batches"],
            "completedSessions": raw["completed_sessions"],
            "deletedSessions": raw["deleted_sessions"],
            "completedCurrentReports": raw["completed_current_reports"],
            "existingCases": raw["existing_cases"],
            "unmaterializedReports": raw["unmaterialized_reports"],
            "scanned": raw["scanned"],
            "eligible": raw["eligible"],
            "skipped": raw["skipped"],
            "alreadyMaterialized": raw["already_materialized"],
            "classificationErrors": raw["classification_errors"],
            "classificationCounts": raw["classification_counts"],
            "anomalyCounts": raw["anomaly_counts"],
            "anomalyRows": raw["anomaly_rows"],
            "anomalies": raw["anomalies"],
            "anomalyDetailsTruncated": raw["anomaly_rows"] > len(raw["anomalies"]),
            "created": raw["created"],
            "durationMs": raw["duration_ms"],
            "writeBlocked": raw["write_blocked"],
            "estimate": raw["estimate"],
        }


def _bounded_int(label, minimum, maximum):
    def parse(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError(f"{label} debe ser un entero.") from None
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(
                f"{label} debe estar entre {minimum} y {maximum}."
            )
        return parsed

    return parse


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Descubre, clasifica, estima y reporta sin modificar datos.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Crea únicamente casos relacionalmente inequívocos dentro de una transacción.",
    )
    parser.add_argument(
        "--confirm-write",
        default=None,
        help=f"En modo --apply debe ser exactamente {WRITE_CONFIRMATION}.",
    )
    parser.add_argument(
        "--batch-size",
        type=_bounded_int("--batch-size", 1, MAX_BATCH_SIZE),
        default=DEFAULT_BATCH_SIZE,
        help=f"Filas por lote (1..{MAX_BATCH_SIZE}; default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--limit",
        type=_bounded_int("--limit", 1, MAX_LIMIT),
        default=None,
        help=f"Máximo a inspeccionar (1..{MAX_LIMIT}; inventario completo por defecto).",
    )
    return parser


def _validate_write_confirmation(parser, args):
    if args.apply and args.confirm_write != WRITE_CONFIRMATION:
        parser.error(
            f"--apply exige --confirm-write {WRITE_CONFIRMATION}; "
            "ejecuta primero un --dry-run completo"
        )
    if args.dry_run and args.confirm_write is not None:
        parser.error("--confirm-write solo es válido junto con --apply")


def _connect():
    from seed_master_topics import connect

    return connect()


def _require_schema(cursor):
    cursor.execute("SELECT OBJECT_ID(N'dbo.labeling_case',N'U')")
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise ReconciliationError(
            "Falta dbo.labeling_case; prepara y verifica el esquema antes de reconciliar."
        )


def _read_counts(cursor, summary):
    cursor.execute(SUMMARY_SQL)
    row = cursor.fetchone()
    if not row:
        raise ReconciliationError("No se pudo obtener el resumen de descubrimiento.")
    summary.completed_sessions = int(row[0] or 0)
    summary.deleted_sessions = int(row[1] or 0)
    summary.completed_current_reports = int(row[2] or 0)
    summary.existing_cases = int(row[3] or 0)
    summary.unmaterialized_reports = int(row[4] or 0)


def _load_json_array(value, label):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        raise ClassificationError(f"{label} no es JSON válido.") from None
    if not isinstance(parsed, list):
        raise ClassificationError(f"{label} debe ser una lista JSON.")
    return parsed


def _classification_inputs(row):
    raw_areas = _load_json_array(row[14], "areas")
    raw_governance = _load_json_array(row[15], "governance")

    area_scores = {}
    for item in raw_areas:
        if not isinstance(item, dict) or "areaKey" not in item or "value" not in item:
            raise ClassificationError("Un área no contiene areaKey y value.")
        key = str(item["areaKey"]).strip()
        if not key or key in area_scores:
            raise ClassificationError("Las áreas contienen una clave vacía o duplicada.")
        area_scores[key] = item["value"]

    metric_thresholds = {}
    for item in raw_governance:
        if not isinstance(item, dict) or "metricKey" not in item or "thresholdsJson" not in item:
            raise ClassificationError("Una regla de gobernanza no tiene contrato válido.")
        key = str(item["metricKey"]).strip()
        if not key or key in metric_thresholds:
            raise ClassificationError("Las reglas de gobernanza están vacías o duplicadas.")
        try:
            thresholds = json.loads(item["thresholdsJson"])
        except (TypeError, ValueError):
            raise ClassificationError(f"{key}.thresholdsJson no es JSON válido.") from None
        if not isinstance(thresholds, dict):
            raise ClassificationError(f"{key}.thresholdsJson debe ser un objeto.")
        metric_thresholds[key] = thresholds

    return row[6], area_scores, rules_from_metric_thresholds(metric_thresholds), raw_areas


def _fusion_report_id(value):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None, "fusion_json_invalid"
    if not isinstance(parsed, dict):
        return None, "fusion_json_invalid"
    report_id = parsed.get("reportId", parsed.get("report_id"))
    if report_id is None or not str(report_id).strip():
        return None, "fusion_report_id_missing"
    return str(report_id), None


def _anomaly_codes(row):
    codes = []
    if bool(row[2]):
        codes.append("session_deleted")
    current_reports = int(row[4] or 0)
    if current_reports == 0:
        codes.append("current_report_missing")
        return codes
    if current_reports > 1:
        codes.append("current_report_multiple")
        return codes
    if row[8] is None:
        codes.append("report_job_missing")
        return codes
    if row[9] is None:
        codes.append("report_job_orphan")
        return codes
    if str(row[10]).lower() != str(row[0]).lower():
        codes.append("job_session_mismatch")
    if str(row[11]).lower() != str(row[7]).lower():
        codes.append("job_rubric_mismatch")
    fusion_count = int(row[12] or 0)
    if fusion_count == 0:
        codes.append("fusion_missing")
    elif fusion_count > 1:
        codes.append("fusion_multiple")
    else:
        fusion_report_id, fusion_error = _fusion_report_id(row[13])
        if fusion_error:
            codes.append(fusion_error)
        elif fusion_report_id.lower() != str(row[5]).lower():
            codes.append("fusion_report_id_mismatch")
    return codes


def _wire_number(value):
    if isinstance(value, bool) or value is None:
        return value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    if not number.is_finite():
        return value
    integral = number.to_integral_value()
    return int(integral) if number == integral else float(number)


def _snapshot_json(row, raw_areas):
    areas = [
        {
            "areaId": str(item.get("areaId")) if item.get("areaId") is not None else None,
            "areaKey": str(item["areaKey"]),
            "aiValue": _wire_number(item["value"]),
        }
        for item in raw_areas
    ]
    return json.dumps(
        {
            "schemaVersion": 1,
            "reportId": str(row[5]),
            "overallScore": _wire_number(row[6]),
            "areas": areas,
            "metrics": [],
            "sourceIssues": [SOURCE_ISSUE_UNSEALED_RECORDING],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _insert_case(cursor, row, result, raw_areas):
    case_id = str(uuid.uuid4())
    reason_json = json.dumps(
        result.reason_detail,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    snapshot_json = _snapshot_json(row, raw_areas)
    cursor.execute(
        INSERT_CASE_SQL,
        case_id,
        row[3],
        row[0],
        row[5],
        row[8],
        row[7],
        row[1],
        result.queue_reason,
        reason_json,
        snapshot_json,
        row[5],
        row[0],
        row[8],
        row[7],
        row[5],
    )
    inserted = cursor.fetchone()
    return bool(inserted and int(inserted[0] or 0) == 1)


def reconcile(cursor, *, batch_size, limit, apply=False):
    """Inspect every bounded row and optionally create only unambiguous cases."""
    started = time.perf_counter()
    summary = ReconciliationSummary(
        mode="apply" if apply else "dry-run",
        status="reconciled" if apply else "preflight",
        batch_size=batch_size,
        limit=limit,
        write_blocked=not apply,
    )
    _require_schema(cursor)
    _read_counts(cursor, summary)

    remaining = limit
    last_finished_at = None
    last_session_id = None

    while remaining is None or remaining > 0:
        requested = batch_size if remaining is None else min(batch_size, remaining)
        if last_finished_at is None:
            cursor.execute(FIRST_BATCH_SQL, requested)
        else:
            cursor.execute(
                NEXT_BATCH_SQL,
                requested,
                last_finished_at,
                last_finished_at,
                last_session_id,
            )
        rows = list(cursor.fetchall())
        if not rows:
            break

        summary.batches += 1
        summary.scanned += len(rows)
        for row in rows:
            anomaly_codes = _anomaly_codes(row)
            if anomaly_codes:
                summary.skipped += 1
                summary.add_anomaly(row, anomaly_codes)
                continue
            if row[16] is not None:
                summary.skipped += 1
                summary.already_materialized += 1
                continue
            try:
                overall_score, area_scores, rules, raw_areas = _classification_inputs(row)
                result = classify_case(overall_score, area_scores, rules)
            except ClassificationError:
                summary.classification_errors += 1
                summary.skipped += 1
                summary.add_anomaly(row, ["classification_input_invalid"])
                continue

            summary.eligible += 1
            summary.classification_counts[result.queue_reason] += 1
            if apply and _insert_case(cursor, row, result, raw_areas):
                summary.created += 1
            elif apply:
                summary.skipped += 1
                summary.already_materialized += 1

        last_session_id = rows[-1][0]
        last_finished_at = rows[-1][1]
        if remaining is not None:
            remaining -= len(rows)
        if len(rows) < requested:
            break

    summary.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
    full_scan = limit is None or summary.scanned >= summary.completed_sessions
    summary.finish_estimate(full_scan=full_scan)
    return summary


def _begin_write(cursor):
    cursor.execute(
        "SET XACT_ABORT ON; SET LOCK_TIMEOUT 30000; "
        "IF @@TRANCOUNT=0 BEGIN TRANSACTION;"
    )
    cursor.execute(
        """DECLARE @schema_result int,@backfill_result int;
           EXEC @schema_result=sys.sp_getapplock
                @Resource='voxready-azure-schema-v1',
                @LockMode='Shared',@LockOwner='Transaction',@LockTimeout=30000;
           IF @schema_result<0 THROW 51000,'No se pudo estabilizar el esquema de etiquetado',1;
           EXEC @backfill_result=sys.sp_getapplock
                @Resource='voxready-labeling-backfill-v1',
                @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=30000;
           IF @backfill_result<0 THROW 51001,'No se pudo bloquear el backfill de etiquetado',1;"""
    )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_write_confirmation(parser, args)

    connection = None
    try:
        connection = _connect()
        connection.timeout = 60
        cursor = connection.cursor()
        cursor.execute("SET LOCK_TIMEOUT 10000; SET DEADLOCK_PRIORITY LOW;")
        if args.apply:
            _begin_write(cursor)
            verify_labeling(cursor, ReconciliationError)
        summary = reconcile(
            cursor,
            batch_size=args.batch_size,
            limit=args.limit,
            apply=args.apply,
        )
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        print(json.dumps(summary.to_wire(), ensure_ascii=False, sort_keys=True))
        return 0
    except ReconciliationError as error:
        if connection:
            connection.rollback()
        print(f"ERROR: {error}", file=sys.stderr)
    except Exception as error:
        if connection:
            connection.rollback()
        print(
            f"ERROR: reconciliación falló ({type(error).__name__}); "
            "la transacción fue revertida. Revisa conexión, esquema y permisos.",
            file=sys.stderr,
        )
    finally:
        if connection:
            connection.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
