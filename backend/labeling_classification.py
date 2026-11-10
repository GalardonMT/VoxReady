"""Deterministic queue classification for labeling cases.

The classifier is independent from SQL and never drops a valid case because of
its score. Missing or malformed inputs fail closed instead of falling back to
historical defaults.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


OVERALL_THRESHOLD = Decimal("50")
REQUIRED_AREA_KEYS = frozenset(("expression", "voice", "coherence", "empathy"))
QUEUE_REASONS = ("critical", "borderline", "disparity", "routine")
REASON_DETAIL_KEYS = {
    "critical": frozenset(("kind", "overallScore", "overallThreshold", "criticalAreaKeys")),
    "borderline": frozenset(("kind", "overallScore", "center", "halfWidth")),
    "disparity": frozenset(("kind", "minAreaKey", "maxAreaKey", "delta", "threshold")),
    "routine": frozenset(("kind", "selectionRule")),
}


class ClassificationError(ValueError):
    """The report cannot be classified without inventing evidence."""


@dataclass(frozen=True)
class ClassificationRules:
    borderline_half_width: Decimal
    disparity_threshold: Decimal

    def __post_init__(self):
        if self.borderline_half_width <= 0:
            raise ClassificationError("gov.borderline_delta.halfWidth debe ser mayor que cero.")
        if self.borderline_half_width > OVERALL_THRESHOLD:
            raise ClassificationError("gov.borderline_delta.halfWidth no puede superar 50.")
        if self.disparity_threshold <= 0:
            raise ClassificationError("gov.disparity_delta.auditAt debe ser mayor que cero.")
        if self.disparity_threshold > 100:
            raise ClassificationError("gov.disparity_delta.auditAt no puede superar 100.")


@dataclass(frozen=True)
class ClassificationResult:
    queue_reason: str
    reason_detail: dict

    def __post_init__(self):
        if self.queue_reason not in QUEUE_REASONS:
            raise ClassificationError("Motivo de cola desconocido.")
        if self.reason_detail.get("kind") != self.queue_reason:
            raise ClassificationError("reasonDetail.kind no coincide con queueReason.")
        if frozenset(self.reason_detail) != REASON_DETAIL_KEYS[self.queue_reason]:
            raise ClassificationError("reasonDetail no coincide con el contrato del motivo.")


def _decimal(value, label):
    if isinstance(value, bool) or value is None:
        raise ClassificationError(f"{label} debe ser numérico.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ClassificationError(f"{label} debe ser numérico.") from None
    if not parsed.is_finite():
        raise ClassificationError(f"{label} debe ser finito.")
    return parsed


def _score(value, label):
    parsed = _decimal(value, label)
    if parsed < 0 or parsed > 100:
        raise ClassificationError(f"{label} debe estar entre 0 y 100.")
    return parsed


def _wire_number(value):
    integral = value.to_integral_value()
    return int(integral) if value == integral else float(value)


def rules_from_metric_thresholds(metric_thresholds: Mapping[str, Mapping]):
    """Build rules from the report rubric version; no catalog default is used."""
    try:
        borderline = metric_thresholds["gov.borderline_delta"]
        disparity = metric_thresholds["gov.disparity_delta"]
        half_width = borderline["halfWidth"]
        audit_at = disparity["auditAt"]
    except (KeyError, TypeError):
        raise ClassificationError(
            "Faltan halfWidth o auditAt en la configuración de gobernanza del informe."
        ) from None
    return ClassificationRules(
        borderline_half_width=_decimal(half_width, "gov.borderline_delta.halfWidth"),
        disparity_threshold=_decimal(audit_at, "gov.disparity_delta.auditAt"),
    )


def classify_case(overall_score, area_scores: Mapping[str, object], rules: ClassificationRules):
    """Classify one report using the frozen priority and reasonDetail contract."""
    overall = _score(overall_score, "overallScore")
    if not isinstance(area_scores, Mapping):
        raise ClassificationError("areaScores debe ser un mapa.")
    normalized_keys = {str(key).strip() for key in area_scores}
    if normalized_keys != REQUIRED_AREA_KEYS or len(area_scores) != len(REQUIRED_AREA_KEYS):
        raise ClassificationError(
            "areaScores debe contener exactamente expression, voice, coherence y empathy."
        )
    areas = {
        str(key).strip(): _score(value, f"areaScores.{str(key).strip()}")
        for key, value in area_scores.items()
    }

    critical_area_keys = sorted(
        key for key, value in areas.items() if value < OVERALL_THRESHOLD
    )
    if overall < OVERALL_THRESHOLD or critical_area_keys:
        return ClassificationResult(
            queue_reason="critical",
            reason_detail={
                "kind": "critical",
                "overallScore": _wire_number(overall),
                "overallThreshold": _wire_number(OVERALL_THRESHOLD),
                "criticalAreaKeys": critical_area_keys,
            },
        )

    if abs(overall - OVERALL_THRESHOLD) <= rules.borderline_half_width:
        return ClassificationResult(
            queue_reason="borderline",
            reason_detail={
                "kind": "borderline",
                "overallScore": _wire_number(overall),
                "center": _wire_number(OVERALL_THRESHOLD),
                "halfWidth": _wire_number(rules.borderline_half_width),
            },
        )

    minimum = min(areas.values())
    maximum = max(areas.values())
    minimum_key = min(key for key, value in areas.items() if value == minimum)
    maximum_key = min(key for key, value in areas.items() if value == maximum)
    delta = maximum - minimum
    if delta >= rules.disparity_threshold:
        return ClassificationResult(
            queue_reason="disparity",
            reason_detail={
                "kind": "disparity",
                "minAreaKey": minimum_key,
                "maxAreaKey": maximum_key,
                "delta": _wire_number(delta),
                "threshold": _wire_number(rules.disparity_threshold),
            },
        )

    return ClassificationResult(
        queue_reason="routine",
        reason_detail={
            "kind": "routine",
            "selectionRule": "all_completed_current_reports",
        },
    )
