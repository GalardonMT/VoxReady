"""HTTP contract tests for Tarea 4 of the labeling queue."""

from contextlib import contextmanager
from datetime import datetime, timezone
import sys
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
import pytest

import labeling_api


pytestmark = pytest.mark.skipif(
    sys.platform == "win32" and sys.version_info >= (3, 14),
    reason="Starlette TestClient/AnyIO queda bloqueado por socketpair en Python 3.14 para Windows; se ejecuta en el runtime backend soportado.",
)


CASE_ID = "11111111-1111-4111-8111-111111111111"
ACTOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
NOW = datetime(2026, 10, 27, 14, 4, 30, tzinfo=timezone.utc)


class Cursor:
    def __init__(self):
        self.statement = ""

    def execute(self, statement, *params):
        self.statement = statement
        return self

    def fetchone(self):
        if "labeling:recording:evidence" in self.statement:
            return (
                CASE_ID, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "labeling-evidence/sealed.webm", None, '"0xETAG"',
                "video/webm", 249.6,
            )
        return None


@contextmanager
def database():
    yield Cursor()


def verify_token(authorization: str | None = Header(None)):
    if not authorization:
        raise HTTPException(403, "Usuario no autenticado.")
    return {"role_hint": authorization.removeprefix("Bearer ")}


def resolve_master(_cursor, claims):
    role = claims["role_hint"]
    if role != "master_config":
        raise HTTPException(403, "Se requiere el rol master_config.")
    return {"id": ACTOR_ID, "role": role, "client_id": None}


def issue_recording_url(_evidence, _expires_at):
    return "https://storage.invalid/sealed.webm?sig=redacted"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(labeling_api.create_labeling_router(
        verify_token_dependency=verify_token,
        database_factory=database,
        resolve_master=resolve_master,
        issue_recording_url=issue_recording_url,
    ))
    return TestClient(app)


def auth(role="master_config"):
    return {"Authorization": f"Bearer {role}"}


def list_payload():
    return {
        "items": [{
            "caseId": CASE_ID, "caseNumber": "8844", "status": "pending",
            "queueReason": "critical",
            "reasonDetail": {"kind": "critical", "overallScore": 48},
            "client": {"code": "CLI-12345678", "displayName": "Organización"},
            "speakerCode": "VOC-12345678", "scenario": {"title": "Crisis"},
            "session": {"startedAt": NOW, "finishedAt": NOW, "durationSeconds": 250},
            "report": {
                "reportId": "22222222-2222-4222-8222-222222222222",
                "generatedAt": NOW, "overallScore": 48,
            },
            "criticalAreas": [{"areaKey": "empathy", "label": "Empatía", "value": 42}],
            "lease": {"state": "available", "ownerCode": None, "expiresAt": None},
            "latestReview": None,
        }],
        "total": 1, "limit": 10,
    }


def review_payload():
    return {
        "reviewId": "66666666-6666-4666-8666-666666666666",
        "caseId": CASE_ID, "reviewNo": 1, "reviewerCode": "EXP-12345678",
        "isCurrent": True, "supersedesReviewId": None, "submittedAt": NOW,
        "contentRevision": 2, "overallComment": "Observación experta.",
        "rubricCorrections": [{
            "areaKey": "expression", "aiValue": 85, "correctedValue": 82,
            "comment": "Ajuste justificado.",
        }],
        "metricCorrections": [],
    }


def valid_review_request():
    return {
        "leaseToken": "x" * 32, "leaseGeneration": 1,
        "expectedContentRevision": 1,
        "idempotencyKey": "55555555-5555-4555-8555-555555555555",
        "supersedesReviewId": None, "overallComment": "Observación experta.",
        "rubricCorrections": [{
            "areaId": "44444444-4444-4444-8444-444444444444",
            "correctedValue": 82, "comment": "Ajuste justificado.",
        }],
        "metricCorrections": [],
    }


def test_role_matrix_and_v1_alias(client, monkeypatch):
    monkeypatch.setattr(labeling_api.labeling_store, "list_cases", lambda *_args, **_kwargs: list_payload())
    for role in ("spokesperson", "client_admin"):
        response = client.get("/api/master/labeling-cases", headers=auth(role))
        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "MASTER_ROLE_REQUIRED"
    assert client.get("/api/master/labeling-cases", headers=auth()).status_code == 200
    assert client.get("/v1/api/master/labeling-cases", headers=auth()).status_code == 200


def test_query_validation_is_problem_json(client):
    response = client.get("/api/master/labeling-cases?limit=11", headers=auth())
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.headers["content-type"].startswith("application/problem+json")


def test_store_conflict_has_stable_problem_contract(client, monkeypatch):
    def conflict(*_args, **_kwargs):
        raise labeling_api.labeling_store.LabelingStoreError(
            "LEASE_CONFLICT", "Otro experto posee la reserva activa.",
            status=409, context={"expiresAt": NOW},
        )
    monkeypatch.setattr(labeling_api.labeling_store, "acquire_lease", conflict)
    response = client.post(
        f"/api/master/labeling-cases/{CASE_ID}/lease",
        headers=auth(), json={"leaseToken": None, "leaseGeneration": None},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "LEASE_CONFLICT"
    assert body["context"]["expiresAt"].endswith("Z")
    assert "token" not in str(body).lower()


def test_review_creation_and_idempotent_replay(client, monkeypatch):
    calls = iter((False, True))

    def submit(*_args, **_kwargs):
        return {"replayed": next(calls), "review": review_payload()}

    monkeypatch.setattr(labeling_api.labeling_store, "submit_review", submit)
    url = f"/api/master/labeling-cases/{CASE_ID}/reviews"
    assert client.post(url, headers=auth(), json=valid_review_request()).status_code == 201
    replay = client.post(url, headers=auth(), json=valid_review_request())
    assert replay.status_code == 200
    assert replay.json()["reviewId"] == review_payload()["reviewId"]


def test_review_rejects_server_owned_fields(client):
    payload = valid_review_request()
    payload["reviewerId"] = ACTOR_ID
    response = client.post(
        f"/api/master/labeling-cases/{CASE_ID}/reviews",
        headers=auth(), json=payload,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_recording_url_is_short_lived_no_store_and_audited(client, monkeypatch):
    audited = []
    monkeypatch.setattr(
        labeling_api.labeling_store, "audit_recording_access",
        lambda *_args, **kwargs: audited.append(kwargs),
    )
    response = client.get(
        f"/api/master/labeling-cases/{CASE_ID}/recording-url", headers=auth()
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["expiresAt"].endswith("Z")
    assert response.json()["url"].startswith("https://storage.invalid/")
    assert audited and "url" not in audited[0]


def test_recording_not_found_maps_to_410(client, monkeypatch):
    class ResourceNotFoundError(Exception):
        pass

    monkeypatch.setattr(labeling_api, "_LABELING_RECORDING_URL", lambda *_: (_ for _ in ()).throw(ResourceNotFoundError()))
    response = client.get(
        f"/api/master/labeling-cases/{CASE_ID}/recording-url", headers=auth()
    )
    assert response.status_code == 410
    assert response.json()["code"] == "RECORDING_RETAINED_OR_DELETED"


def test_openapi_excludes_internal_columns_and_server_owned_review_fields(client):
    serialized = str(client.get("/openapi.json").json()).lower()
    for forbidden in (
        "lock_token_hash", "recording_evidence_path", "recording_sha256",
        "analysis_job_id", "client_id", "speaker_id",
    ):
        assert forbidden not in serialized
    review_schema = client.get("/openapi.json").json()["components"]["schemas"]["ReviewRequest"]
    properties = review_schema["properties"]
    assert not {"aiValue", "reviewerId", "status", "submittedAt", "isCurrent"} & set(properties)
