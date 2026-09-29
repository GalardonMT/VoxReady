"""GET /v1/me - authenticated user profile."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.db import get_db
from app.models.identity import Client

router = APIRouter(tags=["identity"])


@router.get("/me")
async def get_me(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    client = await db.get(Client, principal.client_id) if principal.client_id else None
    return {
        "userId": str(principal.user_id),
        "email": principal.email,
        "displayName": principal.display_name,
        "role": principal.role,
        "clientId": str(principal.client_id) if principal.client_id else None,
        "clientName": client.name if client else None,
        "preferredLanguage": principal.preferred_language,
    }
