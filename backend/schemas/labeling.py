"""Public HTTP contracts for the master labeling queue."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProblemDetails(PublicModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    correlationId: UUID
    context: dict[str, Any] | None = None


class ClientSummary(PublicModel):
    code: str
    displayName: str


class ScenarioSummary(PublicModel):
    title: str


class SessionSummary(PublicModel):
    startedAt: datetime | None
    finishedAt: datetime | None
    durationSeconds: float | None


class ReportSummary(PublicModel):
    reportId: UUID
    generatedAt: datetime
    overallScore: float | None


class CriticalArea(PublicModel):
    areaKey: str
    label: str
    value: float


class LeaseView(PublicModel):
    state: Literal["available", "owned", "locked_by_other", "expired", "not_claimable"]
    ownerCode: str | None
    expiresAt: datetime | None


class ReviewSummary(PublicModel):
    reviewId: UUID
    reviewNo: int = Field(ge=1)
    reviewerCode: str
    submittedAt: datetime


class LabelingCaseItem(PublicModel):
    caseId: UUID
    caseNumber: str
    status: Literal["pending", "reviewed"]
    queueReason: Literal["critical", "borderline", "disparity", "routine"]
    reasonDetail: dict[str, Any]
    client: ClientSummary
    speakerCode: str
    scenario: ScenarioSummary
    session: SessionSummary
    report: ReportSummary
    criticalAreas: list[CriticalArea]
    lease: LeaseView
    latestReview: ReviewSummary | None


class LabelingCaseList(PublicModel):
    items: list[LabelingCaseItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=10)


class RubricArea(PublicModel):
    areaId: UUID
    areaKey: Literal["expression", "voice", "coherence", "empathy"]
    label: str
    aiValue: float | None
    editable: bool


class RubricSnapshot(PublicModel):
    rubricVersionId: UUID
    areas: list[RubricArea]


class MetricObservation(PublicModel):
    valueType: Literal["decimal", "integer"]
    canonicalUnit: str
    conversion: str
    technicalMin: float | None
    technicalMax: float | None


class MetricSnapshot(PublicModel):
    metricKey: str
    categoryKey: str
    metricKind: Literal["observation", "configuration", "aggregate_target"]
    label: str
    availability: Literal["available", "unknown", "not_emitted"]
    aiValue: float | None
    unit: str
    precision: int = Field(ge=0, le=8)
    mappingVersion: int = Field(ge=1)
    observation: MetricObservation | None
    editable: bool
    unavailableReason: str | None
    publishedThresholds: dict[str, float]


class MetricGroup(PublicModel):
    categoryKey: str
    label: str
    metrics: list[MetricSnapshot]


class RecordingSummary(PublicModel):
    availability: Literal["available", "unavailable"]
    durationSeconds: float | None


class LabelingCaseDetail(LabelingCaseItem):
    contentRevision: int = Field(ge=1)
    sourceStatus: Literal["complete", "partial", "ambiguous"]
    sourceIssues: list[str]
    snapshotSchemaVersion: int = Field(ge=1)
    rubric: RubricSnapshot
    metricGroups: list[MetricGroup]
    recording: RecordingSummary
    currentReview: ReviewSummary | None


class LeaseRequest(PublicModel):
    leaseToken: str | None = Field(default=None, min_length=32, max_length=256)
    leaseGeneration: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def matching_pair(self):
        if (self.leaseToken is None) != (self.leaseGeneration is None):
            raise ValueError("leaseToken y leaseGeneration deben enviarse juntos.")
        return self


class LeaseResponse(PublicModel):
    caseId: UUID
    leaseToken: str
    leaseGeneration: int = Field(ge=1)
    contentRevision: int = Field(ge=1)
    expiresAt: datetime
    serverTime: datetime
    readOnly: bool


class ReleaseLeaseRequest(PublicModel):
    leaseToken: str = Field(min_length=32, max_length=256)
    leaseGeneration: int = Field(ge=1)


class RecordingUrlResponse(PublicModel):
    url: str
    expiresAt: datetime
    contentType: str
    durationSeconds: float | None
    etag: str
    blobVersionId: str | None


class RubricCorrectionRequest(PublicModel):
    areaId: UUID
    correctedValue: Decimal = Field(ge=0, le=100, decimal_places=2)
    comment: str | None = Field(default=None, max_length=2000)


class MetricCorrectionRequest(PublicModel):
    metricKey: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9_.-]+$")
    correctedValue: Decimal
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRequest(PublicModel):
    leaseToken: str = Field(min_length=32, max_length=256)
    leaseGeneration: int = Field(ge=1)
    expectedContentRevision: int = Field(ge=1)
    idempotencyKey: UUID
    supersedesReviewId: UUID | None = None
    overallComment: str = Field(min_length=1, max_length=4000)
    rubricCorrections: list[RubricCorrectionRequest] = Field(min_length=1, max_length=4)
    metricCorrections: list[MetricCorrectionRequest] = Field(default_factory=list, max_length=100)

    @field_validator("overallComment")
    @classmethod
    def normalize_required_comment(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("overallComment es obligatorio.")
        return normalized

    @field_validator("rubricCorrections", "metricCorrections")
    @classmethod
    def reject_duplicates(cls, values):
        keys = [str(getattr(value, "areaId", getattr(value, "metricKey", ""))).lower() for value in values]
        if len(keys) != len(set(keys)):
            raise ValueError("No se permiten correcciones duplicadas.")
        return values


class RubricCorrectionResponse(PublicModel):
    areaKey: str
    aiValue: float
    correctedValue: float
    comment: str | None


class MetricCorrectionResponse(PublicModel):
    metricKey: str
    aiValue: float
    correctedValue: float
    unit: str
    comment: str | None


class ReviewResponse(PublicModel):
    reviewId: UUID
    caseId: UUID
    reviewNo: int = Field(ge=1)
    reviewerCode: str
    isCurrent: bool
    supersedesReviewId: UUID | None
    submittedAt: datetime
    contentRevision: int = Field(ge=1)
    overallComment: str
    rubricCorrections: list[RubricCorrectionResponse]
    metricCorrections: list[MetricCorrectionResponse]


class ReviewListResponse(PublicModel):
    items: list[ReviewResponse]
    total: int = Field(ge=0)


class AggregateBase(PublicModel):
    sampleCount: int = Field(ge=0)
    meanAiValue: float | None
    meanCorrectedValue: float | None
    meanDelta: float | None
    meanAbsoluteError: float | None
    changedCount: int = Field(ge=0)
    increasedCount: int = Field(ge=0)
    decreasedCount: int = Field(ge=0)
    unchangedCount: int = Field(ge=0)


class RubricAggregate(AggregateBase):
    rubricVersionId: UUID
    areaKey: str


class MetricAggregate(AggregateBase):
    metricKey: str
    mappingVersion: int = Field(ge=1)
    unit: str


class CategoryAggregate(PublicModel):
    categoryKey: str
    reviewedMetricCount: int = Field(ge=0)
    changedCount: int = Field(ge=0)


class Period(PublicModel):
    from_: datetime | None = Field(alias="from")
    to: datetime | None


class QualitySummaryResponse(PublicModel):
    period: Period
    currentReviewsOnly: bool
    reviewedCases: int = Field(ge=0)
    rubricAreas: list[RubricAggregate]
    metrics: list[MetricAggregate]
    categories: list[CategoryAggregate]
