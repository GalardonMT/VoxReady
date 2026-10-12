"""Prueba real de Azure SQL, opt-in. Todas las altas de prueba se revierten.

VOXREADY_TEST_AZURE_SQL=1 python -m pytest backend/tests/test_master_topics_azure.py
La autenticación se simula; autorización y persistencia se ejecutan realmente.
"""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import main

pytestmark = pytest.mark.skipif(os.getenv('VOXREADY_TEST_AZURE_SQL') != '1', reason='Azure SQL integration is opt-in')


@pytest.fixture
def azure_api(monkeypatch):
    spec = importlib.util.spec_from_file_location('seed', BACKEND / 'scripts' / 'seed_master_topics.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    conn = seed.connect()
    cursor = conn.cursor()
    cursor.execute('SET XACT_ABORT OFF; IF @@TRANCOUNT=0 BEGIN TRANSACTION;')
    users = {role: str(uuid.uuid4()) for role in ('master', 'speaker', 'colleague', 'outsider')}
    other_client = str(uuid.uuid4())
    cursor.execute("INSERT INTO dbo.client(id,name,status) VALUES(?,'Prueba transaccional sin persistencia','active')", other_client)
    for label, user_id in users.items():
        cursor.execute("INSERT INTO dbo.app_user(id,client_id,email,display_name,role) VALUES(?,?,?,?,?)", user_id,
                       other_client if label == 'outsider' else seed.DEMO_CLIENT_ID,
                       user_id + '@example.invalid', 'Prueba transaccional', 'master_config' if label == 'master' else 'spokesperson')
    current = {'label': 'master'}

    @contextmanager
    def transactional_database(_):
        request_cursor = conn.cursor()
        request_cursor.execute('SAVE TRANSACTION test_request')
        try:
            yield request_cursor
        except Exception:
            request_cursor.execute('ROLLBACK TRANSACTION test_request')
            raise
        finally:
            request_cursor.close()

    monkeypatch.setattr(main.master_store, 'database', transactional_database)
    main.app.dependency_overrides[main.verify_token] = lambda: {'sub': users[current['label']]}
    try:
        with TestClient(main.app) as client:
            yield client, current, cursor, seed
    finally:
        main.app.dependency_overrides.clear()
        conn.rollback()
        conn.close()


def test_master_workflow_integrity_and_authorization(azure_api):
    client, current, cursor, seed = azure_api
    current['label'] = 'speaker'
    assert client.get('/api/master/topics').status_code == 403
    current['label'] = 'master'
    clients = client.get('/v1/api/master/clients')
    assert clients.status_code == 200
    assert any(c['id'].lower() == seed.DEMO_CLIENT_ID.lower() for c in clients.json()['items'])
    payload = {'name': 'Prueba fase 2', 'context': 'Contexto de prueba', 'optics': 'empathetic',
               'audience': 'leadership', 'keyMessages': ['Mensaje uno', 'Mensaje dos'], 'redLines': ['Línea uno'],
               'questions': [f'Pregunta {i}' for i in range(1, 13)]}
    response = client.post('/api/master/topics', json=payload)
    assert response.status_code == 201, response.text
    topic = response.json()
    assert len(topic['questions']) == 12
    topic_id = topic['id']
    ids = [q['id'] for q in topic['questions']]
    selected = [ids[8], ids[2], ids[11], ids[0]]
    scenario_payload = {'title': 'Prueba orden arbitrario', 'category': 'operational', 'difficulty': 'basic',
                        'estimatedMinutes': 7, 'clientId': seed.DEMO_CLIENT_ID, 'questionIds': selected}
    response = client.post(f'/api/master/topics/{topic_id}/scenarios', json=scenario_payload)
    assert response.status_code == 201, response.text
    scenario = response.json()
    scenario_id = scenario['id']
    assert [q['id'] for q in scenario['questions']] == selected
    scenario_payload['questionIds'] = [ids[4], ids[11], ids[2], ids[0]]
    response = client.put(f'/api/master/scenarios/{scenario_id}', json=scenario_payload)
    assert response.status_code == 200, response.text
    assert response.json()['questionIds'] == scenario_payload['questionIds']
    cursor.execute('SELECT COUNT(*) FROM dbo.scenario_question WHERE scenario_id=?', scenario_id)
    assert cursor.fetchone()[0] == 5  # relación retirada preservada
    cursor.execute("SELECT COUNT(*) FROM dbo.scenario_question WHERE scenario_id=? AND status='archived'", scenario_id)
    assert cursor.fetchone()[0] == 1
    payload['questions'] = [{'id': q['id'], 'text': q['text']} for q in topic['questions'][1:]]
    payload['questions'][0]['text'] = 'Pregunta editada conservando identidad'
    payload['questions'].append('Pregunta nueva sin límite artificial')
    payload['keyMessages'] = ['Mensaje actualizado']
    payload['redLines'] = []
    response = client.put(f'/api/master/topics/{topic_id}', json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()['questions']) == 12
    cursor.execute('SELECT status,in_bank FROM dbo.question WHERE id=?', ids[0])
    assert tuple(cursor.fetchone()) == ('archived', False)
    cursor.execute('SELECT COUNT(*) FROM dbo.question WHERE topic_id=?', topic_id)
    assert cursor.fetchone()[0] == 13
    cursor.execute("SELECT COUNT(*) FROM dbo.topic_key_message WHERE topic_id=? AND status='archived'", topic_id)
    assert cursor.fetchone()[0] == 1
    # Una pregunta retirada del banco sigue perteneciendo al escenario previamente configurado.
    assert client.get(f'/api/master/topics/{topic_id}').json()['scenarios'][0]['questionIds'] == scenario_payload['questionIds']
    bad_payload = {**payload, 'name': 'Cambio que debe revertirse', 'questions': [{'id': str(uuid.uuid4()), 'text': 'Ajena'}]}
    assert client.put(f'/api/master/topics/{topic_id}', json=bad_payload).status_code == 422
    assert client.get(f'/api/master/topics/{topic_id}').json()['name'] == payload['name']
    for status in ('archived', 'active'):
        response = client.patch(f'/api/master/topics/{topic_id}/status', json={'status': status})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == status
        assert all(s['status'] == status for s in response.json()['scenarios'])
    assert client.patch(f'/api/master/scenarios/{scenario_id}/status', json={'status': 'archived'}).json()['status'] == 'archived'
    assert client.patch(f'/api/master/scenarios/{scenario_id}/status', json={'status': 'active'}).json()['status'] == 'active'
    assert client.patch(f'/api/master/topics/{topic_id}/status', json={'status': 'archived'}).status_code == 200
    assert client.patch(f'/api/master/scenarios/{scenario_id}/status', json={'status': 'active'}).status_code == 409
    assert client.post('/api/master/topics', json={**payload, 'optics': 'Empática'}).status_code == 422
    assert client.post(f'/api/master/topics/{topic_id}/scenarios', json={**scenario_payload, 'questionIds': [ids[1], ids[1]]}).status_code == 422
    assert client.get('/api/master/topics?status=all').status_code == 200
    assert client.get('/api/master/topics?status=unknown').status_code == 422


def test_company_visibility_persistent_sessions_and_snapshot(azure_api):
    client, current, cursor, seed = azure_api
    topic_payload = {'name': 'Prueba fase 3', 'context': 'Entrevista ordenada', 'optics': 'technical',
                     'audience': 'frontline', 'questions': [f'Pregunta {i}' for i in range(1, 13)]}
    topic = client.post('/api/master/topics', json=topic_payload).json()
    ids = [q['id'] for q in topic['questions']]
    selected = [ids[9], ids[3], ids[11], ids[1]]
    scenario_payload = {'title': 'Entrevista por empresa', 'category': 'health', 'difficulty': 'hard',
                        'estimatedMinutes': 10, 'clientId': seed.DEMO_CLIENT_ID, 'questionIds': selected}
    response = client.post(f"/api/master/topics/{topic['id']}/scenarios", json=scenario_payload)
    assert response.status_code == 201, response.text
    scenario = response.json()
    current['label'] = 'speaker'
    catalog = client.get('/v1/scenarios').json()
    assert scenario['id'] in [s['id'] for s in catalog['items']]
    first = client.get('/scenarios?page=1&pageSize=1').json()
    assert len(first['items']) == 1 and first['total'] >= 4
    assert client.get('/scenarios?page=0').status_code == 422
    assert client.get('/scenarios?q=Entrevista%20por%20empresa').json()['total'] == 1
    key = str(uuid.uuid4())
    request = {'scenarioId': scenario['id'], 'language': 'es'}
    response = client.post('/v1/sessions', json=request, headers={'Idempotency-Key': key})
    assert response.status_code == 201, response.text
    session = response.json()
    assert session['questionCount'] == 4
    assert client.post('/v1/sessions', json=request, headers={'Idempotency-Key': key}).json()['sessionId'] == session['sessionId']
    assert client.post('/v1/sessions', json={**request, 'language': 'en'}, headers={'Idempotency-Key': key}).status_code == 409
    setup = client.get(f"/sessions/{session['sessionId']}").json()
    assert [q['id'] for q in setup['questions']] == selected
    assert [q['sequenceNo'] for q in setup['questions']] == [1, 2, 3, 4]
    cursor.execute('SELECT COUNT(*) FROM dbo.session WHERE external_session_id=?', session['sessionId'])
    assert cursor.fetchone()[0] == 1
    current['label'] = 'colleague'
    assert client.get('/v1/scenarios').json() == catalog
    assert client.get(f"/sessions/{session['sessionId']}").status_code == 404
    current['label'] = 'outsider'
    assert client.get('/v1/scenarios').json()['items'] == []
    assert client.get(f"/scenarios/{scenario['id']}").status_code == 404
    assert client.post('/sessions', json=request).status_code == 404
    current['label'] = 'master'
    scenario_payload['questionIds'] = list(reversed(selected))
    assert client.put(f"/api/master/scenarios/{scenario['id']}", json=scenario_payload).status_code == 200
    topic_payload['questions'] = [{'id': q['id'], 'text': q['text'] + ' editada'} for q in topic['questions']]
    assert client.put(f"/api/master/topics/{topic['id']}", json=topic_payload).status_code == 200
    assert client.patch(f"/api/master/topics/{topic['id']}/status", json={'status': 'archived'}).status_code == 200
    current['label'] = 'speaker'
    assert scenario['id'] not in [s['id'] for s in client.get('/scenarios').json()['items']]
    assert client.post('/sessions', json=request).status_code == 404
    assert client.get(f"/sessions/{session['sessionId']}").json()['questions'] == setup['questions']
    current['label'] = 'master'
    assert client.patch(f"/api/master/topics/{topic['id']}/status", json={'status': 'active'}).status_code == 200
    current['label'] = 'speaker'
    second = client.post('/sessions', json=request).json()
    assert second['sessionId'] != session['sessionId']
    assert [q['id'] for q in client.get(f"/sessions/{second['sessionId']}").json()['questions']] == list(reversed(selected))
