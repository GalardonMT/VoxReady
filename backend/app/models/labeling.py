"""Labeling module: review queue, expert corrections and agreement metric."""
import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, pk
from app.utils import utcnow


class LabelingCase(AuditMixin, Base):
    __tablename__ = "labeling_case"
    __table_args__ = (
        sa.CheckConstraint(
            "reason IN ('low_confidence','borderline','random')",
            name="ck_labeling_case_reason",
        ),
        sa.CheckConstraint(
            "status IN ('pending','resolved')", name="ck_labeling_case_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(sa.String(20))
    status: Mapped[str] = mapped_column(sa.String(20), default="pending")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


class LabelingCorrection(AuditMixin, Base):
    __tablename__ = "labeling_correction"
    __table_args__ = (
        sa.CheckConstraint("ai_value BETWEEN 0 AND 100", name="ck_correction_ai"),
        sa.CheckConstraint(
            "corrected_value BETWEEN 0 AND 100", name="ck_correction_corrected"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    labeling_case_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("labeling_case.id"), nullable=False
    )
    rubric_area_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_area.id"), nullable=False
    )
    ai_value: Mapped[int] = mapped_column(sa.Integer)
    corrected_value: Mapped[int] = mapped_column(sa.Integer)
    comment: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )


class AiHumanAgreementMetric(AuditMixin, Base):
    __tablename__ = "ai_human_agreement_metric"

    id: Mapped[uuid.UUID] = pk()
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(sa.Date)
    period_end: Mapped[date] = mapped_column(sa.Date)
    agreement: Mapped[Decimal] = mapped_column(sa.Numeric(4, 3))
    sample_size: Mapped[int] = mapped_column(sa.Integer)
    computed_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
