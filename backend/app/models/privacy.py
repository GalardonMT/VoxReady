"""Privacy module: retention policies, deletion requests and audit log."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, JSONType, pk
from app.utils import utcnow


class RetentionPolicy(AuditMixin, Base):
    __tablename__ = "retention_policy"
    __table_args__ = (
        sa.CheckConstraint(
            "keep IN ('full_recording','metrics_only')", name="ck_retention_keep"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    keep: Mapped[str] = mapped_column(sa.String(20))
    term_days: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    version_label: Mapped[str] = mapped_column(sa.String(20))
    is_current: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    effective_from: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )


class DeletionRequest(AuditMixin, Base):
    __tablename__ = "deletion_request"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending','processed')", name="ck_deletion_request_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="pending")
    requested_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    processed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=True
    )


class AuditEvent(AuditMixin, Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(sa.String(40))
    entity_type: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    detail_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
