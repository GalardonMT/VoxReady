"""Accesos pendientes: no crea usuarios Entra ni escribe contraseñas.

El esquema es un borrador separado y nunca se prepara al importar este módulo.
La activación exige el contrato Entra acreditado y falla cerrada si falta evidencia.
"""
import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

import client_store
import entra_access
import entra_directory
import master_topics as store


class PendingAccessRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['client_admin', 'spokesperson']
    displayName: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None

    @field_validator('displayName')
    @classmethod
    def valid_name(cls, value):
        # NVARCHAR limita unidades UTF-16, no puntos de código de Python.
        if len(value.encode('utf-16-le')) > 150 * 2:
            raise ValueError('El nombre supera el límite permitido.')
        return value

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if value is not None:
            value = value.lower()
            if len(value.encode('utf-16-le')) > 255 * 2:
                raise ValueError('El correo supera el límite permitido de 255 caracteres.')
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                raise ValueError('Ingresa un correo válido.')
        return value

    @model_validator(mode='after')
    def role_email(self):
        # Compatibilidad: una solicitud antigua con correo de vocero conserva la
        # modalidad fija. La interfaz nueva omite correo para ambos roles.
        if self.role == 'client_admin' and self.email is not None:
            raise ValueError('El administrador elegirá su correo al activar.')
        return self


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{43}$')]


class InvitationIssueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allowAccountChoice: bool = False


def require_enabled():
    if os.getenv('VOXREADY_PENDING_ACCESS_ENABLED', 'false').lower() != 'true':
        raise HTTPException(503, 'Los accesos pendientes aún no están habilitados.')


def token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def serialize(row):
    item = dict(row)
    for key in ('id', 'clientId'):
        item[key] = str(item[key])
    for key in ('createdAt', 'expiresAt', 'usedAt'):
        value = item.get(key)
        if isinstance(value, datetime):
            item[key] = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    now = datetime.now(timezone.utc)
    item['state'] = ('activated' if item.get('usedAt') else
                     'pending' if not item.get('expiresAt') else
                     'expired' if item['expiresAt'] <= now else 'invited')
    return item


SELECT_ACCESS = """SELECT id,client_id AS clientId,role,display_name AS displayName,
    expected_email AS email,created_at AS createdAt,expires_at AS expiresAt,used_at AS usedAt,
    account_choice AS accountChoice
    FROM dbo.pending_access"""


def list_accesses(cursor, client_id):
    client_store.require_client(cursor, client_id)
    cursor.execute(SELECT_ACCESS + ' WHERE client_id=? ORDER BY created_at,id', str(client_id))
    return [serialize(item) for item in store.rows(cursor)]


def reserve_account_email(cursor):
    # Una reserva global respeta las equivalencias de la colación SQL. Hashes de
    # cadenas Python distintas no serializan necesariamente correos iguales en SQL.
    # Obtenerla antes de bloquear empresas mantiene un orden común de bloqueos.
    cursor.execute("""DECLARE @result int;
        EXEC @result=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',
            @LockOwner='Transaction',@LockTimeout=10000;
        IF @result<0 THROW 51000,'No se pudo reservar el correo',1;""",
        'voxready-access-email-reservation-v1')


def create_access(cursor, client_id, payload, actor_id):
    if payload.email:
        reserve_account_email(cursor)
    # Serializa altas y reemplazos por empresa, incluidos correos pendientes.
    client_store.require_client(cursor, client_id, lock=True)
    if payload.email:
        # El índice único de app_user.email también reserva perfiles eliminados.
        cursor.execute("""SELECT TOP 1 id FROM dbo.app_user
            WHERE LOWER(LTRIM(RTRIM(email)))=LOWER(?)""", payload.email)
        if cursor.fetchone():
            raise HTTPException(409, 'El correo pertenece a un perfil activo o eliminado. Revisa el usuario existente; no se reasignará.')
        cursor.execute("""SELECT TOP 1 id FROM dbo.pending_access
            WHERE expected_email=? AND used_at IS NULL""", payload.email)
        if cursor.fetchone():
            raise HTTPException(409, 'Ya existe un acceso pendiente para ese correo.')
    access_id = str(uuid.uuid4())
    cursor.execute("""INSERT INTO dbo.pending_access
        (id,client_id,role,display_name,expected_email,created_by,account_choice)
        VALUES(?,?,?,?,?,?,?)""",
        access_id, str(client_id), payload.role, payload.displayName, payload.email, actor_id, payload.email is None)
    cursor.execute(SELECT_ACCESS + ' WHERE id=?', access_id)
    return serialize(store.rows(cursor)[0])


def complete_with_verified_profile(cursor, token, *, bind_verified_profile):
    """Núcleo transaccional; el endpoint exige identidad Entra verificada.

    El adaptador de identidad debe verificar Entra ANTES de llamar aquí.
    bind_verified_profile(cursor, access) solo puede proceder de código servidor:
    debe comprobar la identidad estable y la evidencia exigida según el rol, rechazar vinculaciones
    incompatibles y devolver el UUID del perfil creado/vinculado en ESTA transacción.
    Nunca aceptar este callback, el UUID ni una prueba de correo desde un formulario.
    El llamante usa store.database: cualquier error debe revertir también el perfil.
    """
    digest = token_digest(InvitationRequest(token=token).token)
    reserve_account_email(cursor)
    cursor.execute('SELECT client_id FROM dbo.pending_access WHERE token_hash=?', digest)
    located = cursor.fetchone()
    if located is None:
        raise HTTPException(404, 'El enlace no es válido o fue reemplazado.')
    client_id = str(located[0])
    client_store.require_client(cursor, client_id, lock=True)
    cursor.execute("""SELECT id,client_id,role,display_name,expected_email,used_at,
        CASE WHEN expires_at<=SYSUTCDATETIME() THEN 1 ELSE 0 END AS expired,account_choice
        FROM dbo.pending_access WITH (UPDLOCK,HOLDLOCK)
        WHERE token_hash=? AND client_id=?""", digest, client_id)
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, 'El enlace no es válido o fue reemplazado.')
    if row[5] is not None or row[6]:
        raise HTTPException(410, 'El enlace venció o ya fue utilizado.')
    access = dict(zip(('id', 'client_id', 'role', 'display_name', 'expected_email'), row[:5]))
    access['account_choice'] = bool(row[7])
    if access['role'] not in ('client_admin', 'spokesperson'):
        raise HTTPException(409, 'El acceso no tiene un rol compatible.')
    store.require_active_company(cursor, {'client_id': client_id, 'role': access['role']})
    profile_id = store.uid(bind_verified_profile(cursor, access))
    # Defensa adicional: rol/empresa/correo se comprueban en SQL con su colación.
    # El callback sigue siendo responsable de no apropiarse de un perfil existente.
    cursor.execute("""SELECT id FROM dbo.app_user WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND client_id=?
        AND role=? AND is_deleted=0
        AND (? IS NULL OR LOWER(LTRIM(RTRIM(email)))=LOWER(?))""",
        profile_id, client_id, access['role'],
        None if access['account_choice'] else access['expected_email'],
        None if access['account_choice'] else access['expected_email'])
    if cursor.fetchone() is None:
        raise HTTPException(409, 'El perfil no corresponde al acceso pendiente.')
    cursor.execute("""UPDATE dbo.pending_access SET used_at=SYSUTCDATETIME(),
        completed_user_id=?,updated_at=SYSUTCDATETIME()
        WHERE id=? AND client_id=? AND token_hash=? AND used_at IS NULL
        AND expires_at>SYSUTCDATETIME()""", profile_id, str(access['id']), client_id, digest)
    if cursor.rowcount != 1:
        raise HTTPException(410, 'El enlace venció o cambió durante la activación.')
    return {'userId': profile_id, 'clientId': client_id, 'role': access['role']}


def issue_invitation(cursor, client_id, access_id, *, allow_account_choice=False):
    # El bloqueo de la fila es común a la finalización de activación.
    client_store.require_client(cursor, client_id, lock=True)
    cursor.execute("""SELECT used_at,role,account_choice FROM dbo.pending_access WITH (UPDLOCK,HOLDLOCK)
        WHERE id=? AND client_id=?""", str(access_id), str(client_id))
    access = cursor.fetchone()
    if access is None:
        raise HTTPException(404, 'Acceso pendiente no encontrado.')
    if access[0] is not None:
        raise HTTPException(409, 'El acceso ya fue activado; no admite otro enlace.')
    token = secrets.token_urlsafe(32)
    cursor.execute("""UPDATE dbo.pending_access SET token_hash=?,
        account_choice=CASE WHEN ?=1 THEN 1 ELSE account_choice END,
        expires_at=DATEADD(hour,48,SYSUTCDATETIME()),generation=generation+1,
        updated_at=SYSUTCDATETIME() WHERE id=? AND client_id=? AND used_at IS NULL""",
        token_digest(token), allow_account_choice, str(access_id), str(client_id))
    if cursor.rowcount != 1:
        raise HTTPException(409, 'El estado del acceso cambió. Recarga la lista.')
    cursor.execute('SELECT expires_at FROM dbo.pending_access WHERE id=?', str(access_id))
    expires_at = cursor.fetchone()[0]
    return {'activationPath': '/activate/#' + token, 'expiresAt': expires_at.replace(tzinfo=timezone.utc),
            'accountChoice': bool(access[2]) or allow_account_choice}


def inspect_invitation(cursor, token):
    # Solo lectura. No devuelve nombre de empresa, correo ni otros datos personales.
    cursor.execute("""SELECT role,expires_at,used_at,
        CASE WHEN expires_at<=SYSUTCDATETIME() THEN 1 ELSE 0 END AS expired,account_choice
        FROM dbo.pending_access WHERE token_hash=?""", token_digest(token))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, 'El enlace no es válido o fue reemplazado.')
    if row[2] is not None or row[3]:
        raise HTTPException(410, 'El enlace venció o ya fue utilizado. Solicita otro al maestro.')
    return {'role': row[0], 'expiresAt': row[1].replace(tzinfo=timezone.utc),
            'accountChoice': row[0] == 'client_admin' or bool(row[4]),
            'activationAvailable': entra_access.activation_ready_for_role(row[0], bool(row[4])),
            'message': 'Enlace reconocido. La API verificará la identidad y el correo antes de completar el registro.'}


def create_router(*, verify_token_dependency, database_factory):
    router = APIRouter(tags=['pending-access'])

    def no_store(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'

    def require_master(claims=Depends(verify_token_dependency)):
        with database_factory() as cursor:
            return store.resolve_user(cursor, claims, master=True)

    master = APIRouter(dependencies=[Depends(require_enabled), Depends(no_store)])

    @master.get('/api/master/clients/{client_id}/pending-accesses')
    def list_pending(client_id: uuid.UUID, actor=Depends(require_master)):
        with database_factory() as cursor:
            items = list_accesses(cursor, client_id)
            by_role = {role: entra_access.activation_ready_for_role(role) for role in ('client_admin','spokesperson')}
            return {'items': items, 'activationAvailable': any(by_role.values()), 'activationByRole': by_role}

    @master.post('/api/master/clients/{client_id}/pending-accesses', status_code=201)
    def create_pending(client_id: uuid.UUID, payload: PendingAccessRequest, actor=Depends(require_master)):
        with database_factory() as cursor:
            return create_access(cursor, client_id, payload, actor['id'])

    @master.post('/api/master/clients/{client_id}/pending-accesses/{access_id}/invitation')
    def generate(client_id: uuid.UUID, access_id: uuid.UUID, payload: InvitationIssueRequest | None = None,
                 actor=Depends(require_master)):
        with database_factory() as cursor:
            return issue_invitation(cursor, client_id, access_id,
                                    allow_account_choice=bool(payload and payload.allowAccountChoice))

    router.include_router(master)

    @router.post('/api/access-invitations/inspect', dependencies=[Depends(require_enabled), Depends(no_store)])
    def inspect(payload: InvitationRequest):
        with database_factory() as cursor:
            return inspect_invitation(cursor, payload.token)

    @router.get('/api/access-invitations/identity-status', dependencies=[Depends(no_store)])
    def identity_status(identity=Depends(entra_access.require_identity)):
        return entra_access.identity_status(identity)

    @router.post('/api/access-invitations/directory-status', dependencies=[Depends(no_store)])
    def directory_status(identity=Depends(entra_access.require_identity),
                         graph_authorization: str | None = Header(None, alias='X-VoxReady-Graph-Authorization')):
        return entra_directory.directory_status(identity, graph_authorization)

    def require_activation():
        require_enabled()
        if not entra_access.client_admin_activation_ready() and not entra_access.activation_ready():
            raise HTTPException(503, 'Falta confirmar el contrato Entra y las cuentas existentes. La activación continúa bloqueada.')

    @router.post('/api/access-invitations/complete', dependencies=[Depends(require_activation), Depends(no_store)])
    def complete(payload: InvitationRequest, identity=Depends(entra_access.require_identity)):
        with database_factory() as cursor:
            return complete_with_verified_profile(cursor, payload.token,
                bind_verified_profile=lambda tx, access: entra_access.bind_profile(
                    tx, access, identity, entra_access.activation_email(identity, access)))

    return router
