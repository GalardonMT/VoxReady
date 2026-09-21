"""Multimodal analysis module: jobs, pipeline results, reports and scores."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, JSONType, pk
from app.utils import utcnow


class AnalysisJob(AuditMixin, Base):
    __tablename__ = "analysis_job"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_analysis_job_status",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(sa.String(20), default="queued")
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    estimated_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class AnalysisPipelineResult(AuditMixin, Base):
    __tablename__ = "analysis_pipeline_result"
    __table_args__ = (
        sa.CheckConstraint(
            "pipeline IN ('voice','image','content','fusion')",
            name="ck_pipeline_result_pipeline",
        ),
        sa.CheckConstraint(
            "status IN ('pending','done','failed')", name="ck_pipeline_result_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("analysis_job.id"), nullable=False
    )
    pipeline: Mapped[str] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(sa.String(20), default="pending")
    summary_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    raw_blob_path: Mapped[str | None] = mapped_column(sa.String(400), nullable=True)


class Report(AuditMixin, Base):
    __tablename__ = "report"

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("analysis_job.id"), nullable=False
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    overall_score: Mapped[int] = mapped_column(sa.Integer)
    narrative_strengths: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    narrative_improvements: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    cross_signal_observation: Mapped[str | None] = mapped_column(
        sa.String(1000), nullable=True
    )
    version_no: Mapped[int] = mapped_column(sa.Integer, default=1)
    is_current: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)


class AreaScore(AuditMixin, Base):
    __tablename__ = "area_score"
    __table_args__ = (
        sa.CheckConstraint("value BETWEEN 0 AND 100", name="ck_area_score_value"),
    )

    id: Mapped[uuid.UUID] = pk()
    report_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("report.id"), nullable=False
    )
    rubric_area_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_area.id"), nullable=False
    )
    value: Mapped[int] = mapped_column(sa.Integer)
