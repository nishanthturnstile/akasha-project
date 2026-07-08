"""Create predefined_seasons table.

Revision ID: 20260707_0006
Revises: 20260703_0005
Create Date: 2026-07-07 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.models import AKASHA_SCHEMA, Base

revision = "20260707_0006"
down_revision = "20260703_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.predefined_seasons CASCADE")
