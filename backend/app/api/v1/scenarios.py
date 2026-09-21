"""Scenario catalog endpoints (spokesperson)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, pagination_params, to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.content import Scenario, Topic

router = APIRouter(tags=["scenarios"])


def _serialize_scenario(scenario: Scenario, topic: Topic | None) -> dict:
    return {
        "id": str(scenario.id),
        "title": scenario.title,
        "context": topic.context if topic else "",
        "category": scenario.category,
        "audience": topic.audience if topic else "",
        "difficulty": scenario.difficulty,
        "estimatedMinutes": scenario.estimated_minutes,
        "questionCount": scenario.question_count,
        "languages": (topic.languages if topic else None) or [],
    }


def _base_query(principal: Principal):
    return (
        select(Scenario, Topic)
        .join(Topic, Scenario.topic_id == Topic.id)
        .where(
            Scenario.client_id == principal.client_id,
            Scenario.status == "active",
            Scenario.is_deleted.is_(False),
            Topic.is_deleted.is_(False),
        )
    )


@router.get("/scenarios")
async def list_scenarios(
    category: str | None = Query(None),
    audience: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1),
    pageSize: int = Query(20),
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    pagination: Pagination = pagination_params(page, pageSize)
    if category is not None and category not in ("health", "reputational", "operational"):
        raise AppError(
            400, "invalid_query", "Parámetros de filtro o paginación inválidos."
        )

    stmt = _base_query(principal)
    if category:
        stmt = stmt.where(Scenario.category == category)
    if audience:
        stmt = stmt.where(Topic.audience == audience)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Scenario.title.ilike(like), Topic.context.ilike(like)))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(
            stmt.order_by(Scenario.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()
    return {
        "items": [_serialize_scenario(s, t) for s, t in rows],
        "page": pagination.page,
        "pageSize": pagination.page_size,
        "total": total,
    }


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: str,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sid = to_uuid(scenario_id, "scenario_not_found")
    row = (
        await db.execute(_base_query(principal).where(Scenario.id == sid))
    ).first()
    if row is None:
        raise AppError(
            404,
            "scenario_not_found",
            "El escenario no existe o no está habilitado para el usuario.",
        )
    scenario, topic = row
    return _serialize_scenario(scenario, topic)
