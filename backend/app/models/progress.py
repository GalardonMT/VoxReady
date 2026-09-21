"""Progress module: area progress, recommendations, microlessons, schedule."""
import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, SoftDeleteMixin, pk


class UserAreaProgress(AuditMixin, Base):
    __tablename__ = "user_area_progress"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    rubric_area_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_area.id"), nullable=False
    )
    current_value: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    delta: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    sessions_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    last_session_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


class Recommendation(AuditMixin, Base):
    __tablename__ = "recommendation"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('generated','manual')", name="ck_recommendation_source"
        ),
        sa.CheckConstraint(
            "status IN ('active','dismissed')", name="ck_recommendation_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(150))
    detail: Mapped[str] = mapped_column(sa.String(500))
    microlesson_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("microlesson.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(sa.String(20), default="generated")
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class Microlesson(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "microlesson"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_microlesson_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(150))
    topic_tag: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    video_blob_path: Mapped[str | None] = mapped_column(sa.String(400), nullable=True)
    example_content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class Schedule(AuditMixin, Base):
    __tablename__ = "schedule"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('scheduled','completed','cancelled')", name="ck_schedule_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    scheduled_date: Mapped[date] = mapped_column(sa.Date)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("scenario.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(sa.String(20), default="scheduled")
