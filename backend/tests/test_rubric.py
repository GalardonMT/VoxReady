"""Master rubric tests: weight validation, draft save and publish."""
from tests.conftest import MASTER_EMAIL, auth, token_for

AREAS_OK = [
    {
        "name": "Expresión",
        "channel": "imagen/no verbal",
        "criteria": "Contacto visual y gestos.",
        "weight": 30,
        "descriptors": {"high": "Alto", "medium": "Medio", "low": "Bajo"},
    },
    {
        "name": "Voz",
        "channel": "voz/prosodia",
        "criteria": "Ritmo y tono.",
        "weight": 30,
        "descriptors": {"high": "Alto", "medium": "Medio", "low": "Bajo"},
    },
    {
        "name": "Coherencia",
        "channel": "contenido",
        "criteria": "Mensajes clave.",
        "weight": 20,
        "descriptors": {"high": "Alto", "medium": "Medio", "low": "Bajo"},
    },
    {
        "name": "Empatía",
        "channel": "señal cruzada",
        "criteria": "Reconocimiento emocional.",
        "weight": 20,
        "descriptors": {"high": "Alto", "medium": "Medio", "low": "Bajo"},
    },
]


async def test_rubric_weights_must_sum_100(client):
    token = await token_for(client, MASTER_EMAIL)
    bad = [{**a, "weight": 10} for a in AREAS_OK]  # sums 40
    response = await client.put(
        "/v1/master/rubric",
        json={"areas": bad, "languages": ["es"]},
        headers=auth(token),
    )
    assert response.status_code == 400
    assert response.json()["title"] == "weights_sum_invalid"


async def test_rubric_draft_and_publish_flow(client):
    token = await token_for(client, MASTER_EMAIL)
    headers = auth(token)

    # Current published rubric is v0.4 with 4 areas.
    response = await client.get("/v1/master/rubric", headers=headers)
    assert response.status_code == 200
    assert response.json()["version"] == "v0.4"
    assert len(response.json()["areas"]) == 4

    # Save a valid draft.
    response = await client.put(
        "/v1/master/rubric",
        json={"areas": AREAS_OK, "languages": ["es", "en"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["status"] == "draft"
    version = draft["version"]

    # Unknown version -> 404 version_not_found.
    response = await client.post(
        "/v1/master/rubric/publish",
        json={"version": "v9.9"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["title"] == "version_not_found"

    # Publish the draft.
    response = await client.post(
        "/v1/master/rubric/publish",
        json={"version": version, "reevaluate": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["publishedAt"]

    # Publishing again -> 409 already_published.
    response = await client.post(
        "/v1/master/rubric/publish",
        json={"version": version},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["title"] == "already_published"

    # The new version is now the current one.
    response = await client.get("/v1/master/rubric", headers=headers)
    assert response.json()["version"] == version
