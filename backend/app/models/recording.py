"""Recording storage module: recording metadata and exports."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, pk
from app.utils import utcnow


class Recording(AuditMixin, Base):
    __tablename__ = "recording"
    __table_args__ = (
        sa.CheckConstraint(
            "storage_tier IN ('hot','cool','archive')", name="ck_recording_tier"
        ),
        sa.CheckConstraint(
            "status IN ('available','archived','deleted')", name="ck_recording_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    blob_container: Mapped[str] = mapped_column(sa.String(100))
    blob_path: Mapped[str] = mapped_column(sa.String(400))
    content_type: Mapped[str] = mapped_column(sa.String(50))
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    storage_tier: Mapped[str] = mapped_column(sa.String(20), default="hot")
    status: Mapped[str] = mapped_column(sa.String(20), default="available")
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


class RecordingExport(AuditMixin, Base):
    __tablename__ = "recording_export"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('requested','completed','failed')",
            name="ck_recording_export_status",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    recording_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("recording.id"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    target_path: Mapped[str | None] = mapped_column(sa.String(400), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="requested")
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
