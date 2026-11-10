"""SQL store and domain invariants for the master labeling queue.

The module intentionally has no FastAPI dependency. Callers own the database
connection and transaction; mutating operations start a transaction only when
the caller has not already started one. Lease tokens are hashed before SQL and
never appear in audit details or return values outside lease responses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import secrets
import uuid


LEASE_MINUTES = 20
MAX_LIST_LIMIT = 10
AREA_LABELS = {
    "expression": "Expresión",
    "voice": "Tono de voz",
    "coherence": "Coherencia",
    "empathy": "Nivel de empatía",
}
CATEGORY_LABELS = {
    "voice": "Voz",
    "vision": "Video",
    "content": "Contenido",
    "empathy": "Empatía",
    "governance": "Gobernanza",
}
CATEGORY_ORDER = {key: index for index, key in enumerate(CATEGORY_LABELS)}
AUDIT_DETAIL_KEYS = {
    "labeling_case_claimed": {"leaseGeneration", "expiredPreviousLease"},
    "labeling_case_released": {"leaseGeneration"},
    "labeling_case_reviewed": {
        "reviewId",
        "reviewNo",
        "rubricCorrectionCount",
        "metricCorrectionCount",
        "changedCount",
    },
    "labeling_recording_accessed": {"evidenceVersioned"},
}


class LabelingStoreError(RuntimeError):
    """Stable domain error for the API layer to translate later."""

    def __init__(self, code, message, *, status=409, context=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.context = dict(context or {})


def _uuid(value, field):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise LabelingStoreError(
            "INVALID_IDENTIFIER", f"{field} debe ser UUID.", status=422
        ) from None


def _limit(value):
    if isinstance(value, bool):
        raise LabelingStoreError("INVALID_LIMIT", "limit no es válido.", status=422)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise LabelingStoreError("INVALID_LIMIT", "limit no es válido.", status=422) from None
    if parsed < 1 or parsed > MAX_LIST_LIMIT:
        raise LabelingStoreError(
            "INVALID_LIMIT", f"limit debe estar entre 1 y {MAX_LIST_LIMIT}.", status=422
        )
    return parsed


def _naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _database_now(cursor, provided=None):
    if provided is not None:
        if not isinstance(provided, datetime):
            raise TypeError("now debe ser datetime.")
        return _naive_utc(provided)
    cursor.execute("/* labeling:clock */ SELECT CAST(SYSUTCDATETIME() AS datetime2(3))")
    row = cursor.fetchone()
    if not row or not isinstance(row[0], datetime):
        raise LabelingStoreError("CLOCK_UNAVAILABLE", "No se pudo obtener la hora SQL.", status=503)
    return _naive_utc(row[0])


def _rows(cursor):
    columns = [str(column[0]) for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _single_dict(cursor):
    columns = [str(column[0]) for column in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def _json_object(raw, field):
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise LabelingStoreError(
            "CORRUPT_CASE", f"{field} no contiene JSON válido.", status=503
        ) from None
    if not isinstance(parsed, dict):
        raise LabelingStoreError(
            "CORRUPT_CASE", f"{field} no contiene un objeto JSON.", status=503
        )
    return parsed


def _pseudonym(prefix, value):
    digest = hashlib.sha256(f"voxready-labeling-v1:{value}".encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:8].upper()}"


def _wire_number(value):
    if value is None:
        return None
    parsed = Decimal(str(value))
    integral = parsed.to_integral_value()
    return int(integral) if parsed == integral else float(parsed)


def _lease_view(row, actor_id, now):
    status = str(row.get("status") or "")
    source_status = str(row.get("source_status") or "")
    owner = row.get("lock_owner_id")
    expires = _naive_utc(row.get("lock_expires_at"))
    if status == "reviewed" or source_status == "ambiguous":
        state = "not_claimable"
    elif owner is None:
        state = "available"
    elif expires is None or expires <= now:
        state = "expired"
    elif actor_id and str(owner).lower() == str(actor_id).lower():
        state = "owned"
    else:
        state = "locked_by_other"
    owner_code = None
    if state in {"owned", "locked_by_other"}:
        owner_code = _pseudonym("EXP", owner)
    return {
        "state": state,
        "ownerCode": owner_code,
        "expiresAt": expires if state in {"owned", "locked_by_other"} else None,
    }


def _review_summary(row, prefix):
    review_id = row.get(f"{prefix}_review_id")
    if not review_id:
        return None
    reviewer_id = row.get(f"{prefix}_reviewer_id")
    return {
        "reviewId": str(review_id),
        "reviewNo": int(row[f"{prefix}_review_no"]),
        "reviewerCode": _pseudonym("EXP", reviewer_id),
        "submittedAt": row[f"{prefix}_submitted_at"],
    }


def _normalize_areas(snapshot, source_status):
    areas = snapshot.get("areas")
    if not isinstance(areas, list):
        raise LabelingStoreError("CORRUPT_CASE", "El snapshot no contiene áreas.", status=503)
    normalized = []
    seen = set()
    for area in areas:
        if not isinstance(area, dict):
            raise LabelingStoreError("CORRUPT_CASE", "El snapshot contiene un área inválida.", status=503)
        key = str(area.get("areaKey") or "")
        if key not in AREA_LABELS or key in seen:
            raise LabelingStoreError("CORRUPT_CASE", "Las áreas del snapshot no son válidas.", status=503)
        seen.add(key)
        try:
            area_id = str(uuid.UUID(str(area.get("areaId"))))
        except (TypeError, ValueError, AttributeError):
            raise LabelingStoreError(
                "CORRUPT_CASE", "El snapshot contiene un identificador de área inválido.", status=503
            ) from None
        normalized.append(
            {
                "areaId": area_id,
                "areaKey": key,
                "label": area.get("label") or AREA_LABELS[key],
                "aiValue": _wire_number(area.get("aiValue", area.get("value"))),
                "editable": bool(area.get("editable", source_status != "ambiguous")),
            }
        )
    if seen != set(AREA_LABELS):
        raise LabelingStoreError("CORRUPT_CASE", "El snapshot no contiene cuatro áreas.", status=503)
    return sorted(normalized, key=lambda item: list(AREA_LABELS).index(item["areaKey"]))


def _normalize_metric_groups(snapshot):
    metrics = snapshot.get("metrics")
    if not isinstance(metrics, list):
        raise LabelingStoreError("CORRUPT_CASE", "El snapshot no contiene métricas.", status=503)
    groups = {}
    seen = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise LabelingStoreError("CORRUPT_CASE", "El snapshot contiene una métrica inválida.", status=503)
        key = str(metric.get("metricKey") or "")
        if not key or key in seen:
            raise LabelingStoreError("CORRUPT_CASE", "Las métricas del snapshot no son únicas.", status=503)
        seen.add(key)
        category = str(metric.get("categoryKey") or "")
        groups.setdefault(
            category,
            {
                "categoryKey": category,
                "label": CATEGORY_LABELS.get(category, category),
                "metrics": [],
            },
        )["metrics"].append(metric)
    for group in groups.values():
        group["metrics"].sort(key=lambda item: str(item["metricKey"]))
    return sorted(
        groups.values(),
        key=lambda item: (CATEGORY_ORDER.get(item["categoryKey"], 999), item["categoryKey"]),
    )


def _case_payload(row, actor_id, now, *, detail=False):
    snapshot = _json_object(row["ai_snapshot_json"], "ai_snapshot_json")
    reason = _json_object(row["reason_detail_json"], "reason_detail_json")
    if reason.get("kind") != row["queue_reason"]:
        raise LabelingStoreError(
            "CORRUPT_CASE", "El motivo de cola no coincide con su detalle.", status=503
        )
    areas = _normalize_areas(snapshot, row["source_status"])
    started = _naive_utc(row.get("started_at"))
    finished = _naive_utc(row.get("session_finished_at"))
    session_duration = None
    if started is not None and finished is not None and finished >= started:
        session_duration = round((finished - started).total_seconds(), 3)
    payload = {
        "caseId": str(row["case_id"]),
        "caseNumber": str(row["case_number"]),
        "status": row["status"],
        "queueReason": row["queue_reason"],
        "reasonDetail": reason,
        "client": {
            "code": _pseudonym("CLI", row["client_id"]),
            "displayName": row["client_name"],
        },
        "speakerCode": _pseudonym("VOC", row["speaker_id"]),
        "scenario": {"title": row["scenario_title"]},
        "session": {
            "startedAt": started,
            "finishedAt": finished,
            "durationSeconds": session_duration,
        },
        "report": {
            "reportId": str(row["report_id"]),
            "generatedAt": row["report_generated_at"],
            "overallScore": _wire_number(row["overall_score"]),
        },
        "criticalAreas": [
            {
                "areaKey": area["areaKey"],
                "label": area["label"],
                "value": area["aiValue"],
            }
            for area in areas
            if area["aiValue"] is not None and Decimal(str(area["aiValue"])) < 50
        ],
        "lease": _lease_view(row, actor_id, now),
        "latestReview": _review_summary(row, "latest"),
    }
    if detail:
        recording = snapshot.get("recording")
        if not isinstance(recording, dict):
            recording = {}
        payload.update(
            {
                "contentRevision": int(row["content_revision"]),
                "sourceStatus": row["source_status"],
                "sourceIssues": list(snapshot.get("sourceIssues") or []),
                "snapshotSchemaVersion": int(row["snapshot_schema_version"]),
                "rubric": {
                    "rubricVersionId": str(row["rubric_version_id"]),
                    "areas": areas,
                },
                "metricGroups": _normalize_metric_groups(snapshot),
                "recording": {
                    "availability": "available"
                    if row.get("recording_evidence_path")
                    else "unavailable",
                    "durationSeconds": _wire_number(
                        row.get("recording_duration_seconds")
                    ),
                },
                "currentReview": _review_summary(row, "current"),
            }
        )
    return payload


_CASE_SELECT = """
SELECT {top}
       lc.id AS case_id,lc.case_number,lc.client_id,lc.report_id,
       lc.rubric_version_id,lc.session_finished_at,lc.queue_reason,
       lc.reason_detail_json,lc.ai_snapshot_json,lc.snapshot_schema_version,
       lc.source_status,lc.status,lc.lock_owner_id,lc.lock_expires_at,
       lc.lease_generation,lc.content_revision,lc.recording_evidence_path,
       lc.recording_duration_seconds,c.name AS client_name,s.user_id AS speaker_id,
       s.started_at,sc.title AS scenario_title,r.generated_at AS report_generated_at,
       r.overall_score,
       latest.id AS latest_review_id,latest.review_no AS latest_review_no,
       latest.reviewer_id AS latest_reviewer_id,
       latest.submitted_at AS latest_submitted_at,
       current_review.id AS current_review_id,
       current_review.review_no AS current_review_no,
       current_review.reviewer_id AS current_reviewer_id,
       current_review.submitted_at AS current_submitted_at
  FROM dbo.labeling_case AS lc
  JOIN dbo.client AS c ON c.id=lc.client_id
  JOIN dbo.[session] AS s ON s.id=lc.session_id AND s.is_deleted=0
  JOIN dbo.scenario AS sc ON sc.id=s.scenario_id
  JOIN dbo.report AS r ON r.id=lc.report_id
  OUTER APPLY (
      SELECT TOP 1 lr.id,lr.review_no,lr.reviewer_id,lr.submitted_at
        FROM dbo.labeling_review AS lr
       WHERE lr.labeling_case_id=lc.id
       ORDER BY lr.review_no DESC,lr.id DESC
  ) AS latest
  OUTER APPLY (
      SELECT TOP 1 cr.id,cr.review_no,cr.reviewer_id,cr.submitted_at
        FROM dbo.labeling_review AS cr
       WHERE cr.labeling_case_id=lc.id AND cr.is_current=1
       ORDER BY cr.review_no DESC,cr.id DESC
  ) AS current_review
"""


def count_cases(cursor, *, status):
    """Shared queue/dashboard population; independent of the displayed page size."""
    if status not in {"pending", "reviewed"}:
        raise LabelingStoreError("INVALID_STATUS", "status no es válido.", status=422)
    cursor.execute(
        """/* labeling:list:count */
        SELECT COUNT_BIG(*)
          FROM dbo.labeling_case AS lc
          JOIN dbo.[session] AS s ON s.id=lc.session_id AND s.is_deleted=0
         WHERE lc.status=?""",
        status,
    )
    total_row = cursor.fetchone()
    return int(total_row[0] or 0) if total_row else 0


def list_cases(cursor, *, status, limit=10, actor_id=None, now=None):
    """List at most ten pending or reviewed cases with stable ordering."""
    if status not in {"pending", "reviewed"}:
        raise LabelingStoreError("INVALID_STATUS", "status no es válido.", status=422)
    limit = _limit(limit)
    actor = _uuid(actor_id, "actorId") if actor_id else None
    clock = _database_now(cursor, now)
    total = count_cases(cursor, status=status)
    order = (
        "lc.session_finished_at DESC,lc.id DESC"
        if status == "pending"
        else "latest.submitted_at DESC,latest.id DESC"
    )
    sql = (
        f"/* labeling:list:{status} */ "
        + _CASE_SELECT.format(top="TOP (?)")
        + f" WHERE lc.status=? ORDER BY {order}"
    )
    cursor.execute(sql, limit, status)
    items = [_case_payload(row, actor, clock) for row in _rows(cursor)]
    if status == "reviewed" and any(item["latestReview"] is None for item in items):
        raise LabelingStoreError(
            "CORRUPT_CASE", "Existe un caso revisado sin revisión.", status=503
        )
    return {"items": items, "total": total, "limit": limit}


def get_case_detail(cursor, case_id, *, actor_id=None, now=None):
    """Return normalized case detail without PII or internal media paths."""
    case_id = _uuid(case_id, "caseId")
    actor = _uuid(actor_id, "actorId") if actor_id else None
    clock = _database_now(cursor, now)
    sql = (
        "/* labeling:detail */ "
        + _CASE_SELECT.format(top="")
        + " WHERE lc.id=?"
    )
    cursor.execute(sql, case_id)
    row = _single_dict(cursor)
    if not row:
        raise LabelingStoreError("CASE_NOT_FOUND", "Caso no encontrado.", status=404)
    return _case_payload(row, actor, clock, detail=True)


def _begin(cursor):
    cursor.execute("/* labeling:transaction */ IF @@TRANCOUNT=0 BEGIN TRANSACTION;")


def _lock_case(cursor, case_id):
    cursor.execute(
        """/* labeling:case:lock */
        SELECT id,client_id,status,source_status,lock_owner_id,lock_token_hash,
               lock_expires_at,lease_generation,content_revision,
               ai_snapshot_json,rubric_version_id
          FROM dbo.labeling_case WITH (UPDLOCK,HOLDLOCK)
         WHERE id=?""",
        case_id,
    )
    row = cursor.fetchone()
    if not row:
        raise LabelingStoreError("CASE_NOT_FOUND", "Caso no encontrado.", status=404)
    keys = (
        "id",
        "client_id",
        "status",
        "source_status",
        "lock_owner_id",
        "lock_token_hash",
        "lock_expires_at",
        "lease_generation",
        "content_revision",
        "ai_snapshot_json",
        "rubric_version_id",
    )
    return dict(zip(keys, row))


def _token_hash(token):
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
        raise LabelingStoreError("INVALID_LEASE", "Token de reserva inválido.", status=409)
    return hashlib.sha256(token.encode("utf-8")).digest()


def _matches_hash(actual, expected):
    if actual is None:
        return False
    return hmac.compare_digest(bytes(actual), expected)


def _audit(cursor, event_type, *, client_id, actor_id, case_id, detail):
    allowed = AUDIT_DETAIL_KEYS.get(event_type)
    if allowed is None or set(detail) - allowed:
        raise ValueError("Detalle de auditoría no permitido.")
    if any(isinstance(value, (dict, list, bytes, bytearray)) for value in detail.values()):
        raise ValueError("Detalle de auditoría no es escalar.")
    cursor.execute(
        """/* labeling:audit */
        INSERT INTO dbo.audit_event (
            id,client_id,actor_user_id,event_type,entity_type,entity_id,
            detail_json,occurred_at,created_at,updated_at
        ) VALUES (NEWID(),?,?,?,'labeling_case',?,?,SYSUTCDATETIME(),
                  SYSUTCDATETIME(),SYSUTCDATETIME())""",
        client_id,
        actor_id,
        event_type,
        case_id,
        json.dumps(detail, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def acquire_lease(
    cursor,
    case_id,
    reviewer_id,
    *,
    lease_token=None,
    lease_generation=None,
    allow_reviewed=False,
    now=None,
):
    """Acquire a new tab-specific lease or renew the exact active lease."""
    case_id = _uuid(case_id, "caseId")
    reviewer_id = _uuid(reviewer_id, "reviewerId")
    _begin(cursor)
    clock = _database_now(cursor, now)
    case = _lock_case(cursor, case_id)
    if case["source_status"] == "ambiguous" or (
        case["status"] == "reviewed" and not allow_reviewed
    ):
        raise LabelingStoreError(
            "CASE_NOT_CLAIMABLE", "El caso no admite una reserva.", status=409
        )

    owner = case["lock_owner_id"]
    expires = _naive_utc(case["lock_expires_at"])
    active = owner is not None and expires is not None and expires > clock
    expiry = clock + timedelta(minutes=LEASE_MINUTES)

    if active:
        if str(owner).lower() != reviewer_id.lower():
            raise LabelingStoreError(
                "LEASE_CONFLICT",
                "Otro experto posee la reserva activa.",
                status=409,
                context={"expiresAt": expires},
            )
        if lease_token is None or lease_generation is None:
            raise LabelingStoreError(
                "LEASE_CONFLICT",
                "La reserva pertenece a otra pestaña o adquisición.",
                status=409,
                context={"expiresAt": expires},
            )
        supplied_hash = _token_hash(lease_token)
        try:
            supplied_generation = int(lease_generation)
        except (TypeError, ValueError):
            raise LabelingStoreError("STALE_LEASE", "La reserva quedó obsoleta.", status=409) from None
        if supplied_generation != int(case["lease_generation"]) or not _matches_hash(
            case["lock_token_hash"], supplied_hash
        ):
            raise LabelingStoreError("STALE_LEASE", "La reserva quedó obsoleta.", status=409)
        cursor.execute(
            """/* labeling:lease:renew */
            UPDATE dbo.labeling_case
               SET lock_expires_at=?,updated_at=SYSUTCDATETIME()
             WHERE id=?""",
            expiry,
            case_id,
        )
        token = lease_token
        generation = int(case["lease_generation"])
    else:
        if lease_token is not None or lease_generation is not None:
            raise LabelingStoreError("STALE_LEASE", "La reserva quedó obsoleta.", status=409)
        token = secrets.token_urlsafe(32)
        generation = int(case["lease_generation"] or 0) + 1
        cursor.execute(
            """/* labeling:lease:claim */
            UPDATE dbo.labeling_case
               SET lock_owner_id=?,lock_token_hash=?,lock_acquired_at=?,
                   lock_expires_at=?,lease_generation=?,updated_at=SYSUTCDATETIME()
             WHERE id=?""",
            reviewer_id,
            _token_hash(token),
            clock,
            expiry,
            generation,
            case_id,
        )
        _audit(
            cursor,
            "labeling_case_claimed",
            client_id=case["client_id"],
            actor_id=reviewer_id,
            case_id=case_id,
            detail={
                "leaseGeneration": generation,
                "expiredPreviousLease": owner is not None,
            },
        )
    return {
        "caseId": case_id,
        "leaseToken": token,
        "leaseGeneration": generation,
        "contentRevision": int(case["content_revision"]),
        "expiresAt": expiry,
        "serverTime": clock,
        "readOnly": False,
    }


def release_lease(
    cursor,
    case_id,
    reviewer_id,
    *,
    lease_token,
    lease_generation,
    now=None,
):
    """Release the exact lease; repeat after release is an idempotent no-op."""
    case_id = _uuid(case_id, "caseId")
    reviewer_id = _uuid(reviewer_id, "reviewerId")
    supplied_hash = _token_hash(lease_token)
    try:
        generation = int(lease_generation)
    except (TypeError, ValueError):
        raise LabelingStoreError("INVALID_LEASE", "Generación inválida.", status=409) from None
    _begin(cursor)
    _database_now(cursor, now)
    case = _lock_case(cursor, case_id)
    current_generation = int(case["lease_generation"])
    if case["lock_owner_id"] is None:
        if generation == current_generation:
            return {"released": True, "idempotent": True}
        raise LabelingStoreError("STALE_LEASE", "La reserva quedó obsoleta.", status=409)
    if (
        generation != current_generation
        or str(case["lock_owner_id"]).lower() != reviewer_id.lower()
        or not _matches_hash(case["lock_token_hash"], supplied_hash)
    ):
        raise LabelingStoreError("STALE_LEASE", "La reserva quedó obsoleta.", status=409)
    cursor.execute(
        """/* labeling:lease:release */
        UPDATE dbo.labeling_case
           SET lock_owner_id=NULL,lock_token_hash=NULL,lock_acquired_at=NULL,
               lock_expires_at=NULL,updated_at=SYSUTCDATETIME()
         WHERE id=?""",
        case_id,
    )
    _audit(
        cursor,
        "labeling_case_released",
        client_id=case["client_id"],
        actor_id=reviewer_id,
        case_id=case_id,
        detail={"leaseGeneration": generation},
    )
    return {"released": True, "idempotent": False}


def _field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _text(value, field, *, required=False, maximum=2000):
    normalized = " ".join(str(value or "").split())
    if required and not normalized:
        raise LabelingStoreError(
            "INVALID_REVIEW", f"{field} es obligatorio.", status=422
        )
    if len(normalized) > maximum:
        raise LabelingStoreError(
            "INVALID_REVIEW", f"{field} supera {maximum} caracteres.", status=422
        )
    return normalized or None


def _decimal(value, field):
    if value is None or isinstance(value, bool):
        raise LabelingStoreError("INVALID_REVIEW", f"{field} no es numérico.", status=422)
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise LabelingStoreError("INVALID_REVIEW", f"{field} no es numérico.", status=422) from None
    if not parsed.is_finite():
        raise LabelingStoreError("INVALID_REVIEW", f"{field} no es finito.", status=422)
    return parsed


def _canonical_decimal(value):
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _prepare_review(snapshot, source_status, request):
    if source_status == "ambiguous":
        raise LabelingStoreError(
            "SOURCE_NOT_REVIEWABLE", "La fuente del caso es ambigua.", status=409
        )
    overall_comment = _text(
        _field(request, "overallComment"),
        "overallComment",
        required=True,
        maximum=4000,
    )
    expected_revision = _field(request, "expectedContentRevision")
    lease_generation = _field(request, "leaseGeneration")
    try:
        expected_revision = int(expected_revision)
        lease_generation = int(lease_generation)
    except (TypeError, ValueError):
        raise LabelingStoreError(
            "INVALID_REVIEW", "Las revisiones esperadas no son válidas.", status=422
        ) from None
    idempotency_key = _uuid(_field(request, "idempotencyKey"), "idempotencyKey")
    supersedes_raw = _field(request, "supersedesReviewId")
    supersedes = _uuid(supersedes_raw, "supersedesReviewId") if supersedes_raw else None

    areas = {item["areaId"].lower(): item for item in _normalize_areas(snapshot, source_status) if item["editable"]}
    received_areas = {}
    for correction in list(_field(request, "rubricCorrections", []) or []):
        area_id = _uuid(_field(correction, "areaId"), "areaId").lower()
        if area_id in received_areas or area_id not in areas:
            raise LabelingStoreError(
                "INVALID_REVIEW", "Área duplicada o ajena al snapshot.", status=422
            )
        corrected = _decimal(_field(correction, "correctedValue"), "correctedValue")
        if corrected < 0 or corrected > 100 or corrected.normalize().as_tuple().exponent < -2:
            raise LabelingStoreError(
                "INVALID_REVIEW", "El puntaje de área debe estar entre 0 y 100 con hasta dos decimales.", status=422
            )
        ai_value = _decimal(areas[area_id]["aiValue"], "aiValue")
        comment = _text(_field(correction, "comment"), "comment")
        if corrected != ai_value and not comment:
            raise LabelingStoreError(
                "COMMENT_REQUIRED", "Cada cambio de área exige comentario.", status=422
            )
        received_areas[area_id] = {
            "areaId": area_id,
            "areaKey": areas[area_id]["areaKey"],
            "aiValue": ai_value,
            "correctedValue": corrected,
            "comment": comment,
        }
    if set(received_areas) != set(areas):
        raise LabelingStoreError(
            "INCOMPLETE_RUBRIC", "La revisión debe incluir todas las áreas editables.", status=422
        )

    metric_catalog = {}
    for metric in snapshot.get("metrics") or []:
        if isinstance(metric, dict):
            metric_catalog[str(metric.get("metricKey"))] = metric
    received_metrics = {}
    for correction in list(_field(request, "metricCorrections", []) or []):
        metric_key = str(_field(correction, "metricKey") or "")
        metric = metric_catalog.get(metric_key)
        if metric_key in received_metrics or not metric:
            raise LabelingStoreError(
                "INVALID_REVIEW", "Métrica duplicada o ajena al snapshot.", status=422
            )
        if metric.get("availability") != "available" or not metric.get("editable"):
            raise LabelingStoreError(
                "METRIC_NOT_EDITABLE", "La métrica no es editable.", status=422
            )
        corrected = _decimal(_field(correction, "correctedValue"), "correctedValue")
        observation = metric.get("observation") or {}
        minimum = observation.get("technicalMin")
        maximum = observation.get("technicalMax")
        if minimum is not None and corrected < _decimal(minimum, "technicalMin"):
            raise LabelingStoreError("INVALID_REVIEW", "La métrica está bajo su mínimo técnico.", status=422)
        if maximum is not None and corrected > _decimal(maximum, "technicalMax"):
            raise LabelingStoreError("INVALID_REVIEW", "La métrica supera su máximo técnico.", status=422)
        if observation.get("valueType") == "integer" and corrected != corrected.to_integral_value():
            raise LabelingStoreError("INVALID_REVIEW", "La métrica exige un entero.", status=422)
        precision = int(metric.get("precision") or 0)
        if corrected.normalize().as_tuple().exponent < -precision:
            raise LabelingStoreError(
                "INVALID_REVIEW", "La métrica supera la precisión permitida.", status=422
            )
        ai_value = _decimal(metric.get("aiValue"), "aiValue")
        comment = _text(_field(correction, "comment"), "comment")
        if corrected != ai_value and not comment:
            raise LabelingStoreError(
                "COMMENT_REQUIRED", "Cada cambio de métrica exige comentario.", status=422
            )
        unit = str(metric.get("unit") or "").strip()
        if not unit:
            raise LabelingStoreError("CORRUPT_CASE", "La métrica no declara unidad.", status=503)
        received_metrics[metric_key] = {
            "metricKey": metric_key,
            "mappingVersion": int(metric.get("mappingVersion") or 1),
            "unit": unit,
            "aiValue": ai_value,
            "correctedValue": corrected,
            "comment": comment,
        }

    canonical = {
        "expectedContentRevision": expected_revision,
        "leaseGeneration": lease_generation,
        "supersedesReviewId": supersedes,
        "overallComment": overall_comment,
        "rubricCorrections": [
            {
                "areaId": item["areaId"],
                "correctedValue": _canonical_decimal(item["correctedValue"]),
                "comment": item["comment"],
            }
            for item in sorted(received_areas.values(), key=lambda value: value["areaId"])
        ],
        "metricCorrections": [
            {
                "metricKey": item["metricKey"],
                "correctedValue": _canonical_decimal(item["correctedValue"]),
                "comment": item["comment"],
            }
            for item in sorted(received_metrics.values(), key=lambda value: value["metricKey"])
        ],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()
    return {
        "overallComment": overall_comment,
        "expectedContentRevision": expected_revision,
        "leaseGeneration": lease_generation,
        "leaseTokenHash": _token_hash(_field(request, "leaseToken")),
        "idempotencyKey": idempotency_key,
        "supersedesReviewId": supersedes,
        "requestHash": digest,
        "areas": list(received_areas.values()),
        "metrics": list(received_metrics.values()),
    }


def _review_response(cursor, case_id, review_id, content_revision=None):
    cursor.execute(
        """/* labeling:review:response */
        SELECT r.id,r.labeling_case_id,r.reviewer_id,r.review_no,r.overall_comment,
               r.supersedes_review_id,r.is_current,r.submitted_at,lc.content_revision
          FROM dbo.labeling_review AS r
          JOIN dbo.labeling_case AS lc ON lc.id=r.labeling_case_id
         WHERE r.id=? AND r.labeling_case_id=?""",
        review_id,
        case_id,
    )
    row = cursor.fetchone()
    if not row:
        raise LabelingStoreError("CORRUPT_REVIEW", "La revisión no puede leerse.", status=503)
    cursor.execute(
        """/* labeling:review:areas */
        SELECT ra.area_key,c.ai_value,c.corrected_value,c.comment
          FROM dbo.labeling_rubric_correction AS c
          JOIN dbo.rubric_area AS ra ON ra.id=c.rubric_area_id
         WHERE c.review_id=? ORDER BY ra.area_key""",
        review_id,
    )
    area_rows = cursor.fetchall()
    cursor.execute(
        """/* labeling:review:metrics */
        SELECT metric_key,ai_value,corrected_value,unit,comment
          FROM dbo.labeling_metric_correction
         WHERE review_id=? ORDER BY metric_key""",
        review_id,
    )
    metric_rows = cursor.fetchall()
    return {
        "reviewId": str(row[0]),
        "caseId": str(row[1]),
        "reviewNo": int(row[3]),
        "reviewerCode": _pseudonym("EXP", row[2]),
        "isCurrent": bool(row[6]),
        "supersedesReviewId": str(row[5]) if row[5] else None,
        "submittedAt": row[7],
        "contentRevision": int(content_revision if content_revision is not None else row[8]),
        "overallComment": row[4],
        "rubricCorrections": [
            {
                "areaKey": item[0],
                "aiValue": _wire_number(item[1]),
                "correctedValue": _wire_number(item[2]),
                "comment": item[3],
            }
            for item in area_rows
        ],
        "metricCorrections": [
            {
                "metricKey": item[0],
                "aiValue": _wire_number(item[1]),
                "correctedValue": _wire_number(item[2]),
                "unit": item[3],
                "comment": item[4],
            }
            for item in metric_rows
        ],
    }


def submit_review(cursor, case_id, reviewer_id, request, *, now=None):
    """Insert an immutable review and corrections in the caller transaction."""
    case_id = _uuid(case_id, "caseId")
    reviewer_id = _uuid(reviewer_id, "reviewerId")
    _begin(cursor)
    clock = _database_now(cursor, now)
    case = _lock_case(cursor, case_id)
    snapshot = _json_object(case["ai_snapshot_json"], "ai_snapshot_json")
    prepared = _prepare_review(snapshot, case["source_status"], request)

    cursor.execute(
        """/* labeling:review:idempotency */
        SELECT id,request_hash,reviewer_id FROM dbo.labeling_review WITH (HOLDLOCK)
         WHERE labeling_case_id=? AND idempotency_key=?""",
        case_id,
        prepared["idempotencyKey"],
    )
    existing = cursor.fetchone()
    if existing:
        if (
            str(existing[2]).lower() != reviewer_id.lower()
            or not hmac.compare_digest(bytes(existing[1]), prepared["requestHash"])
        ):
            raise LabelingStoreError(
                "IDEMPOTENCY_CONFLICT",
                "La clave de idempotencia pertenece a otra solicitud.",
                status=409,
            )
        return {
            "replayed": True,
            "review": _review_response(cursor, case_id, str(existing[0])),
        }

    expires = _naive_utc(case["lock_expires_at"])
    if (
        case["lock_owner_id"] is None
        or str(case["lock_owner_id"]).lower() != reviewer_id.lower()
        or expires is None
        or expires <= clock
        or int(case["lease_generation"]) != prepared["leaseGeneration"]
        or not _matches_hash(case["lock_token_hash"], prepared["leaseTokenHash"])
    ):
        raise LabelingStoreError("STALE_LEASE", "La reserva no está vigente.", status=409)
    if int(case["content_revision"]) != prepared["expectedContentRevision"]:
        raise LabelingStoreError(
            "CONTENT_REVISION_CONFLICT", "El caso cambió desde que fue abierto.", status=409
        )

    cursor.execute(
        """/* labeling:review:current */
        SELECT TOP 1 id,review_no FROM dbo.labeling_review WITH (UPDLOCK,HOLDLOCK)
         WHERE labeling_case_id=? AND is_current=1
         ORDER BY review_no DESC,id DESC""",
        case_id,
    )
    current = cursor.fetchone()
    if case["status"] == "reviewed" and current is None:
        raise LabelingStoreError(
            "CORRUPT_CASE", "El caso revisado no tiene revisión vigente.", status=503
        )
    if case["status"] == "pending" and current is not None:
        raise LabelingStoreError(
            "CORRUPT_CASE", "El caso pendiente ya tiene revisión vigente.", status=503
        )
    if current is None and prepared["supersedesReviewId"] is not None:
        raise LabelingStoreError(
            "REVIEW_BASE_CONFLICT", "La primera revisión no puede sustituir otra.", status=409
        )
    if current is not None and str(current[0]).lower() != str(
        prepared["supersedesReviewId"] or ""
    ).lower():
        raise LabelingStoreError(
            "REVIEW_BASE_CONFLICT", "La revisión base ya no es vigente.", status=409
        )
    review_no = int(current[1]) + 1 if current else 1
    review_id = str(uuid.uuid4())
    if current:
        cursor.execute(
            "/* labeling:review:supersede */ UPDATE dbo.labeling_review SET is_current=0 WHERE id=? AND is_current=1",
            current[0],
        )
    cursor.execute(
        """/* labeling:review:insert */
        INSERT INTO dbo.labeling_review (
            id,labeling_case_id,reviewer_id,review_no,overall_comment,
            supersedes_review_id,is_current,idempotency_key,request_hash,
            submitted_at,created_at
        ) VALUES (?,?,?,?,?,?,1,?,?,?,SYSUTCDATETIME())""",
        review_id,
        case_id,
        reviewer_id,
        review_no,
        prepared["overallComment"],
        prepared["supersedesReviewId"],
        prepared["idempotencyKey"],
        prepared["requestHash"],
        clock,
    )
    for area in prepared["areas"]:
        cursor.execute(
            """/* labeling:review:area:insert */
            INSERT INTO dbo.labeling_rubric_correction (
                review_id,rubric_area_id,ai_value,corrected_value,comment,created_at
            ) VALUES (?,?,?,?,?,SYSUTCDATETIME())""",
            review_id,
            area["areaId"],
            area["aiValue"],
            area["correctedValue"],
            area["comment"],
        )
    for metric in prepared["metrics"]:
        cursor.execute(
            """/* labeling:review:metric:insert */
            INSERT INTO dbo.labeling_metric_correction (
                review_id,metric_key,mapping_version,unit,ai_value,
                corrected_value,comment,created_at
            ) VALUES (?,?,?,?,?,?,?,SYSUTCDATETIME())""",
            review_id,
            metric["metricKey"],
            metric["mappingVersion"],
            metric["unit"],
            metric["aiValue"],
            metric["correctedValue"],
            metric["comment"],
        )
    new_revision = int(case["content_revision"]) + 1
    cursor.execute(
        """/* labeling:review:case:update */
        UPDATE dbo.labeling_case
           SET status='reviewed',resolved_by=?,resolved_at=?,content_revision=?,
               lock_owner_id=NULL,lock_token_hash=NULL,lock_acquired_at=NULL,
               lock_expires_at=NULL,updated_at=SYSUTCDATETIME()
         WHERE id=?""",
        reviewer_id,
        clock,
        new_revision,
        case_id,
    )
    changed_count = sum(
        item["aiValue"] != item["correctedValue"]
        for item in prepared["areas"] + prepared["metrics"]
    )
    _audit(
        cursor,
        "labeling_case_reviewed",
        client_id=case["client_id"],
        actor_id=reviewer_id,
        case_id=case_id,
        detail={
            "reviewId": review_id,
            "reviewNo": review_no,
            "rubricCorrectionCount": len(prepared["areas"]),
            "metricCorrectionCount": len(prepared["metrics"]),
            "changedCount": changed_count,
        },
    )
    return {
        "replayed": False,
        "review": _review_response(cursor, case_id, review_id, new_revision),
    }


def list_reviews(cursor, case_id):
    """Return immutable review history in descending review number."""
    case_id = _uuid(case_id, "caseId")
    cursor.execute(
        """/* labeling:reviews:headers */
        SELECT r.id,r.labeling_case_id,r.reviewer_id,r.review_no,r.overall_comment,
               r.supersedes_review_id,r.is_current,r.submitted_at,lc.content_revision
          FROM dbo.labeling_review AS r
          JOIN dbo.labeling_case AS lc ON lc.id=r.labeling_case_id
         WHERE r.labeling_case_id=?
         ORDER BY r.review_no DESC,r.id DESC""",
        case_id,
    )
    headers = cursor.fetchall()
    if not headers:
        return {"items": [], "total": 0}
    cursor.execute(
        """/* labeling:reviews:areas */
        SELECT c.review_id,ra.area_key,c.ai_value,c.corrected_value,c.comment
          FROM dbo.labeling_rubric_correction AS c
          JOIN dbo.labeling_review AS r ON r.id=c.review_id
          JOIN dbo.rubric_area AS ra ON ra.id=c.rubric_area_id
         WHERE r.labeling_case_id=?
         ORDER BY r.review_no DESC,ra.area_key""",
        case_id,
    )
    areas_by_review = {}
    for item in cursor.fetchall():
        areas_by_review.setdefault(str(item[0]), []).append(
            {
                "areaKey": item[1],
                "aiValue": _wire_number(item[2]),
                "correctedValue": _wire_number(item[3]),
                "comment": item[4],
            }
        )
    cursor.execute(
        """/* labeling:reviews:metrics */
        SELECT c.review_id,c.metric_key,c.ai_value,c.corrected_value,c.unit,c.comment
          FROM dbo.labeling_metric_correction AS c
          JOIN dbo.labeling_review AS r ON r.id=c.review_id
         WHERE r.labeling_case_id=?
         ORDER BY r.review_no DESC,c.metric_key""",
        case_id,
    )
    metrics_by_review = {}
    for item in cursor.fetchall():
        metrics_by_review.setdefault(str(item[0]), []).append(
            {
                "metricKey": item[1],
                "aiValue": _wire_number(item[2]),
                "correctedValue": _wire_number(item[3]),
                "unit": item[4],
                "comment": item[5],
            }
        )
    items = []
    for row in headers:
        review_id = str(row[0])
        items.append(
            {
                "reviewId": review_id,
                "caseId": str(row[1]),
                "reviewNo": int(row[3]),
                "reviewerCode": _pseudonym("EXP", row[2]),
                "isCurrent": bool(row[6]),
                "supersedesReviewId": str(row[5]) if row[5] else None,
                "submittedAt": row[7],
                "contentRevision": int(row[8]),
                "overallComment": row[4],
                "rubricCorrections": areas_by_review.get(review_id, []),
                "metricCorrections": metrics_by_review.get(review_id, []),
            }
        )
    return {"items": items, "total": len(items)}


def _period_clause(period_from, period_to, alias="r"):
    clauses = []
    params = []
    if period_from is not None:
        clauses.append(f"{alias}.submitted_at>=?")
        params.append(_naive_utc(period_from))
    if period_to is not None:
        clauses.append(f"{alias}.submitted_at<?")
        params.append(_naive_utc(period_to))
    return clauses, params


def _period_value(value, field):
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise LabelingStoreError(
            "INVALID_PERIOD", f"{field} debe ser fecha y hora.", status=422
        )
    return value


def _aggregate_item(row, identity):
    result = {key: row[key] for key in identity}
    result.update(
        {
            "sampleCount": int(row["sample_count"]),
            "meanAiValue": _wire_number(row["mean_ai_value"]),
            "meanCorrectedValue": _wire_number(row["mean_corrected_value"]),
            "meanDelta": _wire_number(row["mean_delta"]),
            "meanAbsoluteError": _wire_number(row["mean_absolute_error"]),
            "changedCount": int(row["changed_count"]),
            "increasedCount": int(row["increased_count"]),
            "decreasedCount": int(row["decreased_count"]),
            "unchangedCount": int(row["unchanged_count"]),
        }
    )
    for key, value in list(result.items()):
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
    return result


def quality_summary(
    cursor,
    *,
    period_from=None,
    period_to=None,
    current_reviews_only=True,
):
    """Aggregate agreement without mixing rubric versions or metric units."""
    period_from = _period_value(period_from, "from")
    period_to = _period_value(period_to, "to")
    if not isinstance(current_reviews_only, bool):
        raise LabelingStoreError(
            "INVALID_ARGUMENT", "currentReviewsOnly debe ser booleano.", status=422
        )
    if period_from and period_to and _naive_utc(period_from) >= _naive_utc(period_to):
        raise LabelingStoreError("INVALID_PERIOD", "El período no es válido.", status=422)
    period_clauses, period_params = _period_clause(period_from, period_to)
    filters = list(period_clauses)
    if current_reviews_only:
        filters.append("r.is_current=1")
    where = " AND ".join(filters) if filters else "1=1"
    cursor.execute(
        f"""/* labeling:quality:cases */
        SELECT COUNT_BIG(DISTINCT r.labeling_case_id)
          FROM dbo.labeling_review AS r WHERE {where}""",
        *period_params,
    )
    reviewed_cases = int((cursor.fetchone() or (0,))[0] or 0)
    aggregate_columns = """
        COUNT_BIG(*) AS sample_count,
        AVG(CAST(c.ai_value AS DECIMAL(19,6))) AS mean_ai_value,
        AVG(CAST(c.corrected_value AS DECIMAL(19,6))) AS mean_corrected_value,
        AVG(CAST(c.corrected_value-c.ai_value AS DECIMAL(19,6))) AS mean_delta,
        AVG(CAST(ABS(c.corrected_value-c.ai_value) AS DECIMAL(19,6))) AS mean_absolute_error,
        SUM(CASE WHEN c.corrected_value<>c.ai_value THEN 1 ELSE 0 END) AS changed_count,
        SUM(CASE WHEN c.corrected_value>c.ai_value THEN 1 ELSE 0 END) AS increased_count,
        SUM(CASE WHEN c.corrected_value<c.ai_value THEN 1 ELSE 0 END) AS decreased_count,
        SUM(CASE WHEN c.corrected_value=c.ai_value THEN 1 ELSE 0 END) AS unchanged_count
    """
    cursor.execute(
        f"""/* labeling:quality:areas */
        SELECT lc.rubric_version_id AS rubricVersionId,ra.area_key AS areaKey,
               {aggregate_columns}
          FROM dbo.labeling_rubric_correction AS c
          JOIN dbo.labeling_review AS r ON r.id=c.review_id
          JOIN dbo.labeling_case AS lc ON lc.id=r.labeling_case_id
          JOIN dbo.rubric_area AS ra ON ra.id=c.rubric_area_id
         WHERE {where}
         GROUP BY lc.rubric_version_id,ra.area_key
         ORDER BY lc.rubric_version_id,ra.area_key""",
        *period_params,
    )
    areas = [_aggregate_item(row, ("rubricVersionId", "areaKey")) for row in _rows(cursor)]
    cursor.execute(
        f"""/* labeling:quality:metrics */
        SELECT c.metric_key AS metricKey,c.mapping_version AS mappingVersion,
               c.unit AS unit,{aggregate_columns}
          FROM dbo.labeling_metric_correction AS c
          JOIN dbo.labeling_review AS r ON r.id=c.review_id
         WHERE {where}
         GROUP BY c.metric_key,c.mapping_version,c.unit
         ORDER BY c.metric_key,c.mapping_version,c.unit""",
        *period_params,
    )
    metrics = [
        _aggregate_item(row, ("metricKey", "mappingVersion", "unit"))
        for row in _rows(cursor)
    ]
    cursor.execute(
        f"""/* labeling:quality:categories */
        SELECT d.category AS categoryKey,COUNT_BIG(*) AS reviewed_metric_count,
               SUM(CASE WHEN c.corrected_value<>c.ai_value THEN 1 ELSE 0 END) AS changed_count
          FROM dbo.labeling_metric_correction AS c
          JOIN dbo.labeling_review AS r ON r.id=c.review_id
          JOIN dbo.rubric_metric_definition AS d ON d.metric_key=c.metric_key
         WHERE {where}
         GROUP BY d.category ORDER BY d.category""",
        *period_params,
    )
    categories = [
        {
            "categoryKey": row[0],
            "reviewedMetricCount": int(row[1]),
            "changedCount": int(row[2]),
        }
        for row in cursor.fetchall()
    ]
    return {
        "period": {"from": period_from, "to": period_to},
        "currentReviewsOnly": bool(current_reviews_only),
        "reviewedCases": reviewed_cases,
        "rubricAreas": areas,
        "metrics": metrics,
        "categories": categories,
    }


def audit_recording_access(cursor, *, case_id, client_id, actor_id, version_id=None):
    """Record issuance of recording access without persisting URL or blob path."""
    case_id = _uuid(case_id, "caseId")
    client_id = _uuid(client_id, "clientId")
    actor_id = _uuid(actor_id, "actorId")
    _audit(
        cursor,
        "labeling_recording_accessed",
        client_id=client_id,
        actor_id=actor_id,
        case_id=case_id,
        detail={"evidenceVersioned": bool(version_id)},
    )
