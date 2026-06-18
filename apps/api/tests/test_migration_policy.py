from __future__ import annotations

from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
DRIFT_MIGRATION = API_ROOT / "alembic/versions/d9b2c43a8f10_repair_fields_seasons_schema_drift.py"


def test_future_alembic_filenames_include_timestamp_revision_and_slug():
    alembic_ini = (API_ROOT / "alembic.ini").read_text()

    expected_template = (
        "file_template = "
        "%%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s"
    )
    assert expected_template in alembic_ini


def test_schema_drift_migration_repairs_fields_and_seasons_tables():
    migration = DRIFT_MIGRATION.read_text()

    assert 'revision = "d9b2c43a8f10"' in migration
    assert 'down_revision = "20260616_0002"' in migration
    assert "Base.metadata.create_all" not in migration
    for table in ("seasons", "fields", "field_seasons"):
        assert f"CREATE TABLE IF NOT EXISTS {{AKASHA_SCHEMA}}.{table}" in migration

    for index_name in (
        "fields_geometry_gix",
        "fields_user_idx",
        "field_seasons_field_idx",
        "field_seasons_season_idx",
    ):
        assert f"CREATE INDEX IF NOT EXISTS {index_name}" in migration

    assert '_create_updated_at_trigger("fields")' in migration
    assert '_create_updated_at_trigger("seasons")' in migration


def test_schema_drift_migration_updates_only_legacy_app_settings_defaults():
    migration = DRIFT_MIGRATION.read_text()

    assert "resourcesat-2a-liss3-boa" in migration
    assert "sentinel-2-l2a" in migration
    assert "bangalore-60km" in migration
    assert "WHERE key = 'default_source_id'" in migration
    assert "WHERE key = 'aoi'" in migration
