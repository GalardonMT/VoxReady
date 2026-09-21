"""Spokesperson progress and recommendations endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.analysis import AreaScore, Report
from app.models.progress import Recommendation
from app.models.rubric import RubricArea
from app.models.sessions import PracticeSession
from app.services.helpers import get_current_rubric
from app.utils import AREA_COLORS, DEFAULT_AREA_COLOR

router = APIRouter(tags=["progress"])


@router.get("/me/progress")
async def my_progress(
    lastN: int = Query(5),
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    last_n = min(max(lastN, 1), 20)
    rubric = await get_current_rubric(db)
    if rubric is None:
        raise AppError(
            500, "internal_error", "No hay una versión de rúbrica vigente."
        )
    areas = list(
        (
            await db.scalars(
                select(RubricArea)
                .where(RubricArea.rubric_version_id == rubric.id)
                .order_by(RubricArea.sort_order)
            )
        ).all()
    )

    series = []
    for area in areas:
        rows = (
            await db.execute(
                select(AreaScore.value)
                .join(Report, AreaScore.report_id == Report.id)
                .join(PracticeSession, Report.session_id == PracticeSession.id)
                .join(
                    RubricArea, AreaScore.rubric_area_id == RubricArea.id
                )
                .where(
                    PracticeSession.user_id == principal.user_id,
                    Report.is_current.is_(True),
                    RubricArea.area_key == area.area_key,
                )
                .order_by(Report.generated_at.desc())
                .limit(last_n)
            )
        ).all()
        values = [v for (v,) in reversed(rows)]
        current = values[-1] if values else None
        delta = (values[-1] - values[0]) if len(values) >= 2 else (0 if values else None)
        series.append(
            {
                "area": area.area_key,
                "label": area.name,
                "color": AREA_COLORS.get(area.area_key, DEFAULT_AREA_COLOR),
                "values": values,
                "current": current,
                "delta": delta,
            }
        )

    sessions_completed = await db.scalar(
        select(func.count(PracticeSession.id)).where(
            PracticeSession.user_id == principal.user_id,
            PracticeSession.status == "completed",
            PracticeSession.is_deleted.is_(False),
        )
    )
    latest_overall = await db.scalar(
        select(Report.overall_score)
        .join(PracticeSession, Report.session_id == PracticeSession.id)
        .where(
            PracticeSession.user_id == principal.user_id,
            Report.is_current.is_(True),
        )
        .order_by(Report.generated_at.desc())
        .limit(1)
    )
    with_values = [s for s in series if s["current"] is not None]
    weakest = min(with_values, key=lambda s: s["current"])["area"] if with_values else None

    return {
        "series": series,
        "sessionsCompleted": sessions_completed or 0,
        "latestOverall": latest_overall,
        "weakestArea": weakest,
    }


@router.get("/me/recommendations")
async def my_recommendations(
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.scalars(
            select(Recommendation)
            .where(
                Recommendation.user_id == principal.user_id,
                Recommendation.status == "active",
            )
            .order_by(Recommendation.created_at.desc())
        )
    ).all()
    return {
        "items": [
            {
                "id": str(r.id),
                "title": r.title,
                "detail": r.detail,
                "microlessonId": str(r.microlesson_id) if r.microlesson_id else None,
            }
            for r in rows
        ]
    }
