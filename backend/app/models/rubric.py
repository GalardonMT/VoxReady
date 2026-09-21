"""Master rubric module: versioned rubric, areas and level descriptors."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, JSONType, pk


class RubricVersion(AuditMixin, Base):
    __tablename__ = "rubric_version"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('draft','published')", name="ck_rubric_version_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    version_label: Mapped[str] = mapped_column(sa.String(20), unique=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="draft")
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    # Languages with voice-rubric tuning (returned by GET /v1/master/rubric).
    languages: Mapped[list] = mapped_column(JSONType, default=list)


class RubricArea(AuditMixin, Base):
    __tablename__ = "rubric_area"
    __table_args__ = (
        sa.CheckConstraint("weight BETWEEN 0 AND 100", name="ck_rubric_area_weight"),
    )

    id: Mapped[uuid.UUID] = pk()
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    area_key: Mapped[str] = mapped_column(sa.String(30))
    name: Mapped[str] = mapped_column(sa.String(60))
    channel: Mapped[str] = mapped_column(sa.String(60))
    criteria: Mapped[str] = mapped_column(sa.String(500))
    weight: Mapped[int] = mapped_column(sa.Integer)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)


class RubricDescriptor(AuditMixin, Base):
    __tablename__ = "rubric_descriptor"
    __table_args__ = (
        sa.CheckConstraint(
            "level IN ('high','medium','low')", name="ck_rubric_descriptor_level"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    rubric_area_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_area.id"), nullable=False
    )
    level: Mapped[str] = mapped_column(sa.String(10))
    description: Mapped[str] = mapped_column(sa.String(1000))
