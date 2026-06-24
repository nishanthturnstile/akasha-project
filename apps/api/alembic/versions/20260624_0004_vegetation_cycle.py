"""Create vegetation_cycles table.

Revision ID: 20260624_0004
Revises: 20260623_0003
Create Date: 2026-06-24 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.models import AKASHA_SCHEMA, Base

revision = "20260624_0004"
down_revision = "20260623_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.vegetation_cycles CASCADE")
