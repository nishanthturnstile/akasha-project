"""Add the per-user optical cloud threshold.

Revision ID: 20260814_0008
Revises: 20260724_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260814_0008"
down_revision = "20260724_0007"
branch_labels = None
depends_on = None

SCHEMA = "akasha"
COLUMN = "optical_cloud_threshold_percent"
CONSTRAINT = "users_optical_cloud_threshold_percent_chk"


def _column_exists() -> bool:
    inspector = inspect(op.get_bind())
    return COLUMN in {column["name"] for column in inspector.get_columns("users", schema=SCHEMA)}


def _constraint_exists() -> bool:
    inspector = inspect(op.get_bind())
    return any(
        constraint.get("name") == CONSTRAINT
        for constraint in inspector.get_check_constraints("users", schema=SCHEMA)
    )


def upgrade() -> None:
    if not _column_exists():
        op.add_column(
            "users",
            sa.Column(
                COLUMN,
                sa.Integer(),
                nullable=False,
                server_default=sa.text("20"),
            ),
            schema=SCHEMA,
        )
    if not _constraint_exists():
        op.create_check_constraint(
            CONSTRAINT,
            "users",
            f"{COLUMN} BETWEEN 0 AND 70",
            schema=SCHEMA,
        )


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT, "users", schema=SCHEMA, type_="check")
    if _column_exists():
        op.drop_column("users", COLUMN, schema=SCHEMA)
