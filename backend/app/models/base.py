"""Declarative base, audit mixins and portable column types."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils import utcnow

# Portable JSON: JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite tests).
JSONType = sa.JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)


def pk() -> Mapped[uuid.UUID]:
    """Standard UUID v4 primary key column."""
    return mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
