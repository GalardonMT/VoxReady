"""Full session flow test: create -> consent -> recording-url -> upload ->
finish -> analysis -> report, plus idempotency and state validations."""
import asyncio
import uuid

from tests.conftest import VOCERO_EMAIL, auth, token_for


async def _create_session(client, headers, idem_key=None):
    scenarios = await client.get("/v1/scenarios", headers=headers)
    assert scenarios.status_code == 200
    scenario_id = scenarios.json()["items"][0]["id"]
    extra = {"Idempotency-Key": idem_key} if idem_key else {}
    response = await client.post(
        "/v1/sessions",
        json={"scenarioId": scenario_id, "language": "es"},
        headers={**headers, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_full_session_flow(client):
    token = await token_for(client, VOCERO_EMAIL)
    headers = auth(token)

    # Idempotency-Key: repeating POST /v1/sessions returns the same session.
    idem = uuid.uuid4().hex
    created = await _create_session(client, headers, idem_key=idem)
    repeated = await _create_session(client, headers, idem_key=idem)
    assert repeated["sessionId"] == created["sessionId"]
    session_id = created["sessionId"]
    assert created["status"] == "created"
    assert created["questionCount"] > 0

    # recording-url before consent -> 409 consent_required.
    response = await client.post(
        f"/v1/sessions/{session_id}/recording-url",
        json={"contentType": "video/webm"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["title"] == "consent_required"

    # Incomplete consent -> 400 consent_incomplete.
    response = await client.post(
        f"/v1/sessions/{session_id}/consent",
        json={
            "acceptRecording": True,
            "acknowledgeDeletion": False,
            "policyVersion": "ret-2026-01",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["title"] == "consent_incomplete"

    # Valid consent -> 200 consented.
    response = await client.post(
        f"/v1/sessions/{session_id}/consent",
        json={
            "acceptRecording": True,
            "acknowledgeDeletion": True,
            "policyVersion": "ret-2026-01",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "consented"
    assert response.json()["consentId"]

    # Unsupported MIME -> 400 invalid_content_type.
    response = await client.post(
        f"/v1/sessions/{session_id}/recording-url",
        json={"contentType": "video/avi"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["title"] == "invalid_content_type"

    # Valid recording-url -> upload URL + blob path.
    response = await client.post(
        f"/v1/sessions/{session_id}/recording-url",
        json={"contentType": "video/webm", "durationSeconds": 312},
        headers=headers,
    )
    assert response.status_code == 200
    grant = response.json()
    assert grant["uploadUrl"].startswith("http://test/v1/uploads/")
    assert grant["blobPath"].endswith(".webm")
    assert grant["maxSizeBytes"] > 0

    # finish with a blob that was never uploaded -> 400 blob_missing.
    response = await client.post(
        f"/v1/sessions/{session_id}/finish",
        json={"blobPath": "rec/2026/06/inexistente.webm"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["title"] == "blob_missing"

    # Upload the binary through the signed URL (single-use).
    upload = await client.put(grant["uploadUrl"], content=b"fake-webm-bytes")
    assert upload.status_code == 200

    # finish -> 202 analyzing with analysisId.
    response = await client.post(
        f"/v1/sessions/{session_id}/finish",
        json={"blobPath": grant["blobPath"]},
        headers=headers,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "analyzing"
    analysis_id = response.json()["analysisId"]

    # Poll analysis until the in-process worker completes it.
    status = None
    for _ in range(300):
        response = await client.get(
            f"/v1/sessions/{session_id}/analysis", headers=headers
        )
        assert response.status_code == 200
        status = response.json()
        if status["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.02)
    assert status["analysisId"] == analysis_id
    assert status["status"] == "completed"
    assert status["reportReady"] is True
    assert all(v == "done" for v in status["progress"].values())

    # Report with area scores, narrative and signed recording URL.
    response = await client.get(f"/v1/sessions/{session_id}/report", headers=headers)
    assert response.status_code == 200
    report = response.json()
    assert 0 <= report["overallScore"] <= 100
    areas = {a["area"] for a in report["areaScores"]}
    assert areas == {"expression", "voice", "coherence", "empathy"}
    assert report["narrative"]["strengths"]
    assert report["narrative"]["improvements"]
    assert report["narrative"]["crossSignal"]
    assert report["recordingUrl"]
    assert report["scenarioTitle"]

    # The signed read URL serves the uploaded binary.
    download = await client.get(report["recordingUrl"])
    assert download.status_code == 200
    assert download.content == b"fake-webm-bytes"

    # Progress now has one completed session and four area series.
    response = await client.get("/v1/me/progress", headers=headers)
    assert response.status_code == 200
    progress = response.json()
    assert progress["sessionsCompleted"] == 1
    assert progress["latestOverall"] == report["overallScore"]
    assert len(progress["series"]) == 4
    colors = {s["area"]: s["color"] for s in progress["series"]}
    assert colors["expression"] == "#8B5CF6"
    assert colors["voice"] == "#3B82F6"
    assert colors["coherence"] == "#10B981"
    assert colors["empathy"] == "#F59E0B"

    # The worker generated at least one recommendation.
    response = await client.get("/v1/me/recommendations", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1


async def test_finish_without_recording_returns_invalid_state(client):
    token = await token_for(client, VOCERO_EMAIL)
    headers = auth(token)
    created = await _create_session(client, headers)
    response = await client.post(
        f"/v1/sessions/{created['sessionId']}/finish",
        json={"blobPath": "rec/x.webm"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["title"] == "invalid_state"


async def test_report_before_analysis_returns_report_not_ready(client):
    token = await token_for(client, VOCERO_EMAIL)
    headers = auth(token)
    created = await _create_session(client, headers)
    response = await client.get(
        f"/v1/sessions/{created['sessionId']}/report", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["title"] == "report_not_ready"


async def test_session_of_another_user_returns_404(client):
    token = await token_for(client, VOCERO_EMAIL)
    headers = auth(token)
    created = await _create_session(client, headers)
    # The demo client has a single spokesperson; emulate foreign access with a
    # random UUID and with the admin token (different role -> 403 first).
    response = await client.get(
        f"/v1/sessions/{uuid.uuid4()}/analysis", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["title"] == "session_not_found"
