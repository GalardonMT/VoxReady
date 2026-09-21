"""Dev-only token issuer (disabled when DEV_AUTH=false)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError
from app.core.security import create_dev_token
from app.db import get_db
from app.models.identity import AppUser
from app.schemas.dev_auth import DevTokenIn

router = APIRouter(tags=["dev"])


@router.post("/dev/token")
async def issue_dev_token(
    body: DevTokenIn, db: AsyncSession = Depends(get_db)
) -> dict:
    settings = get_settings()
    if not settings.dev_auth:
        raise AppError(404, "not_found", "Recurso no disponible.")
    user = await db.scalar(
        select(AppUser).where(
            AppUser.email == body.email, AppUser.is_deleted.is_(False)
        )
    )
    if user is None:
        raise AppError(404, "user_not_found", "Usuario semilla no encontrado.")
    token = create_dev_token(user, settings)
    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "expiresIn": settings.dev_token_ttl_hours * 3600,
        "userId": str(user.id),
        "role": user.role,
    }
