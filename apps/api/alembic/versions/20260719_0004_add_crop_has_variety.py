"""Add has_variety column to crops table.

Column already exists because 20260623_0003 uses Base.metadata.create_all()
which picks up the current ORM model (Crop.has_variety). This revision exists
only to bridge the previous branch into the main chain — upgrade is a no-op.

Revision ID: 20260719_0004
Revises: 20260707_0006
Create Date: 2026-07-19 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260719_0004"
down_revision = "20260707_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
