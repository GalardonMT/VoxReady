"""Flujo real de microlecciones sobre Azure SQL; todos los cambios se revierten."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import main

pytestmark = pytest.mark.skipif(os.getenv('VOXREADY_TEST_AZURE_SQL') != '1', reason='Azure SQL integration is opt-in')


@pytest.fixture
def microlesson_api(monkeypatch):
    spec = importlib.util.spec_from_file_location('seed', BACKEND / 'scripts' / 'seed_master_topics.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    conn = seed.connect()
    cursor = conn.cursor()
    cursor.execute('SET XACT_ABORT OFF; IF @@TRANCOUNT=0 BEGIN TRANSACTION;')
    cursor.execute('SELECT TOP 1 id,topic_id FROM dbo.scenario WHERE client_id=? AND status=\'active\' AND is_deleted=0', seed.DEMO_CLIENT_ID)
    demo_scenario, topic_id = cursor.fetchone()
    other_client = str(uuid.uuid4())
    other_scenario = str(uuid.uuid4())
    cursor.execute("INSERT INTO dbo.client(id,name,status) VALUES(?,'Cliente externo prueba','active')", other_client)
    cursor.execute("""INSERT INTO dbo.scenario(id,topic_id,client_id,title,category,difficulty,estimated_minutes,question_count,status)
                      VALUES(?,?,?,'Escenario externo','operational','basic',5,0,'active')""", other_scenario, topic_id, other_client)
    users = {name: str(uuid.uuid4()) for name in ('master', 'speaker', 'admin', 'outsider')}
    roles = {'master': 'master_config', 'speaker': 'spokesperson', 'admin': 'client_admin', 'outsider': 'spokesperson'}
    for name, user_id in users.items():
        cursor.execute("INSERT INTO dbo.app_user(id,client_id,email,display_name,role) VALUES(?,?,?,?,?)", user_id,
                       None if name == 'master' else other_client if name == 'outsider' else seed.DEMO_CLIENT_ID,
                       user_id + '@example.invalid', 'Prueba microleccion', roles[name])
    current = {'name': 'master'}

    @contextmanager
    def transactional_database(_):
        request_cursor = conn.cursor()
        request_cursor.execute('SAVE TRANSACTION microlesson_request')
        try:
            yield request_cursor
        except Exception:
            request_cursor.execute('ROLLBACK TRANSACTION microlesson_request')
            raise
        finally:
            request_cursor.close()

    monkeypatch.setattr(main.master_store, 'database', transactional_database)
    main.app.dependency_overrides[main.verify_token] = lambda: {'sub': users[current['name']]}
    storage = MagicMock()
    service = storage.from_connection_string.return_value
    service.account_name = 'test-account'
    service.credential.account_key = 'test-key'
    blob = service.get_container_client.return_value.get_blob_client.return_value
    blob.get_blob_properties.return_value = SimpleNamespace(size=128, content_settings=SimpleNamespace(content_type='video/mp4'))
    blob.exists.return_value = True
    monkeypatch.setattr(main, 'STORAGE_CONN_STR', 'test-storage')
    monkeypatch.setattr(main, 'BlobServiceClient', storage)
    monkeypatch.setattr(main, 'generate_blob_sas', lambda **_: 'temporary-sas')
    try:
        with TestClient(main.app) as client:
            yield client, current, str(demo_scenario), other_scenario, seed, service
    finally:
        main.app.dependency_overrides.clear()
        conn.rollback()
        conn.close()


def payload(client_id, scenario_id, title='Tecnica de prueba', status='active'):
    return {'clientId': client_id, 'scenarioId': scenario_id, 'title': title, 'topicTag': 'bridging',
            'durationMinutes': 4, 'learningObjective': 'Aprender a redirigir preguntas.',
            'theoryContent': 'Reconocer, transicionar y entregar el mensaje clave.',
            'exampleContent': 'Caso comentado de prueba.', 'status': status}


def test_seed_identities_and_role_endpoints():
    expected = {
        'elena.diaz@voxready.ai': 'master_config',
        'ana.torres@acme-corp.com': 'spokesperson',
        'carlos.ruiz@acme-corp.com': 'client_admin',
    }
    with TestClient(main.app) as client:
        tokens = {}
        for email, role in expected.items():
            response = client.post('/v1/dev/token', json={'email': email.upper()})
            assert response.status_code == 200, response.text
            tokens[email] = response.json()['accessToken']
            profile = client.get('/v1/me', headers={'Authorization': 'Bearer ' + tokens[email]})
            assert profile.status_code == 200, profile.text
            assert profile.json()['email'].casefold() == email.casefold()
            assert profile.json()['role'] == role

        master_headers = {'Authorization': 'Bearer ' + tokens['elena.diaz@voxready.ai']}
        assert client.get('/v1/api/master/microlessons/clients', headers=master_headers).status_code == 200
        assert client.get('/v1/api/master/microlessons', headers=master_headers).status_code == 200

        speaker_headers = {'Authorization': 'Bearer ' + tokens['ana.torres@acme-corp.com']}
        assert client.get('/v1/microlessons', headers=speaker_headers).status_code == 200
        assert client.get('/v1/api/master/microlessons', headers=speaker_headers).status_code == 403

        admin_headers = {'Authorization': 'Bearer ' + tokens['carlos.ruiz@acme-corp.com']}
        assert client.get('/v1/api/master/microlessons', headers=admin_headers).status_code == 403
        assert client.get('/v1/microlessons', headers=admin_headers).status_code == 403
        assert client.post('/v1/dev/token', json={'email': 'missing@example.invalid'}).status_code == 404


def test_master_crud_video_status_and_role_permissions(microlesson_api):
    client, current, scenario_id, _, seed, service = microlesson_api
    created = client.post('/api/master/microlessons', json=payload(seed.DEMO_CLIENT_ID, scenario_id))
    assert created.status_code == 201, created.text
    lesson = created.json()
    assert lesson['hasVideo'] is False
    no_video = client.post('/api/master/microlessons', json=payload(seed.DEMO_CLIENT_ID, scenario_id, 'Sin video'))
    assert no_video.status_code == 201 and no_video.json()['hasVideo'] is False
    changed = payload(seed.DEMO_CLIENT_ID, scenario_id, 'Contenido editado')
    changed['theoryContent'] = 'Teoria actualizada.'
    assert client.put(f"/api/master/microlessons/{lesson['id']}", json=changed).json()['theoryContent'] == 'Teoria actualizada.'

    ticket = client.post(f"/api/master/microlessons/{lesson['id']}/video-upload-url",
                         json={'fileName': 'Mi video.mp4', 'contentType': 'video/mp4', 'sizeBytes': 128})
    assert ticket.status_code == 200 and 'temporary-sas' in ticket.json()['uploadUrl']
    final = client.put(f"/api/master/microlessons/{lesson['id']}/video", json={
        'blobPath': ticket.json()['blobPath'], 'fileName': ticket.json()['fileName'],
        'contentType': 'video/mp4', 'sizeBytes': 128})
    assert final.status_code == 200 and final.json()['hasVideo'] is True
    second_ticket = client.post(f"/api/master/microlessons/{lesson['id']}/video-upload-url",
                                json={'fileName': 'reemplazo.mp4', 'contentType': 'video/mp4', 'sizeBytes': 128}).json()
    assert client.put(f"/api/master/microlessons/{lesson['id']}/video", json={
        'blobPath': second_ticket['blobPath'], 'fileName': second_ticket['fileName'],
        'contentType': 'video/mp4', 'sizeBytes': 128}).status_code == 200
    assert service.get_container_client.return_value.delete_blob.called
    removed = client.delete(f"/api/master/microlessons/{lesson['id']}/video")
    assert removed.status_code == 200 and removed.json()['hasVideo'] is False
    assert client.patch(f"/api/master/microlessons/{lesson['id']}/status", json={'status': 'archived'}).json()['status'] == 'archived'
    assert client.patch(f"/api/master/microlessons/{lesson['id']}/status", json={'status': 'active'}).json()['status'] == 'active'
    current['name'] = 'admin'
    assert client.post('/api/master/microlessons', json=changed).status_code == 403
    assert client.put(f"/api/master/microlessons/{lesson['id']}", json=changed).status_code == 403


def test_client_scenario_validation_and_spokesperson_visibility(microlesson_api):
    client, current, scenario_id, other_scenario, seed, _ = microlesson_api
    scenarios = client.get(f'/api/master/microlessons/clients/{seed.DEMO_CLIENT_ID}/scenarios').json()['items']
    assert scenario_id in [item['id'] for item in scenarios]
    assert other_scenario not in [item['id'] for item in scenarios]
    assert client.post('/api/master/microlessons', json=payload(seed.DEMO_CLIENT_ID, other_scenario)).status_code == 422
    active = client.post('/api/master/microlessons', json=payload(seed.DEMO_CLIENT_ID, scenario_id)).json()
    archived = client.post('/api/master/microlessons', json=payload(seed.DEMO_CLIENT_ID, scenario_id, 'Archivada', 'archived')).json()
    current['name'] = 'speaker'
    visible = client.get('/v1/microlessons')
    assert visible.status_code == 200
    ids = [item['id'] for item in visible.json()['items']]
    assert active['id'] in ids and archived['id'] not in ids
    assert client.get(f"/v1/microlessons/{active['id']}").status_code == 200
    assert client.get(f"/v1/microlessons/{archived['id']}").status_code == 404
    current['name'] = 'outsider'
    assert client.get('/v1/microlessons').json()['items'] == []
    assert client.get(f"/v1/microlessons/{active['id']}").status_code == 404
    current['name'] = 'admin'
    assert client.get('/v1/microlessons').status_code == 403
