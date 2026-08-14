"""Create crop growth stages table.

Revision ID: 20260813_0008
Revises: 20260724_0007
Create Date: 2026-08-13 00:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260813_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None

SCHEMA = "akasha"


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("crop_growth_stages", schema=SCHEMA):
        return

    op.create_table(
        "crop_growth_stages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("duration", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["crop_id"],
            [f"{SCHEMA}.crops.id"],
            name="crop_growth_stages_crop_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crop_id", "seq", name="crop_growth_stages_crop_id_seq_key"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("crop_growth_stages", schema=SCHEMA)
