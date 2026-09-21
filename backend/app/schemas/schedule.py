"""Request schemas for the spokesperson schedule endpoint."""
from pydantic import BaseModel


class ScheduleIn(BaseModel):
    date: str
    scenarioId: str | None = None
