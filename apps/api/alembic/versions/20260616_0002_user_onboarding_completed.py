"""Add persisted user onboarding completion flag.

Revision ID: 20260616_0002
Revises: 20260609_0001
Create Date: 2026-06-16 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.models import AKASHA_SCHEMA

revision = "20260616_0002"
down_revision = "20260609_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {AKASHA_SCHEMA}.users
        ADD COLUMN IF NOT EXISTS onboarding_completed boolean NOT NULL DEFAULT false
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE {AKASHA_SCHEMA}.users
        DROP COLUMN IF EXISTS onboarding_completed
        """
    )