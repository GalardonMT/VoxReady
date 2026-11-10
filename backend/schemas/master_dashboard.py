"""Read-only contract for the global master dashboard."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardPeriod(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime


class DashboardWeek(BaseModel):
    timezone: Literal["UTC"] = "UTC"
    period: DashboardPeriod
    previousPeriod: DashboardPeriod
    count: int = Field(ge=0)
    previousCount: int = Field(ge=0)
    changePercent: float | None
    changeStatus: Literal["available", "no_previous_sessions"]


class DashboardVersion(BaseModel):
    id: str
    versionLabel: str
    versionNumber: int
    publishedAt: datetime | None


class DashboardBin(BaseModel):
    label: str
    lowerBound: int
    upperBound: int
    upperInclusive: bool
    count: int = Field(ge=0)


class DashboardDistribution(BaseModel):
    population: Literal["all_completed_current_reports"] = "all_completed_current_reports"
    sampleCount: int = Field(ge=0)
    bins: list[DashboardBin]
    mean: float | None
    standardDeviation: float | None
    standardDeviationKind: Literal["population"] = "population"
    modalRanges: list[str]


class DashboardQuality(BaseModel):
    status: Literal["definition_required"] = "definition_required"
    agreementPercent: None = None
    kappa: None = None


class MasterDashboardResponse(BaseModel):
    generatedAt: datetime
    activeClients: int = Field(ge=0)
    sessionsWeek: DashboardWeek
    pendingReviewCount: int = Field(ge=0)
    publishedVersion: DashboardVersion | None
    scoreDistribution: DashboardDistribution
    quality: DashboardQuality
