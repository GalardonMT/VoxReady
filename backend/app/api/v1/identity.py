"""GET /v1/me - authenticated user profile.

When the JWT comes from Entra External ID (CIAM) the token may not contain
custom claims like `role` or `clientId`.  In that case we look up the user
in the `app_user` table by their Object ID (oid/sub) or email to resolve the
full profile.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import Principal, get_principal
from app.db import get_db
from app.models.identity import AppUser

router = APIRouter(tags=["identity"])


@router.get("/me")
async def get_me(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # If the token already carried role + clientId (e.g. dev HS256 tokens),
    # we can respond immediately without a DB query.
    if principal.role and principal.role not in ("", "None"):
        return {
            "userId": str(principal.user_id),
            "email": principal.email,
            "displayName": principal.display_name,
            "role": principal.role,
            "clientId": str(principal.client_id) if principal.client_id else None,
            "preferredLanguage": principal.preferred_language,
        }

    # Otherwise resolve from the database (Entra CIAM tokens).
    user = await db.scalar(
        select(AppUser).where(
            AppUser.b2c_object_id == str(principal.user_id),
            AppUser.is_deleted.is_(False),
        )
    )

    # Fallback: try matching by email
    if user is None and principal.email:
        user = await db.scalar(
            select(AppUser).where(
                AppUser.email == principal.email,
                AppUser.is_deleted.is_(False),
            )
        )

    if user is None:
        # Auto-provision verified Entra CIAM user into the active client
        from app.models.identity import Client
        client = await db.scalar(select(Client).where(Client.status == "active").limit(1))
        if client:
            user = AppUser(
                id=principal.user_id,
                b2c_object_id=str(principal.user_id),
                client_id=client.id,
                email=principal.email or f"{principal.user_id}@user.voxready.io",
                display_name=principal.display_name or "Vocero",
                role="spokesperson",
                preferred_language=principal.preferred_language or "es",
                status="active",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

    if user is None:
        raise AppError(
            403,
            "user_not_provisioned",
            "El usuario autenticado no tiene un perfil activo en VoxReady. "
            "Contacte al administrador de su organización.",
        )

    return {
        "userId": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role,
        "clientId": str(user.client_id) if user.client_id else None,
        "preferredLanguage": user.preferred_language,
    }
