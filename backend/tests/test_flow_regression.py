"""Contratos existentes: autenticación, SAS, evento del worker e informe coach."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


def test_dev_auth_contract(monkeypatch):
    monkeypatch.setattr(main, 'DEV_AUTH', True)
    assert main.verify_token('Bearer dev-token-voxready-dev')['role'] == 'spokesperson'
    assert main.verify_token(None)['email'] == 'dev@voxready.io'
    monkeypatch.setattr(main, 'DEV_AUTH', False)
    with pytest.raises(HTTPException) as error:
        main.verify_token(None)
    assert error.value.status_code == 401


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


def test_recording_sas_contract(monkeypatch):
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


def test_worker_event_and_report_contract(monkeypatch):
    service_bus = MagicMock()
    sender = service_bus.from_connection_string.return_value.__enter__.return_value.get_queue_sender.return_value.__enter__.return_value
    captured = []
    monkeypatch.setattr(main, 'SERVICE_BUS_CONN_STR', 'test-bus')
    monkeypatch.setattr(main, 'ServiceBusClient', service_bus)
    monkeypatch.setattr(main, 'ServiceBusMessage', lambda text, **_: captured.append(json.loads(text)) or text)
    session_id = 'session-00112233-4455-6677-8899-aabbccddeeff-1791380000'
    scenario_id = '00112233-4455-6677-8899-aabbccddeeff'
    payload = main.FinishSessionRequest(video_blob_name=f'recordings/{session_id}.webm', scenario_id=scenario_id)
    assert main.finish_session(session_id, payload, {'sub': 'test-user'})['status'] == 'queued'
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
