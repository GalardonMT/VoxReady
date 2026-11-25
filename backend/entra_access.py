"""Validación estricta para identidades nuevas; nunca acepta pruebas del navegador."""
from dataclasses import dataclass
from functools import lru_cache
import os
import uuid
from urllib.parse import urlparse

import jwt
import pyodbc
from fastapi import Header, HTTPException


def enabled(name):
    return os.getenv(name, 'false').lower() == 'true'


@dataclass(frozen=True)
class Policy:
    issuer: str
    audience: str
    jwks_url: str
    tenant_id: str
    client_id: str

    @classmethod
    def configured(cls):
        try:
            result = cls(os.getenv('ENTRA_ISSUER') or os.environ['JWT_ISSUER'],
                         os.getenv('ENTRA_API_AUDIENCE') or os.environ['JWT_AUDIENCE'],
                         os.environ['JWKS_URL'], str(uuid.UUID(os.environ['ENTRA_TENANT_ID'])),
                         str(uuid.UUID(os.environ['ENTRA_SPA_CLIENT_ID'])))
            if not result.audience or any(urlparse(u).scheme != 'https' or not urlparse(u).hostname
                                          for u in (result.issuer, result.jwks_url)):
                raise ValueError()
            return result
        except (KeyError, ValueError):
            raise HTTPException(503, 'Falta confirmar la configuración de identidad Entra de la API.') from None


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    object_id: str
    issuer: str
    claims: dict


class BoundClaims(dict):
    """Contexto creado por servidor; ningún claim JSON puede construir esta clase."""
    def __init__(self, identity, profile_id):
        super().__init__(identity.claims)
        self.profile_id = str(profile_id)


@lru_cache(maxsize=4)
def key_client(url):
    return jwt.PyJWKClient(url, cache_keys=True, timeout=10)


def verify(authorization, *, policy=None):
    if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Se necesita iniciar sesión mediante Microsoft Entra.')
    token = authorization.removeprefix('Bearer ')
    policy = policy or Policy.configured()
    try:
        key = key_client(policy.jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['RS256'], audience=policy.audience,
                            issuer=policy.issuer, options={'require': [
                                'exp', 'iat', 'nbf', 'iss', 'aud', 'tid', 'oid', 'sub', 'scp', 'ver']})
        tenant_id, object_id = str(uuid.UUID(claims['tid'])), str(uuid.UUID(claims['oid']))
        version = claims['ver']
        actor = claims.get('azp') if version == '2.0' else claims.get('appid') if version == '1.0' else None
        if (tenant_id != policy.tenant_id or str(uuid.UUID(actor)) != policy.client_id
                or not isinstance(claims['scp'], str) or 'access_as_user' not in claims['scp'].split()
                or claims.get('idtyp') == 'app' or not isinstance(claims['sub'], str) or not claims['sub']):
            raise ValueError()
        return Identity(tenant_id, object_id, policy.issuer, claims)
    except jwt.MissingRequiredClaimError as error:
        raise HTTPException(401, 'El token de API no aporta el claim requerido: ' + error.claim + '.') from None
    except jwt.InvalidIssuerError:
        raise HTTPException(401, 'El emisor del token no coincide con el configurado para la API.') from None
    except jwt.InvalidAudienceError:
        raise HTTPException(401, 'El token no está dirigido a la API de VoxReady.') from None
    except Exception:
        # Nunca registrar JWT, claims, datos personales ni mensajes de bibliotecas.
        raise HTTPException(401, 'El token no corresponde a la identidad, aplicación o permiso autorizado.') from None


def require_identity(authorization: str = Header(None)):
    return verify(authorization)


def activation_ready():
    try:
        Policy.configured()
    except HTTPException:
        return False
    return all(enabled(name) for name in (
        'VOXREADY_ENTRA_IDENTITY_ENABLED', 'VOXREADY_ENTRA_EMAIL_PROOF_CONFIRMED',
        'VOXREADY_LEGACY_IDENTITY_REVIEW_CONFIRMED'))


def client_admin_activation_ready():
    """El enlace autoriza un perfil NUEVO; el correo no selecciona un perfil.

    El maestro permite expresamente al portador elegir su identidad. Se exige
    token API verificado y vínculo (tid,oid); email es contacto, no prueba del
    buzón. No requiere Graph ni inventa una verificación de correo inexistente.
    """
    try:
        Policy.configured()
    except HTTPException:
        return False
    return enabled('VOXREADY_ENTRA_IDENTITY_ENABLED')


def activation_ready_for_role(role, account_choice=True):
    if role == 'client_admin' or (role == 'spokesperson' and account_choice):
        return client_admin_activation_ready()
    return role == 'spokesperson' and activation_ready()


def account_email(identity):
    """Contacto reportado por Entra. Esta función NO acredita control del buzón."""
    email = identity.claims.get('email')
    if not isinstance(email, str):
        raise HTTPException(403, 'Entra no incluyó un correo de contacto compatible en el token de API.')
    from pending_access import PendingAccessRequest
    from pydantic import ValidationError
    try:
        return PendingAccessRequest(role='spokesperson', displayName='Identidad', email=email).email
    except ValidationError:
        raise HTTPException(403, 'El correo informado por Entra no es compatible con VoxReady.') from None


def activation_email(identity, access):
    if access['role'] == 'client_admin' or (access['role'] == 'spokesperson' and access.get('account_choice')):
        if not client_admin_activation_ready():
            raise HTTPException(503, 'La vinculación estable con Entra no está habilitada.')
        return account_email(identity)
    if access['role'] == 'spokesperson':
        return verified_email(identity)
    raise HTTPException(403, 'La invitación no autoriza este rol.')


def verified_email(identity):
    # Contrato conservador: debe observarse y acreditarse en ESTE tenant antes de
    # habilitarlo. No se supone que External ID emita email_verified por defecto.
    # No usar preferred_username/upn ni email_verified enviado como payload JSON.
    if not activation_ready():
        raise HTTPException(503, 'Falta verificar la evidencia del correo y la compatibilidad de cuentas existentes en Entra.')
    if identity.claims.get('email_verified') is not True or not isinstance(identity.claims.get('email'), str):
        raise HTTPException(403, 'Entra no aportó evidencia suficiente del correo. No se vinculó ni consumió el acceso.')
    from pending_access import PendingAccessRequest
    from pydantic import ValidationError
    try:
        return PendingAccessRequest(role='spokesperson', displayName='Identidad', email=identity.claims['email']).email
    except ValidationError:
        raise HTTPException(403, 'El correo acreditado no es compatible con VoxReady.') from None


def identity_status(identity):
    """Informe para el operador: sin valores de identidad, correo o token."""
    evidence = identity.claims.get('email_verified') is True and isinstance(identity.claims.get('email'), str)
    ready = activation_ready() and evidence
    if ready:
        try:
            verified_email(identity)
        except HTTPException:
            ready = False
    admin_ready = client_admin_activation_ready()
    if admin_ready:
        try:
            account_email(identity)
        except HTTPException:
            admin_ready = False
    return {'tokenValidated': True, 'stableIdentifierPresent': True,
            'scopeValidated': True, 'emailClaimPresent': isinstance(identity.claims.get('email'), str),
            'emailVerifiedBooleanTrue': identity.claims.get('email_verified') is True,
            # Solo presencia, incluso si el valor es vacío o tiene otro formato.
            # No equivalen a email_verified ni habilitan la vinculación.
            'verifiedPrimaryEmailClaimPresent': 'verified_primary_email' in identity.claims,
            'verifiedSecondaryEmailClaimPresent': 'verified_secondary_email' in identity.claims,
            # Verificación del dominio; no prueba individual de control del buzón.
            'emailDomainOwnerVerifiedBooleanTrue': identity.claims.get('xms_edov') is True,
            'activationAvailable': admin_ready,
            'clientAdminActivationAvailable': admin_ready,
            'spokespersonActivationAvailable': admin_ready,
            'fixedEmailActivationAvailable': ready,
            'emailProofConfigurationConfirmed': enabled('VOXREADY_ENTRA_EMAIL_PROOF_CONFIRMED'),
            'legacyReviewConfirmed': enabled('VOXREADY_LEGACY_IDENTITY_REVIEW_CONFIRMED')}


def mapped_profile(cursor, identity):
    cursor.execute('SELECT user_id FROM dbo.entra_identity WHERE tenant_id=? AND object_id=?',
                   identity.tenant_id, identity.object_id)
    row = cursor.fetchone()
    return str(row[0]) if row else None


def legacy_filter():
    if not enabled('VOXREADY_ENTRA_IDENTITY_ENABLED'):
        return ''
    # Solo perfiles presentes antes de la migración y aún sin vínculo estable.
    # Nunca ampliar esta lista desde un endpoint de registro o un login.
    return ''' AND EXISTS (SELECT 1 FROM dbo.legacy_access_profile l WHERE l.user_id=app_user.id)
        AND NOT EXISTS (SELECT 1 FROM dbo.entra_identity e WHERE e.user_id=app_user.id)'''


def bind_profile(cursor, access, identity, email):
    """Identity verificada; elección libre usa contacto, modalidad antigua exige prueba.

    El rol y la empresa proceden exclusivamente del acceso bloqueado en SQL.
    Un correo ocupado causa rechazo: nunca elige ni reasigna otro perfil.
    """
    # El llamante ya tiene reserva global y empresa/fila bloqueadas.
    cursor.execute("""SELECT CASE WHEN ?=expected_email THEN 1 ELSE 0 END
        FROM dbo.pending_access WHERE id=?""", email, str(access['id']))
    matches = cursor.fetchone()
    if access['role'] == 'spokesperson' and not access.get('account_choice') and (matches is None or not matches[0]):
        raise HTTPException(403, 'La cuenta Entra no corresponde al correo del vocero. Cambia de cuenta.')
    profile_id = mapped_profile(cursor, identity)
    if profile_id:
        # El núcleo comprueba rol, empresa, eliminación y correo bajo bloqueo.
        return profile_id
    cursor.execute("""SELECT TOP 1 id FROM dbo.app_user WITH (UPDLOCK,HOLDLOCK)
        WHERE id=? OR LOWER(LTRIM(RTRIM(email)))=LOWER(?)""", identity.object_id, email)
    if cursor.fetchone():
        raise HTTPException(409, 'La identidad o el correo coincide con un perfil existente. Requiere revisión; no se reasignará.')
    cursor.execute("""SELECT TOP 1 id FROM dbo.pending_access
        WHERE expected_email=? AND account_choice=0 AND used_at IS NULL AND id<>?""", email, str(access['id']))
    if cursor.fetchone():
        raise HTTPException(409, 'El correo está reservado para otro acceso pendiente.')
    profile_id = str(uuid.uuid4())
    try:
        cursor.execute("""INSERT INTO dbo.app_user (id,client_id,email,display_name,role,preferred_language)
            VALUES(?,?,?,?,?,'es')""", profile_id, str(access['client_id']), email,
            access['display_name'], access['role'])
        cursor.execute("""INSERT INTO dbo.entra_identity (tenant_id,object_id,user_id,issuer)
            VALUES(?,?,?,?)""", identity.tenant_id, identity.object_id, profile_id, identity.issuer)
    except pyodbc.IntegrityError as error:
        if any(code in str(error) for code in ('(2601)', '(2627)')):
            raise HTTPException(409, 'El correo o la identidad acaba de ocuparse. No se completó ni consumió el acceso.') from None
        raise
    return profile_id
