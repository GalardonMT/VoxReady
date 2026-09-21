"""GET /v1/me - authenticated user profile."""
from fastapi import APIRouter, Depends

from app.core.security import Principal, get_principal

router = APIRouter(tags=["identity"])


@router.get("/me")
async def get_me(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "userId": str(principal.user_id),
        "email": principal.email,
        "displayName": principal.display_name,
        "role": principal.role,
        "clientId": str(principal.client_id) if principal.client_id else None,
        "preferredLanguage": principal.preferred_language,
    }
