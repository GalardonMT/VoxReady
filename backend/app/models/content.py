"""Content configuration module: topics, scenarios and question bank."""
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, JSONType, SoftDeleteMixin, pk


class Topic(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "topic"
    __table_args__ = (
        sa.CheckConstraint(
            "optics IN ('empathetic','formal','technical')", name="ck_topic_optics"
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_topic_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(150))
    context: Mapped[str] = mapped_column(sa.Text)
    optics: Mapped[str] = mapped_column(sa.String(20))
    audience: Mapped[str] = mapped_column(sa.String(50))
    # API contract requires the enabled languages on the topic; stored as JSON.
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class TopicKeyMessage(AuditMixin, Base):
    __tablename__ = "topic_key_message"

    id: Mapped[uuid.UUID] = pk()
    topic_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("topic.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(sa.String(500))
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)


class TopicRedLine(AuditMixin, Base):
    __tablename__ = "topic_red_line"

    id: Mapped[uuid.UUID] = pk()
    topic_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("topic.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(sa.String(500))
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0)


class Scenario(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "scenario"
    __table_args__ = (
        sa.CheckConstraint(
            "category IN ('health','reputational','operational')",
            name="ck_scenario_category",
        ),
        sa.CheckConstraint(
            "difficulty IN ('basic','intermediate','hard')",
            name="ck_scenario_difficulty",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name="ck_scenario_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    topic_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("topic.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(150))
    category: Mapped[str] = mapped_column(sa.String(20))
    difficulty: Mapped[str] = mapped_column(sa.String(20))
    estimated_minutes: Mapped[int] = mapped_column(sa.Integer)
    question_count: Mapped[int] = mapped_column(sa.Integer)
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class Question(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "question"
    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('ai','admin','imported')", name="ck_question_source"
        ),
        sa.CheckConstraint(
            "base_language IN ('es','en','pt')", name="ck_question_language"
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')", name="ck_question_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("topic.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(sa.String(500))
    source: Mapped[str] = mapped_column(sa.String(20), default="ai")
    base_language: Mapped[str] = mapped_column(sa.String(2), default="es")
    avg_rating: Mapped[Decimal | None] = mapped_column(sa.Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    in_bank: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class QuestionRating(AuditMixin, Base):
    __tablename__ = "question_rating"
    __table_args__ = (
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_question_rating_value"),
    )

    id: Mapped[uuid.UUID] = pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("question.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("session.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("app_user.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(sa.Integer)
