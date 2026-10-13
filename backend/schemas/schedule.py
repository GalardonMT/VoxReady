"""Contratos HTTP de la agenda interna del vocero."""
from datetime import date as Date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    date: Date
    scenario_id: UUID = Field(alias="scenarioId")


class ScheduleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    date: Optional[Date] = None
    scenario_id: Optional[UUID] = Field(default=None, alias="scenarioId")

    @model_validator(mode="after")
    def require_change(self):
        if self.date is None and self.scenario_id is None:
            raise ValueError("Debes indicar una nueva fecha o un escenario.")
        return self
