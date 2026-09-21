"""Microlesson catalog endpoint (spokesperson)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.progress import Microlesson

router = APIRouter(tags=["microlessons"])


@router.get("/microlessons")
async def list_microlessons(
    topic: str | None = Query(None),
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Microlesson).where(
        Microlesson.client_id == principal.client_id,
        Microlesson.status == "active",
        Microlesson.is_deleted.is_(False),
    )
    if topic:
        stmt = stmt.where(Microlesson.topic_tag == topic)
    rows = (
        await db.scalars(stmt.order_by(Microlesson.created_at))
    ).all()
    return {
        "items": [
            {
                "id": str(m.id),
                "title": m.title,
                "durationMinutes": m.duration_minutes,
                "topic": m.topic_tag,
            }
            for m in rows
        ]
    }
