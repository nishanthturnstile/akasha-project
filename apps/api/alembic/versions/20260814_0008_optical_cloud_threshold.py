"""Add the per-user optical cloud threshold.

Revision ID: 20260814_0008
Revises: 20260724_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260814_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None

SCHEMA = "akasha"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "optical_cloud_threshold_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("20"),
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "users_optical_cloud_threshold_percent_chk",
        "users",
        "optical_cloud_threshold_percent BETWEEN 0 AND 70",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "users_optical_cloud_threshold_percent_chk",
        "users",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("users", "optical_cloud_threshold_percent", schema=SCHEMA)
