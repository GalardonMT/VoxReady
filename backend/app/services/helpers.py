"""Shared service helpers: current rubric/policy lookups and audit logging."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.privacy import AuditEvent, RetentionPolicy
from app.models.rubric import RubricVersion
from app.utils import utcnow


async def get_current_rubric(db: AsyncSession) -> RubricVersion | None:
    """Latest published rubric version (global, cross-tenant)."""
    return await db.scalar(
        select(RubricVersion)
        .where(RubricVersion.status == "published")
        .order_by(RubricVersion.published_at.desc())
        .limit(1)
    )


async def get_current_policy(
    db: AsyncSession, client_id: uuid.UUID
) -> RetentionPolicy | None:
    """Current retention policy for a client."""
    return await db.scalar(
        select(RetentionPolicy)
        .where(
            RetentionPolicy.client_id == client_id,
            RetentionPolicy.is_current.is_(True),
        )
        .order_by(RetentionPolicy.effective_from.desc())
        .limit(1)
    )


def audit(
    db: AsyncSession,
    event_type: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    """Append a compliance audit event (kept for the legal term)."""
    event = AuditEvent(
        event_type=event_type,
        actor_user_id=actor_user_id,
        client_id=client_id,
        entity_type=entity_type,
        entity_id=entity_id,
        detail_json=detail,
        occurred_at=utcnow(),
    )
    db.add(event)
    return event
