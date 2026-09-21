"""Topic management endpoints (client admin)."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, pagination_params, to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.content import Scenario, Topic, TopicKeyMessage, TopicRedLine
from app.models.sessions import PracticeSession
from app.schemas.topics import TopicIn
from app.services.helpers import get_current_policy
from app.utils import iso

router = APIRouter(tags=["topics"])


async def _serialize_topic(db: AsyncSession, topic: Topic) -> dict:
    messages = (
        await db.scalars(
            select(TopicKeyMessage)
            .where(TopicKeyMessage.topic_id == topic.id)
            .order_by(TopicKeyMessage.sort_order)
        )
    ).all()
    red_lines = (
        await db.scalars(
            select(TopicRedLine)
            .where(TopicRedLine.topic_id == topic.id)
            .order_by(TopicRedLine.sort_order)
        )
    ).all()
    policy = await get_current_policy(db, topic.client_id)
    retention_days = (
        policy.term_days if policy is not None and policy.keep == "full_recording" else None
    )
    return {
        "id": str(topic.id),
        "name": topic.name,
        "context": topic.context,
        "optics": topic.optics,
        "audience": topic.audience,
        "languages": topic.languages or [],
        "keyMessages": [m.text for m in messages],
        "redLines": [r.text for r in red_lines],
        "retentionDays": retention_days,
        "status": topic.status,
    }


async def _get_own_topic(
    db: AsyncSession, principal: Principal, topic_id: str
) -> Topic:
    tid = to_uuid(topic_id, "topic_not_found")
    topic = await db.get(Topic, tid)
    if (
        topic is None
        or topic.is_deleted
        or topic.client_id != principal.client_id
    ):
        raise AppError(404, "topic_not_found", "El tema no existe para este cliente.")
    return topic


def _apply_body(topic: Topic, body: TopicIn) -> None:
    topic.name = body.name
    topic.context = body.context
    topic.optics = body.optics
    topic.audience = body.audience
    topic.languages = list(body.languages)


async def _replace_children(db: AsyncSession, topic: Topic, body: TopicIn) -> None:
    await db.execute(
        delete(TopicKeyMessage).where(TopicKeyMessage.topic_id == topic.id)
    )
    await db.execute(delete(TopicRedLine).where(TopicRedLine.topic_id == topic.id))
    for index, text in enumerate(body.keyMessages, start=1):
        db.add(TopicKeyMessage(topic_id=topic.id, text=text, sort_order=index))
    for index, text in enumerate(body.redLines, start=1):
        db.add(TopicRedLine(topic_id=topic.id, text=text, sort_order=index))


@router.get("/topics")
async def list_topics(
    page: int = Query(1),
    pageSize: int = Query(20),
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    pagination: Pagination = pagination_params(page, pageSize)
    base = select(Topic).where(
        Topic.client_id == principal.client_id, Topic.is_deleted.is_(False)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    topics = (
        await db.scalars(
            base.order_by(Topic.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()
    return {
        "items": [await _serialize_topic(db, t) for t in topics],
        "page": pagination.page,
        "pageSize": pagination.page_size,
        "total": total,
    }


@router.post("/topics", status_code=201)
async def create_topic(
    body: TopicIn,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    topic = Topic(client_id=principal.client_id, status="active")
    _apply_body(topic, body)
    db.add(topic)
    await db.flush()
    await _replace_children(db, topic, body)
    await db.commit()
    return {"id": str(topic.id), "name": topic.name, "createdAt": iso(topic.created_at)}


@router.put("/topics/{topic_id}")
async def update_topic(
    topic_id: str,
    body: TopicIn,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    topic = await _get_own_topic(db, principal, topic_id)
    _apply_body(topic, body)
    await _replace_children(db, topic, body)
    await db.commit()
    return {"id": str(topic.id), "updatedAt": iso(topic.updated_at)}


@router.delete("/topics/{topic_id}", status_code=204)
async def delete_topic(
    topic_id: str,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    topic = await _get_own_topic(db, principal, topic_id)
    session_count = await db.scalar(
        select(func.count(PracticeSession.id))
        .join(Scenario, PracticeSession.scenario_id == Scenario.id)
        .where(Scenario.topic_id == topic.id)
    )
    if session_count:
        # Topics with associated sessions are archived, not deleted.
        topic.status = "archived"
    else:
        topic.is_deleted = True
        from app.utils import utcnow

        topic.deleted_at = utcnow()
    await db.commit()
    return Response(status_code=204)
