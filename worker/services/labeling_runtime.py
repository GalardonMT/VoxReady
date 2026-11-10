"""Create labeling cases from exact report, pipeline and media evidence."""

import json
import os
import uuid
from decimal import Decimal, InvalidOperation


REQUIRED_AREA_KEYS = frozenset(("expression", "voice", "coherence", "empathy"))
OBSERVATION_SPECS = {
    "voice.wpm": ("voice", ("wpm_global",), 1, "identity", 0, None),
    "voice.filler_density": ("voice", ("densidad_muletillas_pct",), 2, "identity", 0, 100),
    "voice.prolonged_pause": ("voice", ("pausas_prolongadas",), 0, "identity", 0, None),
    "voice.hesitation_pause": ("voice", ("pausas_vacilacion",), 0, "identity", 0, None),
    "voice.phonation_ratio": ("voice", ("ratio_fonacion",), 1, "ratio_0_1_to_percent", 0, 100),
    "voice.asr_confidence": ("voice", ("__words_confidence__",), 1, "ratio_0_1_to_percent", 0, 100),
    "vision.eye_contact": ("vision", ("summary.eye_contact_pct", "eye_contact_pct", "contacto_visual_porcentaje"), 2, "identity", 0, 100),
    "vision.posture": ("vision", ("summary.shoulder_stability_score", "shoulder_stability_score", "posture_stability_score"), 2, "identity", 0, 100),
    "vision.sway_tolerance": ("vision", ("summary.body_sway_std", "body_sway_std"), 4, "identity", 0, None),
}
METRIC_KIND = {
    "content.red_line_cap": "configuration",
    "empathy.victim_recog": "observation",
    "gov.confidence_min": "configuration",
    "gov.borderline_delta": "configuration",
    "gov.disparity_delta": "configuration",
    "gov.random_sample": "configuration",
    "gov.agreement_target": "aggregate_target",
}
EXPECTED_METRIC_KEYS = frozenset(OBSERVATION_SPECS) | frozenset(METRIC_KIND)


class LabelingRuntimeError(RuntimeError):
    """The report cannot safely become a labeling case."""


def runtime_enabled():
    return os.getenv("LABELING_RUNTIME_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _number(value, label):
    if value is None or isinstance(value, bool):
        raise LabelingRuntimeError(f"{label} no es numérico.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise LabelingRuntimeError(f"{label} no es numérico.") from None
    if not parsed.is_finite():
        raise LabelingRuntimeError(f"{label} no es finito.")
    return parsed


def _wire_number(value, precision=None):
    parsed = _number(value, "value")
    if precision is not None:
        parsed = parsed.quantize(Decimal(1).scaleb(-precision))
    integral = parsed.to_integral_value()
    return int(integral) if parsed == integral else float(parsed)


def _path(source, path):
    current = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def _word_confidence(source):
    words = source.get("words") if isinstance(source, dict) else None
    if not isinstance(words, list) or not words:
        return None, False
    values = []
    for word in words:
        if not isinstance(word, dict) or word.get("confidence") is None:
            return None, False
        confidence = _number(word["confidence"], "words.confidence")
        if confidence < 0 or confidence > 1:
            return None, False
        values.append(confidence)
    return sum(values) / len(values), True


def _observation(metric_key, pipeline_results):
    pipeline, paths, precision, conversion, minimum, maximum = OBSERVATION_SPECS[
        metric_key
    ]
    source = pipeline_results.get(pipeline)
    if not isinstance(source, dict):
        return None, "unknown", "PIPELINE_RESULT_MISSING", None

    if paths == ("__words_confidence__",):
        value, found = _word_confidence(source)
    else:
        found = False
        value = None
        for candidate in paths:
            value, found = _path(source, candidate)
            if found:
                break
    if not found:
        return None, "unknown", "SOURCE_PATH_MISSING", None

    try:
        numeric = _number(value, metric_key)
    except LabelingRuntimeError:
        return None, "unknown", "SOURCE_VALUE_INVALID", None
    if conversion == "ratio_0_1_to_percent":
        if numeric < 0 or numeric > 1:
            return None, "unknown", "SOURCE_VALUE_OUT_OF_RANGE", None
        numeric *= 100
    if minimum is not None and numeric < minimum:
        return None, "unknown", "SOURCE_VALUE_OUT_OF_RANGE", None
    if maximum is not None and numeric > maximum:
        return None, "unknown", "SOURCE_VALUE_OUT_OF_RANGE", None

    observation = {
        "valueType": "integer" if precision == 0 else "number",
        "canonicalUnit": None,
        "conversion": conversion,
        "technicalMin": minimum,
        "technicalMax": maximum,
    }
    return _wire_number(numeric, precision), "available", None, observation


def validate_recording_evidence(evidence):
    if not isinstance(evidence, dict):
        raise LabelingRuntimeError("fusion no contiene recordingEvidence.")
    path = str(evidence.get("sealedPath") or "").strip()
    digest = str(evidence.get("sha256") or "").strip().lower()
    etag = str(evidence.get("etag") or "").strip()
    content_type = str(evidence.get("contentType") or "").strip().lower()
    if not path.startswith("labeling-evidence/") or ".." in path:
        raise LabelingRuntimeError("recordingEvidence.sealedPath no es válido.")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise LabelingRuntimeError("recordingEvidence.sha256 no es válido.")
    if not etag or not content_type.startswith("video/"):
        raise LabelingRuntimeError("recordingEvidence carece de ETag o tipo de video.")
    duration = evidence.get("durationSeconds")
    if duration is not None and _number(duration, "durationSeconds") < 0:
        raise LabelingRuntimeError("recordingEvidence.durationSeconds no es válido.")
    return {
        "sealedPath": path,
        "versionId": evidence.get("versionId") or None,
        "sha256": digest,
        "etag": etag,
        "contentType": content_type,
        "durationSeconds": _wire_number(duration, 3) if duration is not None else None,
    }


def _queue_classification(overall_score, areas, thresholds):
    overall = _number(overall_score, "overallScore")
    if overall < 0 or overall > 100:
        raise LabelingRuntimeError("overallScore está fuera de 0..100.")
    area_map = {}
    for area in areas:
        key = str(area["areaKey"])
        if key in area_map:
            raise LabelingRuntimeError("Hay áreas duplicadas.")
        value = _number(area["aiValue"], f"areas.{key}")
        if value < 0 or value > 100:
            raise LabelingRuntimeError(f"areas.{key} está fuera de 0..100.")
        area_map[key] = value
    if frozenset(area_map) != REQUIRED_AREA_KEYS:
        raise LabelingRuntimeError("El informe no contiene exactamente las cuatro áreas.")

    critical = sorted(key for key, value in area_map.items() if value < 50)
    if overall < 50 or critical:
        return "critical", {
            "kind": "critical",
            "overallScore": _wire_number(overall),
            "overallThreshold": 50,
            "criticalAreaKeys": critical,
        }
    try:
        half_width = _number(
            thresholds["gov.borderline_delta"]["halfWidth"], "halfWidth"
        )
        audit_at = _number(
            thresholds["gov.disparity_delta"]["auditAt"], "auditAt"
        )
    except (KeyError, TypeError):
        raise LabelingRuntimeError("Faltan umbrales de selección de la rúbrica.") from None
    if half_width <= 0 or half_width > 50 or audit_at <= 0 or audit_at > 100:
        raise LabelingRuntimeError("Los umbrales de selección no son válidos.")
    if abs(overall - 50) <= half_width:
        return "borderline", {
            "kind": "borderline",
            "overallScore": _wire_number(overall),
            "center": 50,
            "halfWidth": _wire_number(half_width),
        }
    minimum = min(area_map.values())
    maximum = max(area_map.values())
    minimum_key = min(key for key, value in area_map.items() if value == minimum)
    maximum_key = min(key for key, value in area_map.items() if value == maximum)
    delta = maximum - minimum
    if delta >= audit_at:
        return "disparity", {
            "kind": "disparity",
            "minAreaKey": minimum_key,
            "maxAreaKey": maximum_key,
            "delta": _wire_number(delta),
            "threshold": _wire_number(audit_at),
        }
    return "routine", {
        "kind": "routine",
        "selectionRule": "all_completed_current_reports",
    }


def build_labeling_snapshot(*, report, areas, pipeline_results, metric_catalog, evidence):
    """Build the immutable AI proposal from original pipeline rows only."""
    validated_evidence = validate_recording_evidence(evidence)
    metric_by_key = {item["metricKey"]: item for item in metric_catalog}
    if frozenset(metric_by_key) != EXPECTED_METRIC_KEYS:
        raise LabelingRuntimeError("La rúbrica no contiene exactamente las 16 métricas.")

    snapshot_metrics = []
    source_issues = []
    thresholds = {}
    for item in metric_catalog:
        key = item["metricKey"]
        thresholds[key] = item["publishedThresholds"]
        if key in OBSERVATION_SPECS:
            value, availability, unavailable_reason, observation = _observation(
                key, pipeline_results
            )
            if observation is not None:
                observation["canonicalUnit"] = item["unit"]
            editable = availability == "available"
            if availability == "unknown":
                source_issues.append(f"metric:{key}:{unavailable_reason.lower()}")
            kind = "observation"
        else:
            value = None
            availability = "not_emitted"
            editable = False
            kind = METRIC_KIND[key]
            observation = (
                {
                    "valueType": "integer",
                    "canonicalUnit": item["unit"],
                    "conversion": "identity",
                    "technicalMin": 1,
                    "technicalMax": 5,
                }
                if key == "empathy.victim_recog"
                else None
            )
            unavailable_reason = (
                "NO_SEMANTIC_PRODUCER"
                if key == "empathy.victim_recog"
                else "CONFIGURATION_NOT_OBSERVATION"
            )
        snapshot_metrics.append(
            {
                "metricKey": key,
                "categoryKey": item["categoryKey"],
                "label": item["label"],
                "metricKind": kind,
                "mappingVersion": 1,
                "unit": item["unit"],
                "precision": OBSERVATION_SPECS.get(key, (None, None, 0))[2],
                "aiValue": value,
                "availability": availability,
                "editable": editable,
                "observation": observation,
                "unavailableReason": unavailable_reason,
                "publishedThresholds": item["publishedThresholds"],
            }
        )

    source_status = "partial" if source_issues else "complete"
    queue_reason, reason_detail = _queue_classification(
        report["overallScore"], areas, thresholds
    )
    snapshot = {
        "schemaVersion": 1,
        "identity": {
            "clientId": report["clientId"],
            "sessionId": report["sessionId"],
            "reportId": report["reportId"],
            "analysisJobId": report["analysisJobId"],
            "rubricVersionId": report["rubricVersionId"],
        },
        "overallScore": _wire_number(report["overallScore"]),
        "areas": areas,
        "metrics": snapshot_metrics,
        "sourceIssues": source_issues,
        "recording": validated_evidence,
    }
    return {
        "snapshot": snapshot,
        "sourceStatus": source_status,
        "queueReason": queue_reason,
        "reasonDetail": reason_detail,
        "evidence": validated_evidence,
    }


def _load_material(cursor, report_id):
    cursor.execute(
        """SELECT r.id,r.session_id,r.analysis_job_id,r.rubric_version_id,
                  r.overall_score,s.client_id,
                  COALESCE(s.finished_at,s.updated_at,s.created_at)
             FROM dbo.report AS r
             JOIN dbo.[session] AS s ON s.id=r.session_id AND s.is_deleted=0
             JOIN dbo.analysis_job AS j
               ON j.id=r.analysis_job_id
              AND j.session_id=r.session_id
              AND j.rubric_version_id=r.rubric_version_id
            WHERE r.id=?""",
        report_id,
    )
    row = cursor.fetchone()
    if not row:
        raise LabelingRuntimeError("El informe no tiene una identidad relacional válida.")
    report = {
        "reportId": str(row[0]),
        "sessionId": str(row[1]),
        "analysisJobId": str(row[2]),
        "rubricVersionId": str(row[3]),
        "overallScore": row[4],
        "clientId": str(row[5]),
        "sessionFinishedAt": row[6],
    }

    cursor.execute(
        """SELECT ra.id,ra.area_key,a.value
             FROM dbo.area_score AS a
             JOIN dbo.rubric_area AS ra ON ra.id=a.rubric_area_id
            WHERE a.report_id=? ORDER BY ra.area_key""",
        report_id,
    )
    areas = [
        {"areaId": str(item[0]), "areaKey": item[1], "aiValue": _wire_number(item[2])}
        for item in cursor.fetchall()
    ]

    cursor.execute(
        """SELECT pipeline,summary_json
             FROM dbo.analysis_pipeline_result
            WHERE analysis_job_id=?
              AND pipeline IN ('vision','voice','content_judge','fusion')
            ORDER BY pipeline,id""",
        report["analysisJobId"],
    )
    pipelines = {}
    for pipeline, raw_json in cursor.fetchall():
        if pipeline in pipelines:
            raise LabelingRuntimeError(f"El pipeline {pipeline} está duplicado.")
        try:
            parsed = json.loads(raw_json)
        except (TypeError, ValueError):
            raise LabelingRuntimeError(f"El pipeline {pipeline} no contiene JSON válido.") from None
        if not isinstance(parsed, dict):
            raise LabelingRuntimeError(f"El pipeline {pipeline} no contiene un objeto JSON.")
        pipelines[pipeline] = parsed
    fusion = pipelines.get("fusion")
    if not fusion:
        raise LabelingRuntimeError("Falta el resultado fusion exacto.")
    fusion_report_id = fusion.get("reportId", fusion.get("report_id"))
    if str(fusion_report_id).lower() != report["reportId"].lower():
        raise LabelingRuntimeError("fusion no identifica el mismo informe.")

    cursor.execute(
        """SELECT d.metric_key,d.category,d.label,d.unit,v.thresholds_json,d.sort_order
             FROM dbo.rubric_metric_definition AS d
             JOIN dbo.rubric_metric_value AS v ON v.metric_key=d.metric_key
            WHERE v.rubric_version_id=?
            ORDER BY d.sort_order""",
        report["rubricVersionId"],
    )
    metric_catalog = []
    for item in cursor.fetchall():
        try:
            published = json.loads(item[4])
        except (TypeError, ValueError):
            raise LabelingRuntimeError(f"Umbrales inválidos para {item[0]}.") from None
        metric_catalog.append(
            {
                "metricKey": item[0],
                "categoryKey": item[1],
                "label": item[2],
                "unit": item[3],
                "publishedThresholds": published,
                "sortOrder": item[5],
            }
        )
    return report, areas, pipelines, metric_catalog, fusion.get("recordingEvidence")


def ensure_labeling_case_for_report(cursor, report_id, *, materialize=True):
    """Create at most one case for the exact report inside the caller transaction."""
    cursor.execute(
        "SELECT id FROM dbo.labeling_case WITH (UPDLOCK,HOLDLOCK) WHERE report_id=?",
        report_id,
    )
    existing = cursor.fetchone()
    if existing:
        return {"caseId": str(existing[0]), "created": False}

    report, areas, pipelines, metric_catalog, evidence = _load_material(
        cursor, report_id
    )
    built = build_labeling_snapshot(
        report=report,
        areas=areas,
        pipeline_results=pipelines,
        metric_catalog=metric_catalog,
        evidence=evidence,
    )
    if not materialize:
        return {"caseId": None, "created": False, **built}

    case_id = str(uuid.uuid4())
    evidence = built["evidence"]
    cursor.execute(
        """INSERT INTO dbo.labeling_case (
               id,client_id,session_id,report_id,analysis_job_id,rubric_version_id,
               session_finished_at,queue_reason,reason_detail_json,ai_snapshot_json,
               snapshot_schema_version,source_status,recording_evidence_path,
               recording_version_id,recording_sha256,recording_etag,
               recording_content_type,recording_duration_seconds,status
           ) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,'pending')""",
        case_id,
        report["clientId"],
        report["sessionId"],
        report["reportId"],
        report["analysisJobId"],
        report["rubricVersionId"],
        report["sessionFinishedAt"],
        built["queueReason"],
        json.dumps(built["reasonDetail"], ensure_ascii=False, sort_keys=True),
        json.dumps(built["snapshot"], ensure_ascii=False, sort_keys=True),
        built["sourceStatus"],
        evidence["sealedPath"],
        evidence["versionId"],
        bytes.fromhex(evidence["sha256"]),
        evidence["etag"],
        evidence["contentType"],
        evidence["durationSeconds"],
    )
    return {"caseId": case_id, "created": True, **built}


def reconcile_completed_reports(cursor, *, limit=100, materialize=False):
    """Reconcile completed reports with exact evidence, including superseded ones."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1000:
        raise ValueError("limit debe estar entre 1 y 1000.")
    cursor.execute(
        """SELECT TOP (?) r.id
             FROM dbo.report AS r
             JOIN dbo.[session] AS s ON s.id=r.session_id
            WHERE s.status='completed' AND s.is_deleted=0
              AND NOT EXISTS (
                  SELECT 1 FROM dbo.labeling_case AS lc WHERE lc.report_id=r.id
              )
            ORDER BY r.generated_at,r.id""",
        limit,
    )
    report_ids = [str(row[0]) for row in cursor.fetchall()]
    summary = {"scanned": len(report_ids), "eligible": 0, "created": 0, "errors": []}
    for report_id in report_ids:
        try:
            result = ensure_labeling_case_for_report(
                cursor, report_id, materialize=materialize
            )
        except LabelingRuntimeError as error:
            summary["errors"].append(
                {"reportId": report_id, "code": type(error).__name__}
            )
        else:
            summary["eligible"] += 1
            summary["created"] += int(result["created"])
    return summary
