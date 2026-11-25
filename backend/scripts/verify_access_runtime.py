"""Preflight Docker de solo lectura. Nunca migra, crea perfiles ni consume enlaces."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyodbc
from entra_access import Policy, enabled


class VerificationError(Exception):
    pass


def verify_configuration(discovery):
    if os.getenv('DEV_AUTH', 'false').lower() != 'false':
        raise VerificationError('Docker de accesos requiere DEV_AUTH=false y Microsoft Entra.')
    if not all(enabled(key) for key in ('VOXREADY_ENTRA_IDENTITY_ENABLED', 'VOXREADY_PENDING_ACCESS_ENABLED')):
        raise VerificationError('Debes habilitar identidad Entra e invitaciones para este arranque.')
    policy = Policy.configured()
    if discovery.get('issuer') != policy.issuer or discovery.get('jwks_uri') != policy.jwks_url:
        raise VerificationError('El emisor o las claves no coinciden con el descubrimiento oficial de Entra.')


def verify_schema(cursor):
    row = cursor.execute("""SELECT CONVERT(nvarchar(128),DATABASEPROPERTYEX(DB_NAME(),'Status')),
        CONVERT(nvarchar(128),DATABASEPROPERTYEX(DB_NAME(),'Collation')),COL_LENGTH('dbo.app_user','email')""").fetchone()
    if not row or tuple(row) != ('ONLINE', 'SQL_Latin1_General_CP1_CI_AS', 510):
        raise VerificationError('Estado, colacion o longitud de correo distintos del esquema revisado.')
    required_columns = {
        'pending_access': {'id', 'client_id', 'role', 'display_name', 'expected_email', 'created_by',
                           'created_at', 'updated_at', 'token_hash', 'expires_at', 'generation',
                           'used_at', 'completed_user_id', 'account_choice'},
        'entra_identity': {'tenant_id', 'object_id', 'user_id', 'issuer', 'created_at'},
        'legacy_access_profile': {'user_id', 'recorded_at'},
    }
    for table, required in required_columns.items():
        rows = cursor.execute("""SELECT c.name FROM sys.columns c
            WHERE c.object_id=OBJECT_ID(?)""", 'dbo.' + table).fetchall()
        if not required.issubset({row[0] for row in rows}):
            raise VerificationError('Falta esquema de accesos: dbo.' + table + '. No se ejecuto ninguna migracion.')
    indexes = {
        'app_user': {'UQ_app_user_id_client': True},
        'pending_access': {'PK_pending_access': True, 'UQ_pending_access_token': True,
                           'UQ_pending_access_email': True, 'IX_pending_access_client': False},
        'entra_identity': {'PK_entra_identity': True, 'UQ_entra_identity_user': True},
        'legacy_access_profile': {'PK_legacy_access_profile': True},
    }
    for table, required in indexes.items():
        rows = cursor.execute("""SELECT name,is_unique FROM sys.indexes
            WHERE object_id=OBJECT_ID(?) AND is_disabled=0 AND is_hypothetical=0""", 'dbo.' + table).fetchall()
        observed = {row[0]: bool(row[1]) for row in rows}
        if any(observed.get(name) != unique for name, unique in required.items()):
            raise VerificationError('Faltan indices activos de dbo.' + table + '.')
    required_constraints = {
        'FK_pending_access_client', 'FK_pending_access_creator', 'FK_pending_access_completed',
        'FK_entra_identity_user', 'FK_legacy_access_profile_user',
        'CK_pending_access_role_email', 'CK_pending_access_completion', 'CK_pending_access_token',
    }
    rows = cursor.execute("""SELECT name FROM sys.foreign_keys
        WHERE parent_object_id IN (OBJECT_ID('dbo.pending_access'),OBJECT_ID('dbo.entra_identity'),
            OBJECT_ID('dbo.legacy_access_profile')) AND is_disabled=0 AND is_not_trusted=0
        UNION ALL SELECT name FROM sys.check_constraints
        WHERE parent_object_id=OBJECT_ID('dbo.pending_access') AND is_disabled=0 AND is_not_trusted=0""").fetchall()
    if not required_constraints.issubset({row[0] for row in rows}):
        raise VerificationError('Faltan restricciones activas y verificadas del esquema de accesos.')


def main():
    connection = None
    stage = 'oidc'
    try:
        authority = os.environ.get('ENTRA_AUTHORITY', '').rstrip('/')
        parsed = urlparse(authority)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment:
            raise VerificationError('Falta ENTRA_AUTHORITY HTTPS para comprobar la configuracion.')
        with urlopen(authority + '/v2.0/.well-known/openid-configuration', timeout=12) as response:
            discovery = json.load(response)
        stage = 'configuration'
        verify_configuration(discovery)
        stage = 'sql_connection'
        conn_str = os.environ.get('SQL_CONNECTION_STRING', '')
        if not conn_str:
            raise VerificationError('Falta la conexion SQL de la API.')
        if 'DRIVER=' not in conn_str.upper():
            conn_str = 'DRIVER={ODBC Driver 18 for SQL Server};' + conn_str
        connection = pyodbc.connect(conn_str, timeout=15, autocommit=False)
        connection.timeout = 15
        stage = 'sql_metadata'
        verify_schema(connection.cursor())
        print(json.dumps({'configurationReady': True, 'oidcDiscoveryMatches': True,
                          'accessSchemaReady': True, 'readOnlyVerification': True}))
        return 0
    except VerificationError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
    except Exception as error:
        print('ERROR: no se pudo verificar Entra o SQL. No se modificaron datos; revisa conectividad y configuracion sin compartir secretos.', file=sys.stderr)
        detail = {'stage': stage, 'errorType': type(error).__name__}
        if isinstance(error, pyodbc.Error) and error.args and len(str(error.args[0])) == 5:
            detail['sqlState'] = str(error.args[0])
        print(json.dumps(detail), file=sys.stderr)
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()
    return 1


if __name__ == '__main__':
    sys.exit(main())
