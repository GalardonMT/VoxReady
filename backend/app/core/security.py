"""JWT validation (RS256 via JWKS, HS256 dev mode) and RBAC dependencies."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.utils import utcnow

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: PyJWKClient | None = None


@dataclass
class Principal:
    """Authenticated user resolved from JWT claims."""

    user_id: uuid.UUID
    role: str
    client_id: uuid.UUID | None
    preferred_language: str
    email: str | None = None
    display_name: str | None = None


def _get_jwks_client(settings: Settings) -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwks_url)
    return _jwks_client


def create_dev_token(user, settings: Settings) -> str:
    """Issue a local HS256 token for a seed user (dev mode only)."""
    now = utcnow()
    claims = {
        "sub": str(user.id),
        "role": user.role,
        "clientId": str(user.client_id) if user.client_id else None,
        "preferredLanguage": user.preferred_language,
        "email": user.email,
        "name": user.display_name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.dev_token_ttl_hours)).timestamp()),
    }
    return jwt.encode(claims, settings.dev_auth_secret, algorithm="HS256")


def _decode_token(token: str, settings: Settings) -> dict | None:
    if settings.dev_auth:
        try:
            return jwt.decode(
                token, settings.dev_auth_secret, algorithms=["HS256"]
            )
        except jwt.PyJWTError:
            pass
    if settings.jwks_url:
        try:
            signing_key = _get_jwks_client(settings).get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options={
                    "verify_aud": bool(settings.jwt_audience),
                    "verify_iss": bool(settings.jwt_issuer),
                },
            )
        except jwt.PyJWTError:
            return None
    return None


def _claims_to_principal(claims: dict) -> Principal:
    role = claims.get("role") or claims.get("extension_role")
    client_id = claims.get("clientId") or claims.get("client_id")
    return Principal(
        user_id=uuid.UUID(str(claims["sub"])),
        role=str(role),
        client_id=uuid.UUID(str(client_id)) if client_id else None,
        preferred_language=claims.get("preferredLanguage")
        or claims.get("preferred_language")
        or "es",
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("displayName"),
    )


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """Resolve the authenticated principal or raise 401 unauthorized."""
    settings = get_settings()
    if credentials is None:
        raise AppError(401, "unauthorized", "Token ausente, inválido o expirado.")
    claims = _decode_token(credentials.credentials, settings)
    if claims is None:
        raise AppError(401, "unauthorized", "Token ausente, inválido o expirado.")
    try:
        return _claims_to_principal(claims)
    except (KeyError, ValueError, AttributeError):
        raise AppError(401, "unauthorized", "Token ausente, inválido o expirado.")


def require_roles(*roles: str):
    """Dependency factory enforcing role-based access (403 forbidden)."""

    async def dependency(
        principal: Principal = Depends(get_principal),
    ) -> Principal:
        if principal.role not in roles:
            raise AppError(
                403,
                "forbidden",
                "El rol o scope del token no autoriza esta operación.",
            )
        return principal

    return dependency
