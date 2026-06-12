"""Fresh SQLAlchemy ORM baseline for API-owned app schema.

Revision ID: 20260609_0001
Revises:
Create Date: 2026-06-09 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.auth import DEV_TEAM_ID, DEV_USER_ID
from app.models import AKASHA_SCHEMA, Base

revision = "20260609_0001"
down_revision = None
branch_labels = None
depends_on = None

UPDATED_AT_TABLES = (
    "plots",
    "app_settings",
    "report_templates",
    "field_groups",
    "attachments",
    "field_activities",
    "scout_tasks",
    "uploaded_datasets",
    "users",
    "teams",
    "notifications",
    "fields",
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {AKASHA_SCHEMA}")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {AKASHA_SCHEMA}.set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    Base.metadata.create_all(bind=bind)
    _create_updated_at_triggers()
    _seed_app_settings()
    _seed_dev_principal()


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute(f"DROP FUNCTION IF EXISTS {AKASHA_SCHEMA}.set_updated_at()")
    op.execute(f"DROP SCHEMA IF EXISTS {AKASHA_SCHEMA}")


def _create_updated_at_triggers() -> None:
    for table in UPDATED_AT_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {AKASHA_SCHEMA}.{table}")
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
            BEFORE UPDATE ON {AKASHA_SCHEMA}.{table}
            FOR EACH ROW EXECUTE FUNCTION {AKASHA_SCHEMA}.set_updated_at()
            """
        )


def _seed_app_settings() -> None:
    op.get_bind().exec_driver_sql(
        f"""
        INSERT INTO {AKASHA_SCHEMA}.app_settings (key, value) VALUES
            (
                'aoi',
                '{{"id":"bangalore","name":"Bangalore","center":[77.59,12.97],'
                '"zoom":11,"bounds":[77.4,12.8,77.8,13.2]}}'::jsonb
            ),
            ('default_source_id', '"sentinel-2-l2a"'::jsonb),
            ('default_index', '"NDVI"'::jsonb),
            ('max_polygon_area_ha', '50'::jsonb),
            ('max_polygon_vertices', '5000'::jsonb),
            ('usable_pixel_threshold_percent', '70'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )


def _seed_dev_principal() -> None:
    op.execute(
        f"""
        INSERT INTO {AKASHA_SCHEMA}.users (
            id, email, username, display_name, status
        )
        VALUES (
            '{DEV_USER_ID}'::uuid,
            'dev@akasha.local',
            'dev',
            'Akasha Dev User',
            'active'
        )
        ON CONFLICT (id) DO UPDATE
        SET email = EXCLUDED.email,
            username = EXCLUDED.username,
            display_name = EXCLUDED.display_name,
            status = EXCLUDED.status
        """
    )
    op.execute(
        f"""
        INSERT INTO {AKASHA_SCHEMA}.teams (id, name, created_by)
        VALUES (
            '{DEV_TEAM_ID}'::uuid,
            'Akasha Dev Team',
            '{DEV_USER_ID}'::uuid
        )
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            created_by = COALESCE({AKASHA_SCHEMA}.teams.created_by, EXCLUDED.created_by)
        """
    )
    op.execute(
        f"""
        INSERT INTO {AKASHA_SCHEMA}.memberships (team_id, user_id, role)
        VALUES ('{DEV_TEAM_ID}'::uuid, '{DEV_USER_ID}'::uuid, 'owner')
        ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role
        """
    )
