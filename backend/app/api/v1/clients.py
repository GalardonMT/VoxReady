"""Client admin endpoints: usage dashboard and retention policy."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.analysis import Report
from app.models.content import Topic
from app.models.identity import AppUser, Client
from app.models.privacy import RetentionPolicy
from app.models.sessions import PracticeSession
from app.schemas.clients import RetentionPolicyIn
from app.services.helpers import audit, get_current_policy
from app.utils import iso, utcnow

router = APIRouter(tags=["clients"])

_PERIOD_DAYS = {"month": 30, "quarter": 90, "year": 365}


async def _checked_client(
    db: AsyncSession, principal: Principal, client_id: str
) -> Client:
    cid = to_uuid(client_id, "client_not_found")
    client = await db.get(Client, cid)
    if client is None or client.is_deleted:
        raise AppError(404, "client_not_found", "El cliente no existe.")
    if principal.client_id != client.id:
        raise AppError(
            403, "forbidden", "El rol o scope del token no autoriza esta operación."
        )
    return client


@router.get("/clients/{client_id}/dashboard")
async def client_dashboard(
    client_id: str,
    period: str = Query("month"),
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    client = await _checked_client(db, principal, client_id)
    if period not in _PERIOD_DAYS:
        raise AppError(
            400, "invalid_query", "Parámetros de filtro o paginación inválidos."
        )
    since = utcnow() - timedelta(days=_PERIOD_DAYS[period])

    active_topics = await db.scalar(
        select(func.count(Topic.id)).where(
            Topic.client_id == client.id,
            Topic.status == "active",
            Topic.is_deleted.is_(False),
        )
    )
    spokespeople = await db.scalar(
        select(func.count(AppUser.id)).where(
            AppUser.client_id == client.id,
            AppUser.role == "spokesperson",
            AppUser.status == "active",
            AppUser.is_deleted.is_(False),
        )
    )
    sessions = await db.scalar(
        select(func.count(PracticeSession.id)).where(
            PracticeSession.client_id == client.id,
            PracticeSession.created_at >= since,
            PracticeSession.is_deleted.is_(False),
        )
    )
    average = await db.scalar(
        select(func.avg(Report.overall_score))
        .join(PracticeSession, Report.session_id == PracticeSession.id)
        .where(
            PracticeSession.client_id == client.id,
            PracticeSession.created_at >= since,
            Report.is_current.is_(True),
        )
    )
    return {
        "activeTopics": active_topics or 0,
        "spokespeople": spokespeople or 0,
        "sessions": sessions or 0,
        "averageOverall": int(round(average)) if average is not None else None,
    }


@router.get("/clients/{client_id}/retention-policy")
async def get_retention_policy(
    client_id: str,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    client = await _checked_client(db, principal, client_id)
    policy = await get_current_policy(db, client.id)
    if policy is None:
        # Lazily create the default policy for legacy clients.
        policy = RetentionPolicy(
            client_id=client.id,
            keep="full_recording",
            term_days=90,
            version_label="ret-default",
            is_current=True,
            effective_from=utcnow(),
            created_by=principal.user_id,
        )
        db.add(policy)
        await db.commit()
    return {
        "keep": policy.keep,
        "termDays": policy.term_days,
        "version": policy.version_label,
        "updatedAt": iso(policy.updated_at),
    }


@router.put("/clients/{client_id}/retention-policy")
async def put_retention_policy(
    client_id: str,
    body: RetentionPolicyIn,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    client = await _checked_client(db, principal, client_id)
    if body.keep == "full_recording" and (
        body.termDays is None or body.termDays < 1
    ):
        raise AppError(
            400,
            "invalid_policy",
            "termDays es obligatorio cuando keep=full_recording y debe ser positivo.",
        )
    term_days = body.termDays if body.keep == "full_recording" else None

    previous = await get_current_policy(db, client.id)
    if previous is not None:
        previous.is_current = False
    version_count = await db.scalar(
        select(func.count(RetentionPolicy.id)).where(
            RetentionPolicy.client_id == client.id
        )
    ) or 0
    policy = RetentionPolicy(
        client_id=client.id,
        keep=body.keep,
        term_days=term_days,
        version_label=f"ret-{version_count + 1:04d}",
        is_current=True,
        effective_from=utcnow(),
        created_by=principal.user_id,
    )
    db.add(policy)
    audit(
        db,
        "retention_updated",
        actor_user_id=principal.user_id,
        client_id=client.id,
        entity_type="retention_policy",
        entity_id=policy.id,
        detail={"keep": body.keep, "termDays": term_days},
    )
    await db.commit()
    return {
        "keep": policy.keep,
        "termDays": policy.term_days,
        "version": policy.version_label,
    }
