"""Merge the growth-stage and optical-cloud migration branches.

Revision ID: 20260814_0009
Revises: 20260813_0009, 20260814_0008
"""

from __future__ import annotations

revision = "20260814_0009"
down_revision = ("20260813_0009", "20260814_0008")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge the already-applied migration branches."""


def downgrade() -> None:
    """Split the migration graph back into its two parent branches."""
