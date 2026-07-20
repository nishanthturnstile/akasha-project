"""Add has_variety column to crops table.

Revision ID: 20260719_0004
Revises: d9b2c43a8f10
Create Date: 2026-07-19 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from app.models import AKASHA_SCHEMA

revision = "20260719_0004"
down_revision = "d9b2c43a8f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crops",
        sa.Column("has_variety", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema=AKASHA_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("crops", "has_variety", schema=AKASHA_SCHEMA)
