"""Identity, expiry, tenant isolation and role authorization."""
from datetime import timedelta
from datetime import datetime, timezone
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.core import security
from app.models.identity import AppUser, Client
from app import db as db_module
from app.seed import ADMIN_ID, VOCERO_ID
from tests.conftest import ADMIN_EMAIL, MASTER_EMAIL, VOCERO_EMAIL, auth, token_for


async def test_all_three_roles_use_database_identity(client):
    for email, role in [(VOCERO_EMAIL, "spokesperson"), (ADMIN_EMAIL, "client_admin"), (MASTER_EMAIL, "master_config")]:
        token = await token_for(client, email)
        result = await client.get('/v1/me', headers=auth(token))
        assert result.status_code == 200, result.text
        assert result.json()['role'] == role
        assert bool(result.json()['clientId']) == (role != 'master_config')


async def test_expired_token_and_unauthenticated_are_401(client):
    assert (await client.get('/v1/me')).status_code == 401
    settings = get_settings()
    expired = jwt.encode({'sub': str(VOCERO_ID), 'exp': int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())}, settings.dev_auth_secret, algorithm='HS256')
    assert (await client.get('/v1/me', headers=auth(expired))).status_code == 401


async def test_claimed_role_and_client_cannot_override_database(client):
    settings = get_settings()
    forged = jwt.encode({
        'sub': str(VOCERO_ID), 'role': 'master_config', 'clientId': None,
        'exp': int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }, settings.dev_auth_secret, algorithm='HS256')
    me = await client.get('/v1/me', headers=auth(forged))
    assert me.status_code == 200 and me.json()['role'] == 'spokesperson'
    assert (await client.get('/v1/master/dashboard', headers=auth(forged))).status_code == 403


async def test_other_client_cannot_read_or_write_client_resources(client):
    other_id = uuid.uuid4()
    async with db_module.new_session() as db:
        db.add(Client(id=other_id, name='Otra empresa', status='active'))
        db.add(AppUser(id=uuid.uuid4(), b2c_object_id='other-admin', client_id=other_id,
                       email='admin@other.example', display_name='Otro Admin', role='client_admin',
                       preferred_language='es', status='active'))
        await db.commit()
    token = await token_for(client, 'admin@other.example')
    own_client = (await client.get('/v1/me', headers=auth(await token_for(client, ADMIN_EMAIL)))).json()['clientId']
    assert (await client.get(f'/v1/clients/{own_client}/dashboard', headers=auth(token))).status_code == 403
    assert (await client.put(f'/v1/clients/{own_client}/retention-policy', json={'keep': 'metrics_only'}, headers=auth(token))).status_code == 403
    assert (await client.get('/v1/topics', headers=auth(token))).json()['total'] == 0


async def test_direct_forbidden_api_routes(client):
    vocero = await token_for(client, VOCERO_EMAIL)
    admin = await token_for(client, ADMIN_EMAIL)
    master = await token_for(client, MASTER_EMAIL)
    assert (await client.get('/v1/master/dashboard', headers=auth(vocero))).status_code == 403
    assert (await client.get('/v1/master/dashboard', headers=auth(admin))).status_code == 403
    assert (await client.get('/v1/topics', headers=auth(master))).status_code == 403
    assert (await client.get('/v1/scenarios', headers=auth(admin))).status_code == 403


async def test_dev_issuer_disabled_in_production_even_if_flag_set(client):
    settings = get_settings()
    settings.environment = 'production'
    try:
        assert (await client.post('/v1/dev/token', json={'email': MASTER_EMAIL})).status_code == 404
        old_token = jwt.encode({'sub': str(ADMIN_ID), 'exp': int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}, settings.dev_auth_secret, algorithm='HS256')
        assert (await client.get('/v1/me', headers=auth(old_token))).status_code == 401
    finally:
        settings.environment = 'development'


async def test_external_rs256_uses_registered_subject_and_verified_audience(client, monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    monkeypatch.setattr(security, '_get_jwks_client', lambda settings: type('Jwks', (), {
        'get_signing_key_from_jwt': lambda self, token: type('Key', (), {'key': public_key})()
    })())
    settings = get_settings()
    before = (settings.environment, settings.jwks_url, settings.jwt_issuer, settings.jwt_audience, settings.azure_tenant_id)
    settings.environment = 'production'
    settings.jwks_url = 'https://identity.example/jwks'
    settings.jwt_issuer = 'https://identity.example/'
    settings.jwt_audience = 'voxready-api'
    settings.azure_tenant_id = 'test-tenant'
    try:
        claims = {
            'sub': 'pairwise-subject', 'oid': 'seed-vocero', 'role': 'master_config', 'clientId': None,
            'iss': settings.jwt_issuer, 'aud': settings.jwt_audience, 'tid': settings.azure_tenant_id,
            'exp': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        }
        token = jwt.encode(claims, private_key, algorithm='RS256', headers={'kid': 'test'})
        me = await client.get('/v1/me', headers=auth(token))
        assert me.status_code == 200, me.text
        assert me.json()['role'] == 'spokesperson'
        assert (await client.get('/v1/master/dashboard', headers=auth(token))).status_code == 403
        wrong_audience = jwt.encode({**claims, 'aud': 'other-api'}, private_key, algorithm='RS256', headers={'kid': 'test'})
        assert (await client.get('/v1/me', headers=auth(wrong_audience))).status_code == 401
        wrong_tenant = jwt.encode({**claims, 'tid': 'other-tenant'}, private_key, algorithm='RS256', headers={'kid': 'test'})
        assert (await client.get('/v1/me', headers=auth(wrong_tenant))).status_code == 401
        unknown = jwt.encode({**claims, 'oid': 'not-provisioned'}, private_key, algorithm='RS256', headers={'kid': 'test'})
        assert (await client.get('/v1/me', headers=auth(unknown))).status_code == 401
    finally:
        settings.environment, settings.jwks_url, settings.jwt_issuer, settings.jwt_audience, settings.azure_tenant_id = before


async def test_browser_preflight_for_authorization_header(client):
    response = await client.options('/v1/me', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
