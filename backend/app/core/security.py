"""JWT validation and database-backed role and tenant authorization."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.db import get_db
from app.models.identity import AppUser, Client

bearer_scheme = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None
_jwks_url: str | None = None


@dataclass
class Principal:
    user_id: uuid.UUID
    role: str
    client_id: uuid.UUID | None
    preferred_language: str
    email: str | None = None
    display_name: str | None = None


def _get_jwks_client(settings: Settings) -> PyJWKClient:
    global _jwks_client, _jwks_url
    if _jwks_client is None or _jwks_url != settings.jwks_url:
        _jwks_client = PyJWKClient(settings.jwks_url)
        _jwks_url = settings.jwks_url
    return _jwks_client


def create_dev_token(user: AppUser, settings: Settings) -> str:
    if settings.environment != "development" or not settings.dev_auth:
        raise RuntimeError("La autenticacion de desarrollo esta deshabilitada.")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "clientId": str(user.client_id) if user.client_id else None,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=settings.dev_token_ttl_hours)).timestamp()),
        },
        settings.dev_auth_secret,
        algorithm="HS256",
    )


def _decode_token(token: str, settings: Settings) -> tuple[dict, str] | None:
    if settings.environment == "development" and settings.dev_auth:
        try:
            return jwt.decode(token, settings.dev_auth_secret, algorithms=["HS256"]), "dev"
        except jwt.PyJWTError:
            pass
    if settings.jwks_url and settings.jwt_issuer and settings.jwt_audience:
        try:
            key = _get_jwks_client(settings).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, key.key, algorithms=["RS256"],
                audience=settings.jwt_audience, issuer=settings.jwt_issuer,
            )
            if settings.azure_tenant_id and claims.get("tid") != settings.azure_tenant_id:
                return None
            return claims, "external"
        except jwt.PyJWTError:
            pass
    return None


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise AppError(401, "unauthorized", "Token ausente, invalido o expirado.")
    decoded = _decode_token(credentials.credentials, get_settings())
    if decoded is None:
        raise AppError(401, "unauthorized", "Token ausente, invalido o expirado.")
    claims, token_source = decoded
    subject = claims.get("sub") if token_source == "dev" else claims.get("oid") or claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AppError(401, "unauthorized", "Token sin sujeto valido.")

    if token_source == "dev":
        try:
            user = await db.get(AppUser, uuid.UUID(subject))
        except ValueError:
            user = None
    else:
        user = await db.scalar(select(AppUser).where(AppUser.b2c_object_id == subject))
    if user is None or user.is_deleted or user.status != "active":
        raise AppError(401, "unauthorized", "Usuario inexistente o inactivo.")
    if user.role not in {"spokesperson", "client_admin", "master_config"}:
        raise AppError(403, "forbidden", "Rol no autorizado.")
    if user.role == "master_config":
        if user.client_id is not None:
            raise AppError(403, "forbidden", "Cuenta maestra mal configurada.")
    else:
        if user.client_id is None:
            raise AppError(403, "forbidden", "Usuario sin cliente asignado.")
        client = await db.get(Client, user.client_id)
        if client is None or client.is_deleted or client.status != "active":
            raise AppError(403, "forbidden", "Cliente no disponible.")
    return Principal(
        user_id=user.id, role=user.role, client_id=user.client_id,
        preferred_language=user.preferred_language,
        email=user.email, display_name=user.display_name,
    )


def require_roles(*roles: str):
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise AppError(403, "forbidden", "El rol no autoriza esta operacion.")
        return principal
    return dependency
