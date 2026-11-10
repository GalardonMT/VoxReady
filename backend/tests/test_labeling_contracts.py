"""Runtime-independent checks for the public labeling API contracts."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from pydantic import ValidationError
import pytest

import labeling_api
from labeling_api import create_labeling_router
from schemas.labeling import LeaseRequest, ReviewRequest


def _app():
    app = FastAPI()
    app.include_router(create_labeling_router(
        verify_token_dependency=lambda: {},
        database_factory=lambda: nullcontext(object()),
        resolve_master=lambda _cursor, _claims: {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "role": "master_config",
        },
        issue_recording_url=lambda _evidence, _expiry: "https://storage.invalid/x?sig=x",
    ))
    return app


def _review():
    return {
        "leaseToken": "x" * 32,
        "leaseGeneration": 1,
        "expectedContentRevision": 1,
        "idempotencyKey": "55555555-5555-4555-8555-555555555555",
        "supersedesReviewId": None,
        "overallComment": "  revisión   experta  ",
        "rubricCorrections": [{
            "areaId": "44444444-4444-4444-8444-444444444444",
            "correctedValue": 82,
            "comment": "justificación",
        }],
        "metricCorrections": [],
    }


def test_openapi_exposes_canonical_and_legacy_aliases_without_internal_columns():
    openapi = _app().openapi()
    paths = openapi["paths"]
    for suffix in (
        "/labeling-cases", "/labeling-cases/{case_id}",
        "/labeling-cases/{case_id}/lease",
        "/labeling-cases/{case_id}/recording-url",
        "/labeling-cases/{case_id}/reviews", "/quality-reviews/summary",
    ):
        assert "/api/master" + suffix in paths
        assert "/v1/api/master" + suffix in paths
    serialized = str(openapi).lower()
    for name in (
        "lock_token_hash", "recording_evidence_path", "recording_sha256",
        "analysis_job_id", "speaker_id",
    ):
        assert name not in serialized


def test_review_schema_forbids_server_owned_fields_and_normalizes_comment():
    payload = _review()
    parsed = ReviewRequest.model_validate(payload)
    assert parsed.overallComment == "revisión experta"
    for field in ("aiValue", "reviewerId", "status", "submittedAt", "isCurrent"):
        invalid = dict(payload)
        invalid[field] = "server-owned"
        with pytest.raises(ValidationError):
            ReviewRequest.model_validate(invalid)


def test_lease_acquire_and_renew_shapes_are_atomic():
    assert LeaseRequest.model_validate({"leaseToken": None, "leaseGeneration": None})
    assert LeaseRequest.model_validate({"leaseToken": "x" * 32, "leaseGeneration": 2})
    with pytest.raises(ValidationError):
        LeaseRequest.model_validate({"leaseToken": "x" * 32, "leaseGeneration": None})


def test_problem_responses_are_documented_for_master_routes():
    operation = _app().openapi()["paths"]["/api/master/labeling-cases"]["get"]
    assert {"403", "404", "409", "410", "422", "503"}.issubset(operation["responses"])
    for status in ("403", "404", "409", "410", "422", "503"):
        assert "application/problem+json" in operation["responses"][status]["content"]


def test_reviewed_cases_can_be_claimed_only_through_explicit_lease_operation(monkeypatch):
    captured = {}
    monkeypatch.setattr(labeling_api, "_LABELING_DB", lambda: nullcontext(object()))
    monkeypatch.setattr(
        labeling_api.labeling_store,
        "acquire_lease",
        lambda *_args, **kwargs: captured.update(kwargs) or {
            "caseId": "11111111-1111-4111-8111-111111111111",
            "leaseToken": "x" * 32,
            "leaseGeneration": 1,
            "contentRevision": 2,
            "expiresAt": "2026-10-27T14:24:30Z",
            "serverTime": "2026-10-27T14:04:30Z",
            "readOnly": False,
        },
    )
    request = SimpleNamespace(state=SimpleNamespace(labeling_master={
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "role": "master_config",
    }))
    labeling_api._acquire_lease(
        "11111111-1111-4111-8111-111111111111",
        LeaseRequest(leaseToken=None, leaseGeneration=None),
        request,
    )
    assert captured["allow_reviewed"] is True


def test_recording_sas_is_bound_to_sealed_evidence_and_https_only():
    source = Path(__file__).parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert 'version_id=version_id' in source
    assert 'actual_etag != expected_etag' in source
    assert 'actual_content_type != expected_content_type' in source
    assert 'permission=BlobSasPermissions(read=True)' in source
    assert 'protocol="https"' in source
    assert 'recording_evidence_path' not in source[source.index("def _issue_labeling_recording_url"):]
