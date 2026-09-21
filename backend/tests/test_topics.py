"""Topic CRUD tests (client admin) with archive-on-sessions rule."""
from tests.conftest import ADMIN_EMAIL, VOCERO_EMAIL, auth, token_for

TOPIC_BODY = {
    "name": "Nueva crisis",
    "context": "Contexto de prueba del tema.",
    "optics": "formal",
    "audience": "leadership",
    "languages": ["es", "en"],
    "keyMessages": ["Mensaje clave 1", "Mensaje clave 2"],
    "redLines": ["Línea roja 1"],
}


async def test_topics_crud(client):
    token = await token_for(client, ADMIN_EMAIL)
    headers = auth(token)

    # Create.
    response = await client.post("/v1/topics", json=TOPIC_BODY, headers=headers)
    assert response.status_code == 201, response.text
    topic_id = response.json()["id"]

    # List contains the new topic.
    response = await client.get("/v1/topics", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 4  # 3 seed topics + the new one
    mine = [t for t in body["items"] if t["id"] == topic_id]
    assert mine and mine[0]["keyMessages"] == TOPIC_BODY["keyMessages"]
    assert mine[0]["redLines"] == TOPIC_BODY["redLines"]
    assert mine[0]["retentionDays"] == 90

    # Update (full replacement).
    updated = {**TOPIC_BODY, "name": "Crisis actualizada", "keyMessages": ["Solo uno"]}
    response = await client.put(
        f"/v1/topics/{topic_id}", json=updated, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == topic_id

    # Validation error -> 400 validation_error.
    response = await client.post(
        "/v1/topics", json={"name": "incompleto"}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["title"] == "validation_error"

    # Delete without sessions -> 204 and the topic disappears.
    response = await client.delete(f"/v1/topics/{topic_id}", headers=headers)
    assert response.status_code == 204
    response = await client.get("/v1/topics", headers=headers)
    assert all(t["id"] != topic_id for t in response.json()["items"])

    # Unknown topic -> 404 topic_not_found.
    response = await client.delete(f"/v1/topics/{topic_id}", headers=headers)
    assert response.status_code == 404
    assert response.json()["title"] == "topic_not_found"


async def test_delete_topic_with_sessions_archives_it(client):
    vocero = await token_for(client, VOCERO_EMAIL)
    scenarios = await client.get("/v1/scenarios", headers=auth(vocero))
    scenario = next(
        s for s in scenarios.json()["items"] if "retiro" in s["title"].lower()
    )
    created = await client.post(
        "/v1/sessions",
        json={"scenarioId": scenario["id"]},
        headers=auth(vocero),
    )
    assert created.status_code == 201

    admin = await token_for(client, ADMIN_EMAIL)
    response = await client.get("/v1/topics", headers=auth(admin))
    topic = next(
        t for t in response.json()["items"] if t["name"] == "Retiro de producto"
    )
    response = await client.delete(f"/v1/topics/{topic['id']}", headers=auth(admin))
    assert response.status_code == 204

    # The topic is archived, still listed.
    response = await client.get("/v1/topics", headers=auth(admin))
    archived = next(t for t in response.json()["items"] if t["id"] == topic["id"])
    assert archived["status"] == "archived"
