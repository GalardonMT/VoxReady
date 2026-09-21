"""Initial schema: all VoxReady tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-26
"""
import app.models  # noqa: F401 - ensure all tables are registered
from app.models.base import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from alembic import op

    Base.metadata.drop_all(op.get_bind())
