"""Auth flow tests: 401 unauthorized, 403 forbidden, dev tokens."""
from tests.conftest import ADMIN_EMAIL, MASTER_EMAIL, VOCERO_EMAIL, auth, token_for


async def test_me_without_token_returns_401_problem_details(client):
    response = await client.get("/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "x-correlation-id" in response.headers
    body = response.json()
    assert body["title"] == "unauthorized"
    assert body["status"] == 401
    assert body["correlationId"]


async def test_me_with_invalid_token_returns_401(client):
    response = await client.get("/v1/me", headers=auth("token-falso"))
    assert response.status_code == 401
    assert response.json()["title"] == "unauthorized"


async def test_me_with_dev_token_returns_profile(client):
    token = await token_for(client, VOCERO_EMAIL)
    response = await client.get("/v1/me", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == VOCERO_EMAIL
    assert body["role"] == "spokesperson"
    assert body["clientId"]
    assert body["preferredLanguage"] == "es"


async def test_spokesperson_cannot_manage_topics_returns_403(client):
    token = await token_for(client, VOCERO_EMAIL)
    response = await client.post(
        "/v1/topics",
        json={
            "name": "X",
            "context": "Y",
            "optics": "formal",
            "audience": "leadership",
            "languages": ["es"],
            "keyMessages": ["msg"],
        },
        headers=auth(token),
    )
    assert response.status_code == 403
    assert response.json()["title"] == "forbidden"


async def test_client_admin_cannot_access_master_rubric_returns_403(client):
    token = await token_for(client, ADMIN_EMAIL)
    response = await client.get("/v1/master/rubric", headers=auth(token))
    assert response.status_code == 403


async def test_master_can_access_master_dashboard(client):
    token = await token_for(client, MASTER_EMAIL)
    response = await client.get("/v1/master/dashboard", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["activeClients"] == 1
    assert len(body["scoreDistribution"]) == 5
