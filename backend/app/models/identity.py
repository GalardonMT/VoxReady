"""Identity and multi-tenant module: client, app_user."""
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, SoftDeleteMixin, pk


class Client(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "client"
    __table_args__ = (
        sa.CheckConstraint("status IN ('active','suspended')", name="ck_client_status"),
    )

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(sa.String(150))
    status: Mapped[str] = mapped_column(sa.String(20), default="active")


class AppUser(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('spokesperson','client_admin','master_config')",
            name="ck_app_user_role",
        ),
        sa.CheckConstraint(
            "preferred_language IN ('es','en','pt')", name="ck_app_user_language"
        ),
        sa.CheckConstraint(
            "status IN ('active','deactivated')", name="ck_app_user_status"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    b2c_object_id: Mapped[str] = mapped_column(sa.String(100), unique=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("client.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(sa.String(256))
    display_name: Mapped[str] = mapped_column(sa.String(150))
    role: Mapped[str] = mapped_column(sa.String(20))
    preferred_language: Mapped[str] = mapped_column(sa.String(2), default="es")
    status: Mapped[str] = mapped_column(sa.String(20), default="active")
