"""Spokesperson practice schedule endpoint."""
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import get_db
from app.models.content import Scenario
from app.models.progress import Schedule
from app.schemas.schedule import ScheduleIn
from app.utils import utcnow

router = APIRouter(tags=["schedule"])


@router.post("/me/schedule", status_code=201)
async def create_schedule(
    body: ScheduleIn,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        scheduled_date = datetime.strptime(body.date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise AppError(400, "invalid_date", "Fecha en el pasado o con formato inválido.")
    if scheduled_date < utcnow().date():
        raise AppError(400, "invalid_date", "Fecha en el pasado o con formato inválido.")

    scenario_id = None
    if body.scenarioId:
        scenario_id = to_uuid(body.scenarioId, "scenario_not_found")
        scenario = await db.get(Scenario, scenario_id)
        if (
            scenario is None
            or scenario.is_deleted
            or scenario.client_id != principal.client_id
            or scenario.status != "active"
        ):
            raise AppError(
                404,
                "scenario_not_found",
                "El escenario indicado no existe o no está disponible.",
            )

    entry = Schedule(
        client_id=principal.client_id,
        user_id=principal.user_id,
        scheduled_date=scheduled_date,
        scenario_id=scenario_id,
        status="scheduled",
    )
    db.add(entry)
    await db.commit()
    return {
        "scheduleId": str(entry.id),
        "date": scheduled_date.isoformat(),
        "status": "scheduled",
    }
