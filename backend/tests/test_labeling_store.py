"""Domain tests for the labeling queue store (Tarea 3)."""

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labeling_store


NOW = datetime(2026, 10, 30, 12, 0, 0)
CASE_ID = "11111111-1111-4111-8111-111111111111"
CLIENT_ID = "22222222-2222-4222-8222-222222222222"
SESSION_ID = "33333333-3333-4333-8333-333333333333"
REPORT_ID = "44444444-4444-4444-8444-444444444444"
RUBRIC_ID = "55555555-5555-4555-8555-555555555555"
ACTOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ACTOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
AREA_IDS = {
    "expression": "61111111-1111-4111-8111-111111111111",
    "voice": "62222222-2222-4222-8222-222222222222",
    "coherence": "63333333-3333-4333-8333-333333333333",
    "empathy": "64444444-4444-4444-8444-444444444444",
}


def snapshot():
    return {
        "schemaVersion": 1,
        "sourceIssues": ["metric:empathy.victim_recog:no_semantic_producer"],
        "areas": [
            {"areaId": AREA_IDS[key], "areaKey": key, "aiValue": value}
            for key, value in (
                ("expression", 85),
                ("voice", 80),
                ("coherence", 82),
                ("empathy", 42),
            )
        ],
        "metrics": [
            {
                "metricKey": "voice.wpm",
                "categoryKey": "voice",
                "metricKind": "observation",
                "label": "Ritmo",
                "availability": "available",
                "aiValue": 132.4,
                "unit": "WPM",
                "precision": 1,
                "mappingVersion": 1,
                "observation": {
                    "valueType": "number",
                    "canonicalUnit": "WPM",
                    "conversion": "identity",
                    "technicalMin": 0,
                    "technicalMax": None,
                },
                "editable": True,
                "unavailableReason": None,
                "publishedThresholds": {"optimalLow": 120},
            },
            {
                "metricKey": "empathy.victim_recog",
                "categoryKey": "empathy",
                "metricKind": "observation",
                "label": "Reconocimiento",
                "availability": "not_emitted",
                "aiValue": None,
                "unit": "nivel",
                "precision": 0,
                "mappingVersion": 1,
                "observation": None,
                "editable": False,
                "unavailableReason": "NO_SEMANTIC_PRODUCER",
                "publishedThresholds": {},
            },
        ],
        "recording": {"durationSeconds": 249.6},
    }


CASE_COLUMNS = [
    "case_id", "case_number", "client_id", "report_id", "rubric_version_id",
    "session_finished_at", "queue_reason", "reason_detail_json", "ai_snapshot_json",
    "snapshot_schema_version", "source_status", "status", "lock_owner_id",
    "lock_expires_at", "lease_generation", "content_revision",
    "recording_evidence_path", "recording_duration_seconds", "client_name",
    "speaker_id", "started_at", "scenario_title", "report_generated_at",
    "overall_score", "latest_review_id", "latest_review_no", "latest_reviewer_id",
    "latest_submitted_at", "current_review_id", "current_review_no",
    "current_reviewer_id", "current_submitted_at",
]


def case_row(*, status="pending", finished=None, case_id=CASE_ID, reviewed=False):
    finished = finished or NOW
    latest = "77777777-7777-4777-8777-777777777777" if reviewed else None
    return (
        case_id, 8844, CLIENT_ID, REPORT_ID, RUBRIC_ID, finished, "critical",
        json.dumps({"kind": "critical", "overallScore": 48, "overallThreshold": 50,
                    "criticalAreaKeys": ["empathy"]}),
        json.dumps(snapshot()), 1, "complete", status, None, None, 0, 1,
        "labeling-evidence/session/job/hash.webm", 249.6, "Organización de prueba",
        SESSION_ID, finished - timedelta(minutes=4, seconds=10), "Crisis reputacional",
        finished + timedelta(seconds=10), 48, latest, 1 if reviewed else None,
        ACTOR_A if reviewed else None, finished + timedelta(minutes=5) if reviewed else None,
        latest, 1 if reviewed else None, ACTOR_A if reviewed else None,
        finished + timedelta(minutes=5) if reviewed else None,
    )


class ReadCursor:
    def __init__(self, rows):
        self.source_rows = rows
        self.description = []
        self.rows = []
        self.row = None
        self.statements = []

    def execute(self, statement, *params):
        self.statements.append((statement, params))
        if "labeling:clock" in statement:
            self.row = (NOW,)
        elif "labeling:list:count" in statement:
            self.row = (len(self.source_rows),)
        elif "labeling:list:" in statement or "labeling:detail" in statement:
            self.description = [(column,) for column in CASE_COLUMNS]
            self.rows = list(self.source_rows)
            if "labeling:detail" in statement:
                self.row = self.rows[0] if self.rows else None
                self.rows = []
        else:
            raise AssertionError(statement)
        return self

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


def test_pending_and_reviewed_lists_are_bounded_stable_and_exclusive():
    pending_cursor = ReadCursor([case_row()])
    pending = labeling_store.list_cases(
        pending_cursor, status="pending", limit=10, actor_id=ACTOR_A, now=NOW
    )
    reviewed_cursor = ReadCursor([case_row(status="reviewed", reviewed=True)])
    reviewed = labeling_store.list_cases(
        reviewed_cursor, status="reviewed", limit=10, actor_id=ACTOR_A, now=NOW
    )

    assert pending["total"] == 1 and pending["limit"] == 10
    assert pending["items"][0]["latestReview"] is None
    assert reviewed["items"][0]["latestReview"]["reviewNo"] == 1
    pending_sql = next(sql for sql, _ in pending_cursor.statements if "labeling:list:pending" in sql)
    reviewed_sql = next(sql for sql, _ in reviewed_cursor.statements if "labeling:list:reviewed" in sql)
    assert "lc.status=?" in pending_sql and "lc.session_finished_at DESC,lc.id DESC" in pending_sql
    assert "lc.status=?" in reviewed_sql and "latest.submitted_at DESC,latest.id DESC" in reviewed_sql
    assert "UPDLOCK" not in pending_sql and "HOLDLOCK" not in pending_sql
    with pytest.raises(labeling_store.LabelingStoreError) as error:
        labeling_store.list_cases(ReadCursor([]), status="pending", limit=11, now=NOW)
    assert error.value.status == 422


def test_detail_normalizes_snapshot_and_exposes_no_personal_identity_or_blob_path():
    cursor = ReadCursor([case_row()])
    detail = labeling_store.get_case_detail(cursor, CASE_ID, actor_id=ACTOR_A, now=NOW)

    assert detail["speakerCode"].startswith("VOC-")
    assert detail["client"]["code"].startswith("CLI-")
    assert detail["session"]["durationSeconds"] == 250
    assert detail["criticalAreas"] == [
        {"areaKey": "empathy", "label": "Nivel de empatía", "value": 42}
    ]
    assert [area["areaKey"] for area in detail["rubric"]["areas"]] == [
        "expression", "voice", "coherence", "empathy"
    ]
    assert detail["metricGroups"][0]["categoryKey"] == "voice"
    rendered = json.dumps(detail, default=str)
    assert "@" not in rendered
    assert "labeling-evidence/" not in rendered
    sql = next(sql for sql, _ in cursor.statements if "labeling:detail" in sql)
    assert "UPDLOCK" not in sql and "HOLDLOCK" not in sql


def test_detail_marks_expired_lease_without_exposing_former_owner():
    row = list(case_row())
    row[12] = ACTOR_B
    row[13] = NOW - timedelta(seconds=1)
    detail = labeling_store.get_case_detail(
        ReadCursor([tuple(row)]), CASE_ID, actor_id=ACTOR_A, now=NOW
    )
    assert detail["lease"] == {
        "state": "expired", "ownerCode": None, "expiresAt": None
    }


class DomainCursor:
    def __init__(self, *, source_status="complete", status="pending"):
        self.case = {
            "id": CASE_ID,
            "client_id": CLIENT_ID,
            "status": status,
            "source_status": source_status,
            "lock_owner_id": None,
            "lock_token_hash": None,
            "lock_expires_at": None,
            "lease_generation": 0,
            "content_revision": 1,
            "ai_snapshot_json": json.dumps(snapshot()),
            "rubric_version_id": RUBRIC_ID,
        }
        self.row = None
        self.rows = []
        self.description = []
        self.statements = []
        self.audits = []
        self.reviews = []
        self.area_corrections = []
        self.metric_corrections = []
        self.review_inserts = 0
        self.fail_marker = None

    def execute(self, statement, *params):
        self.statements.append((statement, params))
        if self.fail_marker and self.fail_marker in statement:
            raise RuntimeError("injected failure")
        if "labeling:transaction" in statement:
            pass
        elif "labeling:clock" in statement:
            self.row = (NOW,)
        elif "labeling:case:lock" in statement:
            c = self.case
            self.row = tuple(c[key] for key in (
                "id", "client_id", "status", "source_status", "lock_owner_id",
                "lock_token_hash", "lock_expires_at", "lease_generation",
                "content_revision", "ai_snapshot_json", "rubric_version_id",
            ))
        elif "labeling:lease:claim" in statement:
            self.case.update({
                "lock_owner_id": params[0], "lock_token_hash": params[1],
                "lock_expires_at": params[3], "lease_generation": params[4],
            })
        elif "labeling:lease:renew" in statement:
            self.case["lock_expires_at"] = params[0]
        elif "labeling:lease:release" in statement:
            self.case.update({
                "lock_owner_id": None, "lock_token_hash": None, "lock_expires_at": None,
            })
        elif "labeling:audit" in statement:
            self.audits.append({"client": params[0], "actor": params[1],
                                "event": params[2], "case": params[3],
                                "detail": json.loads(params[4])})
        elif "labeling:review:idempotency" in statement:
            found = next((review for review in self.reviews
                          if review["case_id"] == params[0]
                          and review["idempotency_key"] == params[1]), None)
            self.row = (
                found["id"], found["request_hash"], found["reviewer_id"]
            ) if found else None
        elif "labeling:review:current" in statement:
            current = next((review for review in self.reviews if review["is_current"]), None)
            self.row = (current["id"], current["review_no"]) if current else None
        elif "labeling:review:supersede" in statement:
            for review in self.reviews:
                if review["id"] == str(params[0]):
                    review["is_current"] = False
        elif "labeling:review:insert" in statement:
            self.review_inserts += 1
            self.reviews.append({
                "id": params[0], "case_id": params[1], "reviewer_id": params[2],
                "review_no": params[3], "overall_comment": params[4],
                "supersedes": params[5], "is_current": True,
                "idempotency_key": params[6], "request_hash": params[7],
                "submitted_at": params[8],
            })
        elif "labeling:review:area:insert" in statement:
            self.area_corrections.append(params)
        elif "labeling:review:metric:insert" in statement:
            self.metric_corrections.append(params)
        elif "labeling:review:case:update" in statement:
            self.case.update({
                "status": "reviewed", "content_revision": params[2],
                "lock_owner_id": None, "lock_token_hash": None,
                "lock_expires_at": None,
            })
        elif "labeling:review:response" in statement:
            review = next(review for review in self.reviews if review["id"] == params[0])
            self.row = (
                review["id"], review["case_id"], review["reviewer_id"],
                review["review_no"], review["overall_comment"], review["supersedes"],
                review["is_current"], review["submitted_at"], self.case["content_revision"],
            )
        elif "labeling:review:areas" in statement:
            self.rows = [
                (next(key for key, value in AREA_IDS.items() if value == item[1]),
                 item[2], item[3], item[4])
                for item in self.area_corrections if item[0] == params[0]
            ]
        elif "labeling:review:metrics" in statement:
            self.rows = [
                (item[1], item[4], item[5], item[3], item[6])
                for item in self.metric_corrections if item[0] == params[0]
            ]
        elif "labeling:reviews:headers" in statement:
            self.rows = [
                (
                    review["id"], review["case_id"], review["reviewer_id"],
                    review["review_no"], review["overall_comment"],
                    review["supersedes"], review["is_current"],
                    review["submitted_at"], self.case["content_revision"],
                )
                for review in sorted(
                    self.reviews, key=lambda value: value["review_no"], reverse=True
                )
            ]
        elif "labeling:reviews:areas" in statement:
            self.rows = [
                (item[0], next(key for key, value in AREA_IDS.items() if value == item[1]),
                 item[2], item[3], item[4])
                for item in self.area_corrections
            ]
        elif "labeling:reviews:metrics" in statement:
            self.rows = [
                (item[0], item[1], item[4], item[5], item[3], item[6])
                for item in self.metric_corrections
            ]
        else:
            raise AssertionError(statement)
        return self

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


def acquire(cursor, actor=ACTOR_A):
    return labeling_store.acquire_lease(cursor, CASE_ID, actor, now=NOW)


def review_request(lease, *, key="88888888-8888-4888-8888-888888888888",
                   supersedes=None, comment="Revisión experta"):
    return {
        "leaseToken": lease["leaseToken"],
        "leaseGeneration": lease["leaseGeneration"],
        "expectedContentRevision": lease["contentRevision"],
        "idempotencyKey": key,
        "supersedesReviewId": supersedes,
        "overallComment": comment,
        "rubricCorrections": [
            {"areaId": AREA_IDS[key], "correctedValue": value, "comment": area_comment}
            for key, value, area_comment in (
                ("expression", 82, "Contacto visual intermitente"),
                ("voice", 80, None),
                ("coherence", 82, None),
                ("empathy", 44, "Mostró reconocimiento explícito"),
            )
        ],
        "metricCorrections": [
            {"metricKey": "voice.wpm", "correctedValue": 128.0,
             "comment": "Se excluyó el silencio inicial"}
        ],
    }


def test_claim_claim_renew_release_reclaim_and_two_tabs():
    cursor = DomainCursor()
    lease = acquire(cursor)
    assert lease["leaseGeneration"] == 1
    assert cursor.case["lock_token_hash"] == hashlib.sha256(
        lease["leaseToken"].encode()
    ).digest()
    assert lease["leaseToken"].encode() not in cursor.case["lock_token_hash"]
    with pytest.raises(labeling_store.LabelingStoreError) as other:
        acquire(cursor, ACTOR_B)
    assert other.value.code == "LEASE_CONFLICT"
    with pytest.raises(labeling_store.LabelingStoreError) as second_tab:
        acquire(cursor, ACTOR_A)
    assert second_tab.value.code == "LEASE_CONFLICT"

    renewed = labeling_store.acquire_lease(
        cursor, CASE_ID, ACTOR_A, lease_token=lease["leaseToken"],
        lease_generation=1, now=NOW + timedelta(minutes=5)
    )
    assert renewed["leaseGeneration"] == 1
    assert renewed["contentRevision"] == 1
    released = labeling_store.release_lease(
        cursor, CASE_ID, ACTOR_A, lease_token=lease["leaseToken"],
        lease_generation=1, now=NOW + timedelta(minutes=6)
    )
    assert released == {"released": True, "idempotent": False}
    assert labeling_store.release_lease(
        cursor, CASE_ID, ACTOR_A, lease_token=lease["leaseToken"],
        lease_generation=1, now=NOW + timedelta(minutes=7)
    )["idempotent"] is True
    new_lease = labeling_store.acquire_lease(
        cursor, CASE_ID, ACTOR_B, now=NOW + timedelta(minutes=8)
    )
    assert new_lease["leaseGeneration"] == 2
    with pytest.raises(labeling_store.LabelingStoreError) as stale:
        labeling_store.release_lease(
            cursor, CASE_ID, ACTOR_A, lease_token=lease["leaseToken"],
            lease_generation=1, now=NOW + timedelta(minutes=9)
        )
    assert stale.value.code == "STALE_LEASE"
    assert all("leaseToken" not in event["detail"] for event in cursor.audits)


def test_expired_lease_can_be_claimed_by_another_expert_with_new_generation():
    cursor = DomainCursor()
    old = acquire(cursor)
    cursor.case["lock_expires_at"] = NOW - timedelta(seconds=1)
    claimed = labeling_store.acquire_lease(cursor, CASE_ID, ACTOR_B, now=NOW)
    assert claimed["leaseGeneration"] == old["leaseGeneration"] + 1
    assert cursor.case["lock_owner_id"] == ACTOR_B
    assert cursor.audits[-1]["detail"]["expiredPreviousLease"] is True


def test_submit_is_atomic_immutable_and_idempotent_without_client_ai_values():
    cursor = DomainCursor()
    lease = acquire(cursor)
    lease = labeling_store.acquire_lease(
        cursor, CASE_ID, ACTOR_A, lease_token=lease["leaseToken"],
        lease_generation=lease["leaseGeneration"], now=NOW + timedelta(minutes=5)
    )
    request = review_request(lease)
    first = labeling_store.submit_review(
        cursor, CASE_ID, ACTOR_A, request, now=NOW + timedelta(minutes=5)
    )

    assert first["replayed"] is False
    assert first["review"]["reviewNo"] == 1
    assert cursor.case["status"] == "reviewed"
    assert cursor.case["content_revision"] == 2
    assert cursor.case["lock_owner_id"] is None
    assert cursor.review_inserts == 1
    assert len(cursor.area_corrections) == 4
    assert cursor.area_corrections[0][2] == Decimal("85")
    assert cursor.metric_corrections[0][4] == Decimal("132.4")
    audit_text = json.dumps(cursor.audits[-1])
    assert "silencio" not in audit_text and lease["leaseToken"] not in audit_text

    replay = labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, request, now=NOW)
    assert replay["replayed"] is True
    assert replay["review"]["reviewId"] == first["review"]["reviewId"]
    assert cursor.review_inserts == 1
    changed = deepcopy(request)
    changed["overallComment"] = "Otro contenido"
    with pytest.raises(labeling_store.LabelingStoreError) as conflict:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, changed, now=NOW)
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(labeling_store.LabelingStoreError) as other_actor:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_B, request, now=NOW)
    assert other_actor.value.code == "IDEMPOTENCY_CONFLICT"
    concurrent = deepcopy(request)
    concurrent["idempotencyKey"] = "12345678-1234-4234-8234-123456789012"
    with pytest.raises(labeling_store.LabelingStoreError) as second_submit:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, concurrent, now=NOW)
    assert second_submit.value.code == "STALE_LEASE"


def test_review_validation_requires_all_areas_comments_and_fresh_revision():
    cursor = DomainCursor()
    lease = acquire(cursor)
    incomplete = review_request(lease)
    incomplete["rubricCorrections"].pop()
    with pytest.raises(labeling_store.LabelingStoreError) as missing:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, incomplete, now=NOW)
    assert missing.value.code == "INCOMPLETE_RUBRIC"

    no_comment = review_request(lease)
    no_comment["rubricCorrections"][0]["comment"] = "  "
    with pytest.raises(labeling_store.LabelingStoreError) as comment:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, no_comment, now=NOW)
    assert comment.value.code == "COMMENT_REQUIRED"

    stale = review_request(lease)
    stale["expectedContentRevision"] = 99
    with pytest.raises(labeling_store.LabelingStoreError) as revision:
        labeling_store.submit_review(cursor, CASE_ID, ACTOR_A, stale, now=NOW)
    assert revision.value.code == "CONTENT_REVISION_CONFLICT"


def test_new_review_supersedes_current_without_overwriting_history():
    cursor = DomainCursor()
    first_lease = acquire(cursor)
    first = labeling_store.submit_review(
        cursor, CASE_ID, ACTOR_A, review_request(first_lease), now=NOW
    )["review"]
    second_lease = labeling_store.acquire_lease(
        cursor, CASE_ID, ACTOR_B, allow_reviewed=True, now=NOW + timedelta(minutes=1)
    )
    second_request = review_request(
        second_lease,
        key="99999999-9999-4999-8999-999999999999",
        supersedes=first["reviewId"],
        comment="Segunda revisión",
    )
    second = labeling_store.submit_review(
        cursor, CASE_ID, ACTOR_B, second_request, now=NOW + timedelta(minutes=1)
    )["review"]

    assert second["reviewNo"] == 2
    assert second["supersedesReviewId"] == first["reviewId"]
    assert len(cursor.reviews) == 2
    assert cursor.reviews[0]["is_current"] is False
    assert cursor.reviews[1]["is_current"] is True
    assert cursor.case["content_revision"] == 3
    history = labeling_store.list_reviews(cursor, CASE_ID)
    assert history["total"] == 2
    assert [item["reviewNo"] for item in history["items"]] == [2, 1]
    history_sql = [sql for sql, _ in cursor.statements if "labeling:reviews:" in sql]
    assert len(history_sql) == 3


def test_injected_failure_propagates_before_case_resolution_for_caller_rollback():
    cursor = DomainCursor()
    lease = acquire(cursor)
    before = deepcopy(cursor.case)
    cursor.fail_marker = "labeling:review:metric:insert"
    with pytest.raises(RuntimeError, match="injected failure"):
        labeling_store.submit_review(
            cursor, CASE_ID, ACTOR_A, review_request(lease), now=NOW
        )
    assert cursor.case == before
    assert not any("labeling:review:case:update" in sql for sql, _ in cursor.statements)
    source = Path(labeling_store.__file__).read_text(encoding="utf-8")
    assert ".commit(" not in source and ".rollback(" not in source


class QualityCursor:
    def __init__(self):
        self.row = None
        self.rows = []
        self.description = []
        self.statements = []

    def execute(self, statement, *params):
        self.statements.append((statement, params))
        aggregate_columns = [
            "sample_count", "mean_ai_value", "mean_corrected_value", "mean_delta",
            "mean_absolute_error", "changed_count", "increased_count",
            "decreased_count", "unchanged_count",
        ]
        aggregate_values = (3, 80, 78, -2, 4, 2, 1, 1, 1)
        if "labeling:quality:cases" in statement:
            self.row = (3,)
        elif "labeling:quality:areas" in statement:
            self.description = [(name,) for name in ["rubricVersionId", "areaKey"] + aggregate_columns]
            self.rows = [(RUBRIC_ID, "expression") + aggregate_values]
        elif "labeling:quality:metrics" in statement:
            self.description = [(name,) for name in ["metricKey", "mappingVersion", "unit"] + aggregate_columns]
            self.rows = [("voice.wpm", 1, "WPM") + aggregate_values]
        elif "labeling:quality:categories" in statement:
            self.rows = [("voice", 3, 2)]
        else:
            raise AssertionError(statement)
        return self

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


def test_quality_aggregates_preserve_identity_and_do_not_cancel_error():
    cursor = QualityCursor()
    result = labeling_store.quality_summary(
        cursor,
        period_from=NOW - timedelta(days=30),
        period_to=NOW + timedelta(days=1),
    )

    area = result["rubricAreas"][0]
    metric = result["metrics"][0]
    assert area["rubricVersionId"] == RUBRIC_ID
    assert area["meanDelta"] == -2 and area["meanAbsoluteError"] == 4
    assert (area["increasedCount"], area["decreasedCount"], area["unchangedCount"]) == (1, 1, 1)
    assert (metric["metricKey"], metric["mappingVersion"], metric["unit"]) == (
        "voice.wpm", 1, "WPM"
    )
    area_sql = next(sql for sql, _ in cursor.statements if "labeling:quality:areas" in sql)
    metric_sql = next(sql for sql, _ in cursor.statements if "labeling:quality:metrics" in sql)
    assert "AVG(CAST(ABS(c.corrected_value-c.ai_value)" in area_sql
    assert "GROUP BY lc.rubric_version_id,ra.area_key" in area_sql
    assert "GROUP BY c.metric_key,c.mapping_version,c.unit" in metric_sql
    assert "r.is_current=1" in area_sql


def test_audit_recording_access_whitelists_only_non_sensitive_context():
    cursor = DomainCursor()
    labeling_store.audit_recording_access(
        cursor, case_id=CASE_ID, client_id=CLIENT_ID, actor_id=ACTOR_A,
        version_id="version-id"
    )
    assert cursor.audits == [{
        "client": CLIENT_ID, "actor": ACTOR_A,
        "event": "labeling_recording_accessed", "case": CASE_ID,
        "detail": {"evidenceVersioned": True},
    }]
    rendered = json.dumps(cursor.audits)
    for forbidden in ("token", "comment", "email", "sas", "transcript"):
        assert forbidden not in rendered.lower()
