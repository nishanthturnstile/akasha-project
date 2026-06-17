"""Repair fields/seasons schema drift on pre-existing local volumes.

Revision ID: d9b2c43a8f10
Revises: 20260616_0002
Create Date: 2026-06-17 00:00:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
from app.models import AKASHA_SCHEMA

revision = "d9b2c43a8f10"
down_revision = "20260616_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
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

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AKASHA_SCHEMA}.seasons (
            season_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES {AKASHA_SCHEMA}.users(id) ON DELETE CASCADE,
            name text NOT NULL,
            start_date date,
            end_date date,
            can_delete boolean NOT NULL DEFAULT true,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            CONSTRAINT seasons_name_not_blank CHECK (length(btrim(name)) > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AKASHA_SCHEMA}.fields (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES {AKASHA_SCHEMA}.users(id) ON DELETE CASCADE,
            name text NOT NULL,
            area_ha double precision,
            geometry geometry(GEOMETRY, 4326) NOT NULL,
            group_id uuid REFERENCES {AKASHA_SCHEMA}.field_groups(id) ON DELETE SET NULL,
            created_at timestamp with time zone NOT NULL DEFAULT now(),
            updated_at timestamp with time zone NOT NULL DEFAULT now(),
            CONSTRAINT fields_name_not_blank CHECK (length(btrim(name)) > 0),
            CONSTRAINT fields_geometry_type_chk CHECK (
                GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON') AND ST_IsValid(geometry)
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AKASHA_SCHEMA}.field_seasons (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            field_id uuid NOT NULL REFERENCES {AKASHA_SCHEMA}.fields(id) ON DELETE CASCADE,
            season_id uuid NOT NULL REFERENCES {AKASHA_SCHEMA}.seasons(season_id) ON DELETE CASCADE,
            CONSTRAINT field_seasons_unique_pair UNIQUE (season_id, field_id)
        )
        """
    )

    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS fields_geometry_gix
        ON {AKASHA_SCHEMA}.fields USING gist (geometry)
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS fields_user_idx ON {AKASHA_SCHEMA}.fields (user_id)")
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS field_seasons_field_idx
        ON {AKASHA_SCHEMA}.field_seasons (field_id)
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS field_seasons_season_idx
        ON {AKASHA_SCHEMA}.field_seasons (season_id)
        """
    )

    _create_updated_at_trigger("fields")
    _create_updated_at_trigger("seasons")
    _update_legacy_app_settings()


def downgrade() -> None:
    # This revision repairs possibly live local/staging data created by newer
    # application code. Downgrading must not drop user fields/seasons.
    pass


def _create_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {AKASHA_SCHEMA}.{table}")
    op.execute(
        f"""
        CREATE TRIGGER {table}_set_updated_at
        BEFORE UPDATE ON {AKASHA_SCHEMA}.{table}
        FOR EACH ROW EXECUTE FUNCTION {AKASHA_SCHEMA}.set_updated_at()
        """
    )


def _update_legacy_app_settings() -> None:
    op.execute(
        f"""
        UPDATE {AKASHA_SCHEMA}.app_settings
        SET value = '"resourcesat-2a-liss3-boa"'::jsonb
        WHERE key = 'default_source_id'
          AND value = '"sentinel-2-l2a"'::jsonb
        """
    )
    op.execute(
        f"""
        UPDATE {AKASHA_SCHEMA}.app_settings
        SET value = '{{
            "id": "bangalore-60km",
            "name": "Bangalore 60 km",
            "center": [77.5776037099731, 13.076858177177233],
            "zoom": 9,
            "bounds": [77.023647, 12.537266, 78.131561, 13.61645]
        }}'::jsonb
        WHERE key = 'aoi'
          AND value->>'id' = 'bangalore'
        """
    )
