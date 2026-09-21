"""Translation cache module."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, pk
from app.utils import utcnow


class Translation(AuditMixin, Base):
    __tablename__ = "translation"
    __table_args__ = (
        sa.CheckConstraint("language IN ('es','en','pt')", name="ck_translation_lang"),
        sa.CheckConstraint(
            "source IN ('machine','human')", name="ck_translation_source"
        ),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "field_name", "language",
            name="uq_translation_entity_field_lang",
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    entity_type: Mapped[str] = mapped_column(sa.String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid)
    field_name: Mapped[str] = mapped_column(sa.String(60))
    language: Mapped[str] = mapped_column(sa.String(2))
    translated_text: Mapped[str] = mapped_column(sa.Text)
    source: Mapped[str] = mapped_column(sa.String(10), default="machine")
    is_overridden: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    translated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow)
