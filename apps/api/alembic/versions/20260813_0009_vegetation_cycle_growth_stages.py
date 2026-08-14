"""Create vegetation cycle growth stages table.

Revision ID: 20260813_0009
Revises: 20260813_0008
Create Date: 2026-08-13 00:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260813_0009"
down_revision = "20260813_0008"
branch_labels = None
depends_on = None

SCHEMA = "akasha"


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("vegetation_cycle_growth_stages", schema=SCHEMA):
        return

    op.create_table(
        "vegetation_cycle_growth_stages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vegetation_cycle_id", sa.UUID(), nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("duration", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vegetation_cycle_id"],
            [f"{SCHEMA}.vegetation_cycles.id"],
            name="vegetation_cycle_growth_stages_cycle_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["crop_id"],
            [f"{SCHEMA}.crops.id"],
            name="vegetation_cycle_growth_stages_crop_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vegetation_cycle_id",
            "seq",
            name="vegetation_cycle_growth_stages_cycle_seq_key",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "vegetation_cycle_growth_stages_cycle_idx",
        "vegetation_cycle_growth_stages",
        ["vegetation_cycle_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "vegetation_cycle_growth_stages_crop_idx",
        "vegetation_cycle_growth_stages",
        ["crop_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("vegetation_cycle_growth_stages", schema=SCHEMA)
