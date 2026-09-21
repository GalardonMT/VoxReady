"""Retention policy tests: invalid_policy and version rotation."""
from tests.conftest import ADMIN_EMAIL, auth, token_for


async def _client_id(client, headers) -> str:
    me = await client.get("/v1/me", headers=headers)
    return me.json()["clientId"]


async def test_retention_full_recording_requires_term_days(client):
    token = await token_for(client, ADMIN_EMAIL)
    headers = auth(token)
    client_id = await _client_id(client, headers)

    response = await client.put(
        f"/v1/clients/{client_id}/retention-policy",
        json={"keep": "full_recording"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["title"] == "invalid_policy"

    response = await client.put(
        f"/v1/clients/{client_id}/retention-policy",
        json={"keep": "full_recording", "termDays": 0},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["title"] == "invalid_policy"


async def test_retention_policy_version_rotation(client):
    token = await token_for(client, ADMIN_EMAIL)
    headers = auth(token)
    client_id = await _client_id(client, headers)

    # Seed policy.
    response = await client.get(
        f"/v1/clients/{client_id}/retention-policy", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["keep"] == "full_recording"
    assert response.json()["termDays"] == 90
    assert response.json()["version"] == "ret-2026-01"

    # New version with another term.
    response = await client.put(
        f"/v1/clients/{client_id}/retention-policy",
        json={"keep": "full_recording", "termDays": 30},
        headers=headers,
    )
    assert response.status_code == 200
    new_version = response.json()["version"]
    assert new_version != "ret-2026-01"
    assert response.json()["termDays"] == 30

    # metrics_only clears termDays and creates another version.
    response = await client.put(
        f"/v1/clients/{client_id}/retention-policy",
        json={"keep": "metrics_only"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["keep"] == "metrics_only"
    assert response.json()["termDays"] is None

    # The current policy is the last one written.
    response = await client.get(
        f"/v1/clients/{client_id}/retention-policy", headers=headers
    )
    assert response.json()["keep"] == "metrics_only"
    assert response.json()["termDays"] is None


async def test_retention_policy_of_other_client_forbidden(client):
    token = await token_for(client, ADMIN_EMAIL)
    headers = auth(token)
    other_client = "99999999-9999-4999-8999-999999999999"
    response = await client.get(
        f"/v1/clients/{other_client}/retention-policy", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["title"] == "client_not_found"
