"""Sessions module: practice session state machine, questions and consent."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, JSONType, SoftDeleteMixin, pk


class PracticeSession(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "session"
    __table_args__ = (
        sa.CheckConstraint("language IN ('es','en','pt')", name="ck_session_language"),
        sa.CheckConstraint(
            "status IN ('created','consented','recording','analyzing','completed','failed')",
            name="ck_session_status",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("scenario.id"), nullable=False
    )
    language: Mapped[str] = mapped_column(sa.String(2))
    status: Mapped[str] = mapped_column(sa.String(20), default="created")
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("rubric_version.id"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


class SessionQuestion(AuditMixin, Base):
    __tablename__ = "session_question"

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("question.id"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(sa.Integer)
    asked_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


class Consent(AuditMixin, Base):
    __tablename__ = "consent"

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    accept_recording: Mapped[bool] = mapped_column(sa.Boolean)
    acknowledge_deletion: Mapped[bool] = mapped_column(sa.Boolean)
    retention_policy_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("retention_policy.id"), nullable=False
    )
    consent_hash: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    consented_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)


class IdempotencyKey(Base):
    """Stored responses for Idempotency-Key on sensitive POST operations."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        sa.UniqueConstraint("key", "user_id", name="uq_idempotency_key_user"),
    )

    id: Mapped[uuid.UUID] = pk()
    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
