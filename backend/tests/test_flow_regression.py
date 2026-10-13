"""Contratos existentes: autenticación, SAS, evento del worker e informe coach."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from contextlib import contextmanager

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


@pytest.fixture
def authorized_session(monkeypatch):
    def allow(_connection_string, _claims, _session_id, *, read_only=False):
        return {
            'id': '00112233-4455-6677-8899-aabbccddeeff',
            'scenario_id': '00112233-4455-6677-8899-aabbccddeeff',
            'status': 'created',
            'external_session_id': _session_id,
            'profile': {'id': 'test-user', 'client_id': 'test-client', 'role': 'spokesperson'},
        }

    monkeypatch.setattr(main.spokesperson_store, 'require_session_access', allow)


def test_dev_auth_contract(monkeypatch):
    monkeypatch.setattr(main, 'DEV_AUTH', True)
    monkeypatch.setenv('DEV_AUTH_TEST_EMAIL', 'assigned@example.invalid')
    assert main.verify_token('Bearer dev-token-voxready-dev')['email'] == 'assigned@example.invalid'
    assert main.verify_token(None)['email'] == 'assigned@example.invalid'
    monkeypatch.setattr(main, 'DEV_AUTH', False)
    with pytest.raises(HTTPException) as error:
        main.verify_token(None)
    assert error.value.status_code == 401


def test_dev_auth_requires_preassigned_email(monkeypatch):
    monkeypatch.setattr(main, 'DEV_AUTH', True)
    monkeypatch.delenv('DEV_AUTH_TEST_EMAIL', raising=False)
    with pytest.raises(HTTPException) as error:
        main.verify_token(None)
    assert error.value.status_code == 503


def test_me_uses_only_preassigned_database_role_and_company(monkeypatch):
    cursor = MagicMock()
    cursor.description = [(column,) for column in ('id', 'client_id', 'email', 'display_name', 'role', 'preferred_language')]
    cursor.fetchall.return_value = [('db-user', 'db-client', 'assigned@example.invalid', 'Usuario', 'spokesperson', 'es')]
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value = cursor
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(main, 'SQL_CONN_STR', 'test-db')
    monkeypatch.setattr(main.pyodbc, 'connect', connect)
    profile = main.get_current_user_profile({
        'sub': 'external-subject', 'email': 'assigned@example.invalid',
        'role': 'master_config', 'clientId': 'other-client',
    })
    assert profile['userId'] == 'db-user'
    assert profile['role'] == 'spokesperson'
    assert profile['clientId'] == 'db-client'
    assert cursor.execute.call_count == 1
    assert 'SELECT TOP 2' in cursor.execute.call_args.args[0]


def test_me_rejects_unassigned_user_without_writing(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value = cursor
    monkeypatch.setattr(main, 'SQL_CONN_STR', 'test-db')
    monkeypatch.setattr(main.pyodbc, 'connect', MagicMock(return_value=connection))
    with pytest.raises(HTTPException) as error:
        main.get_current_user_profile({'sub': 'external-subject', 'email': 'unknown@example.invalid'})
    assert error.value.status_code == 403
    assert cursor.execute.call_count == 1
    assert 'SELECT TOP 2' in cursor.execute.call_args.args[0]


def test_me_rejects_duplicate_email(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [('first',), ('second',)]
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value = cursor
    monkeypatch.setattr(main, 'SQL_CONN_STR', 'test-db')
    monkeypatch.setattr(main.pyodbc, 'connect', MagicMock(return_value=connection))
    with pytest.raises(HTTPException) as error:
        main.get_current_user_profile({'email': 'duplicate@example.invalid'})
    assert error.value.status_code == 403


def test_me_fails_closed_when_database_unavailable(monkeypatch):
    monkeypatch.setattr(main, 'SQL_CONN_STR', 'test-db')
    monkeypatch.setattr(main.pyodbc, 'connect', MagicMock(side_effect=main.pyodbc.Error('unavailable')))
    with pytest.raises(HTTPException) as error:
        main.get_current_user_profile({'email': 'assigned@example.invalid'})
    assert error.value.status_code == 503


def test_entra_signed_token_and_invalid_signature(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    monkeypatch.setattr(main, '_get_jwks_client', lambda: client)
    monkeypatch.setattr(main, 'DEV_AUTH', False)
    monkeypatch.setattr(main, 'JWT_AUDIENCE', 'voxready-test-audience')
    claims = {'sub': 'entra-user', 'email': 'test@example.invalid', 'aud': 'voxready-test-audience'}
    token = jwt.encode(claims, private, algorithm='RS256')
    assert main.verify_token('Bearer ' + token)['sub'] == 'entra-user'
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong = jwt.encode(claims, other_private, algorithm='RS256')
    with pytest.raises(HTTPException) as error:
        main.verify_token('Bearer ' + wrong)
    assert error.value.status_code == 401


def test_dev_auth_does_not_accept_unsigned_jwt_fallback(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    monkeypatch.setattr(main, '_get_jwks_client', lambda: client)
    monkeypatch.setattr(main, 'DEV_AUTH', True)
    monkeypatch.setattr(main, 'JWT_AUDIENCE', 'voxready-test-audience')
    token = jwt.encode({'email': 'assigned@example.invalid', 'aud': 'voxready-test-audience'},
                       rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm='RS256')
    with pytest.raises(HTTPException) as error:
        main.verify_token('Bearer ' + token)
    assert error.value.status_code == 401


def test_recording_sas_contract(monkeypatch, authorized_session):
    sdk = MagicMock()
    sdk.from_connection_string.return_value.account_name = 'test-account'
    sdk.from_connection_string.return_value.credential.account_key = 'test-key'
    monkeypatch.setattr(main, 'STORAGE_CONN_STR', 'test-connection')
    monkeypatch.setattr(main, 'BlobServiceClient', sdk)
    monkeypatch.setattr(main, 'generate_blob_sas', lambda **_: 'test-sas')
    session_id = 'session-00112233-4455-6677-8899-aabbccddeeff-1791380000'
    result = main.get_upload_sas_url(session_id, {'sub': 'test-user'})
    assert result['blob_name'] == f'recordings/{session_id}.webm'
    assert result['uploadUrl'] == result['upload_url']
    assert result['upload_url'].endswith(f'/{session_id}.webm?test-sas')


@pytest.mark.asyncio
async def test_worker_event_and_report_contract(monkeypatch, authorized_session):
    service_bus = MagicMock()
    sender = service_bus.from_connection_string.return_value.__enter__.return_value.get_queue_sender.return_value.__enter__.return_value
    captured = []
    trigger_worker = AsyncMock(return_value=False)
    monkeypatch.setattr(main, 'SQL_CONN_STR', '')
    monkeypatch.setattr(main, 'trigger_worker_analysis', trigger_worker)
    monkeypatch.setattr(main, 'SERVICE_BUS_CONN_STR', 'test-bus')
    monkeypatch.setattr(main, 'ServiceBusClient', service_bus)
    monkeypatch.setattr(main, 'ServiceBusMessage', lambda text, **_: captured.append(json.loads(text)) or text)
    session_id = 'session-00112233-4455-6677-8899-aabbccddeeff-1791380000'
    scenario_id = '00112233-4455-6677-8899-aabbccddeeff'
    payload = main.FinishSessionRequest(video_blob_name=f'recordings/{session_id}.webm', scenario_id=scenario_id)
    assert (await main.finish_session(session_id, payload, {'sub': 'test-user'}))['status'] == 'analyzing'
    trigger_worker.assert_awaited_once()
    assert sender.send_messages.call_count == 1
    assert captured[0]['event_type'] == 'SESSION_RECORDING_COMPLETED'
    assert captured[0]['payload']['scenario_id'] == scenario_id
    assert captured[0]['payload']['session_id'] == session_id
    storage = MagicMock()
    blob = storage.from_connection_string.return_value.get_container_client.return_value.get_blob_client.return_value
    blob.exists.return_value = True
    blob.download_blob.return_value.readall.return_value = json.dumps({'session_id': session_id, 'puntuacion_global': {'score_general': 85}}).encode()
    monkeypatch.setattr(main, 'STORAGE_CONN_STR', 'test-storage')
    monkeypatch.setattr(main, 'BlobServiceClient', storage)
    report = main.get_session_report(session_id, {'sub': 'test-user'})
    assert report['status'] == 'completed' and report['puntuacion_global']['score_general'] == 85
    storage.from_connection_string.return_value.get_container_client.return_value.get_blob_client.assert_called_once_with(f'{session_id}_report.json')


@pytest.mark.parametrize('role,client_id,required_filter', [
    ('spokesperson', 'client-a', 'AND user_id=? AND client_id=?'),
    ('client_admin', 'client-a', 'AND client_id=?'),
    ('master_config', None, 'AND is_deleted=0'),
])
def test_session_read_access_uses_database_role_and_scope(monkeypatch, role, client_id, required_filter):
    cursor = MagicMock()
    cursor.fetchone.return_value = ('session-id', 'scenario-id', 'created', 'public-id')

    @contextmanager
    def database(_connection_string):
        yield cursor

    profile = {'id': 'actor-id', 'client_id': client_id, 'role': role}
    monkeypatch.setattr(main.spokesperson_store.store, 'database', database)
    monkeypatch.setattr(main.spokesperson_store.store, 'resolve_user', lambda *_args, **_kwargs: profile)
    result = main.spokesperson_store.require_session_access('test-db', {'sub': 'actor-id'}, 'public-id', read_only=True)
    sql, *params = cursor.execute.call_args.args
    assert required_filter in sql
    assert result['id'] == 'session-id'
    if role == 'spokesperson':
        assert params[-2:] == ['actor-id', 'client-a']
    elif role == 'client_admin':
        assert params[-1] == ('public-id', None, 'client-a')
    else:
        assert params[-1] == ('public-id', None)


def test_unknown_session_denies_access(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    @contextmanager
    def database(_connection_string):
        yield cursor

    monkeypatch.setattr(main.spokesperson_store.store, 'database', database)
    monkeypatch.setattr(main.spokesperson_store.store, 'resolve_user', lambda *_args, **_kwargs: {'id': 'admin', 'client_id': 'client-a', 'role': 'client_admin'})
    with pytest.raises(HTTPException) as error:
        main.spokesperson_store.require_session_access('test-db', {'sub': 'admin'}, 'other-session', read_only=True)
    assert error.value.status_code == 404


def test_admin_cannot_write_another_users_session(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    @contextmanager
    def database(_connection_string):
        yield cursor

    monkeypatch.setattr(main.spokesperson_store.store, 'database', database)
    monkeypatch.setattr(main.spokesperson_store.store, 'resolve_user', lambda *_args, **_kwargs: {'id': 'admin', 'client_id': 'client-a', 'role': 'client_admin'})
    with pytest.raises(HTTPException) as error:
        main.spokesperson_store.require_session_access('test-db', {'sub': 'admin'}, 'other-session')
    assert error.value.status_code == 404
    sql = cursor.execute.call_args.args[0]
    assert 'AND user_id=? AND client_id=?' in sql


def test_master_without_client_is_allowed_only_for_session_read():
    cursor = MagicMock()
    master_id = '00112233-4455-6677-8899-aabbccddeeff'
    cursor.fetchone.return_value = (master_id, None, 'master_config')
    profile = main.master_store.resolve_user(cursor, {'sub': master_id}, allow_unassigned_master=True)
    assert profile == {'id': master_id, 'client_id': None, 'role': 'master_config'}
    with pytest.raises(HTTPException) as error:
        main.master_store.resolve_user(cursor, {'sub': master_id})
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_unauthorized_session_never_reaches_blob_or_worker(monkeypatch):
    def deny(*_args, **_kwargs):
        raise HTTPException(404, 'Sesión no encontrada.')

    blob = MagicMock()
    worker = AsyncMock()
    monkeypatch.setattr(main.spokesperson_store, 'require_session_access', deny)
    monkeypatch.setattr(main, 'BlobServiceClient', blob)
    monkeypatch.setattr(main, 'trigger_worker_analysis', worker)
    monkeypatch.setattr(main, 'STORAGE_CONN_STR', 'test-storage')
    user = {'sub': 'other-user'}
    for call in (
        lambda: main.get_upload_sas_url('other-session', user),
        lambda: main.get_playback_sas_url('other-session', user),
        lambda: main.get_session_report('other-session', user),
        lambda: main.grant_consent('other-session', main.ConsentRequest(), user),
    ):
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await main.finish_session('other-session', main.FinishSessionRequest(), user)
    assert error.value.status_code == 404
    blob.from_connection_string.assert_not_called()
    worker.assert_not_awaited()


@pytest.mark.asyncio
async def test_finish_rejects_blob_from_another_session(monkeypatch, authorized_session):
    worker = AsyncMock()
    monkeypatch.setattr(main, 'trigger_worker_analysis', worker)
    with pytest.raises(HTTPException) as error:
        await main.finish_session('my-session', main.FinishSessionRequest(blobPath='recordings/other-session.webm'), {'sub': 'test-user'})
    assert error.value.status_code == 422
    worker.assert_not_awaited()
