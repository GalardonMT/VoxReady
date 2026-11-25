"""Diagnóstico de lectura de la identidad propia en Graph; nunca autoriza perfiles.

El token de API se valida por separado antes de invocar estas funciones. El token
Graph solo se entrega al host fijo de Microsoft; no se decodifica como prueba de
autorización para VoxReady ni se registra. No consulta ni modifica Azure SQL.
"""
import json
import re
import uuid

import httpx
from fastapi import HTTPException


def _graph_get(client, path):
    try:
        with client.stream('GET', 'https://graph.microsoft.com/v1.0/' + path) as response:
            if response.status_code in (401, 403):
                raise HTTPException(response.status_code,
                    'Microsoft Graph no permitió leer el perfil propio o su organización con User.Read.')
            if response.status_code != 200:
                raise HTTPException(502, 'Microsoft Graph no completó la comprobación de lectura.')
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 65536:
                    raise ValueError()
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError()
            return result
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        # Las excepciones de red/Graph pueden contener información sensible.
        raise HTTPException(502, 'No se pudo comprobar el directorio. No se activó ningún acceso.') from None


def directory_status(identity, graph_authorization):
    if (not isinstance(graph_authorization, str) or len(graph_authorization) > 32768
            or not re.fullmatch(r'Bearer [A-Za-z0-9._~+/=-]+', graph_authorization)):
        raise HTTPException(401, 'Se requiere un token separado de Microsoft Graph para lectura del perfil propio.')
    with httpx.Client(headers={'Authorization': graph_authorization, 'Accept': 'application/json'},
                      timeout=8.0, follow_redirects=False, trust_env=False) as client:
        profile = _graph_get(client, 'me?$select=id,identities,creationType,userType')
        organization = _graph_get(client, 'organization?$select=id,verifiedDomains')
    return directory_report(identity, profile, organization)


def directory_report(identity, profile, organization):
    """Solo booleanos; los datos provienen de Graph, nunca del payload del cliente."""
    try:
        object_matches = str(uuid.UUID(profile['id'])) == identity.object_id
        organizations = organization['value']
        tenant_matches = (isinstance(organizations, list) and len(organizations) == 1
                          and str(uuid.UUID(organizations[0]['id'])) == identity.tenant_id)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(502, 'Graph no devolvió identificadores comparables para esta comprobación.') from None
    if not object_matches or not tenant_matches:
        raise HTTPException(403, 'La cuenta o el tenant de Graph no coincide con la identidad del token de API.')

    domains = organizations[0].get('verifiedDomains')
    domains = domains if isinstance(domains, list) else []
    initial_domains = {d['name'].lower() for d in domains if isinstance(d, dict)
                       and d.get('isInitial') is True and isinstance(d.get('name'), str)}
    identities = profile.get('identities')
    identities = identities if isinstance(identities, list) else []
    local = [entry for entry in identities if isinstance(entry, dict)
             and entry.get('signInType') == 'emailAddress'
             and isinstance(entry.get('issuer'), str) and entry['issuer'].lower() in initial_domains
             and isinstance(entry.get('issuerAssignedId'), str) and entry['issuerAssignedId'].strip()]
    email = identity.claims.get('email')
    email_matches = (len(local) == 1 and isinstance(email, str) and bool(email.strip())
                     and email.strip().lower() == local[0]['issuerAssignedId'].strip().lower())
    return {
        'graphReadSucceeded': True,
        'directoryObjectMatchesToken': object_matches,
        'directoryTenantMatchesToken': tenant_matches,
        'initialTenantDomainPresent': bool(initial_domains),
        'signInIdentitiesPresent': bool(identities),
        'singleLocalEmailIdentity': len(local) == 1,
        'tokenEmailMatchesLocalSignIn': email_matches,
        'federatedIdentityPresent': any(isinstance(entry, dict) and entry.get('signInType') == 'federated'
                                        for entry in identities),
        'creationTypeLocalAccount': profile.get('creationType') == 'LocalAccount',
        'creationTypeEmailVerified': profile.get('creationType') == 'EmailVerified',
        'creationTypeSelfServiceSignUp': profile.get('creationType') == 'SelfServiceSignUp',
        'userTypeMember': profile.get('userType') == 'Member',
        'userTypeGuest': profile.get('userType') == 'Guest',
        # El diagnóstico no acredita por sí solo el contrato de verificación del correo.
        'activationAvailable': False,
    }
