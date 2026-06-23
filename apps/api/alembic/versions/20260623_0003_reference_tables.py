"""Create reference tables: irrigation_types, tillage_types, seeding_types, crops, varieties.

Revision ID: 20260623_0003
Revises: d9b2c43a8f10
Create Date: 2026-06-23 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.models import AKASHA_SCHEMA, Base

revision = "20260623_0003"
down_revision = "d9b2c43a8f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    _seed_seeding_types()


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.varieties CASCADE")
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.crops CASCADE")
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.seeding_types CASCADE")
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.tillage_types CASCADE")
    op.execute(f"DROP TABLE IF EXISTS {AKASHA_SCHEMA}.irrigation_types CASCADE")


def _seed_seeding_types() -> None:
    op.execute(
        f"""
        INSERT INTO {AKASHA_SCHEMA}.seeding_types (name, description) VALUES
            ('direct_seed', 'Seeds sown directly in the field'),
            ('transplant', 'Started in nursery, moved to field'),
            ('planting_cutting', 'Vegetative propagation by cuttings or tubers'),
            ('vine', 'Perennial vine crop'),
            ('perennial_tree', 'Long-lived tree or shrub crop')
        ON CONFLICT (name) DO NOTHING
        """
    )
