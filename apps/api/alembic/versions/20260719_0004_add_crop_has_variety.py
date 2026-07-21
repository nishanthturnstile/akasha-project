"""Add has_variety column to crops table.

Revision ID: 20260719_0004
Revises: 20260707_0006
Create Date: 2026-07-19 00:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260719_0004"
down_revision = "20260707_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crops", sa.Column("has_variety", sa.Boolean(), nullable=False, server_default=sa.text("false")), schema="akasha")


def downgrade() -> None:
    op.drop_column("crops", "has_variety", schema="akasha")
