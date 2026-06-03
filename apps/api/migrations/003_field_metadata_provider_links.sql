-- Akasha Phase 1 — field metadata and provider links for plots.
--
-- Adds user-editable field metadata plus provider/adapter-owned link fields
-- to the existing akasha.plots table without changing or duplicating geometry.
--
-- Statements separated by the repo `--;;` sentinel (see app/cli.py).

ALTER TABLE akasha.plots
    ADD COLUMN IF NOT EXISTS group_name text,
    ADD COLUMN IF NOT EXISTS crop_type text,
    ADD COLUMN IF NOT EXISTS variety text,
    ADD COLUMN IF NOT EXISTS season_label text,
    ADD COLUMN IF NOT EXISTS sowing_date date,
    ADD COLUMN IF NOT EXISTS planting_date date,
    ADD COLUMN IF NOT EXISTS status text,
    ADD COLUMN IF NOT EXISTS external_provider text,
    ADD COLUMN IF NOT EXISTS external_field_id text,
    ADD COLUMN IF NOT EXISTS provider_sync_status text,
    ADD COLUMN IF NOT EXISTS provider_synced_at timestamptz,
    ADD COLUMN IF NOT EXISTS provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
--;;
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_status_chk
--;;
ALTER TABLE akasha.plots
    ADD CONSTRAINT plots_status_chk
    CHECK (status IS NULL OR status IN ('planned', 'active', 'inactive', 'archived'))
--;;
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_provider_sync_status_chk
--;;
ALTER TABLE akasha.plots
    ADD CONSTRAINT plots_provider_sync_status_chk
    CHECK (
        provider_sync_status IS NULL
        OR provider_sync_status IN ('not_synced', 'pending', 'synced', 'failed')
    )
--;;
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_provider_metadata_object_chk
--;;
ALTER TABLE akasha.plots
    ADD CONSTRAINT plots_provider_metadata_object_chk
    CHECK (jsonb_typeof(provider_metadata) = 'object')
--;;
CREATE UNIQUE INDEX IF NOT EXISTS plots_external_provider_field_uidx
    ON akasha.plots (external_provider, external_field_id)
    WHERE external_provider IS NOT NULL AND external_field_id IS NOT NULL
--;;
CREATE INDEX IF NOT EXISTS plots_status_idx ON akasha.plots (status)
--;;
CREATE INDEX IF NOT EXISTS plots_provider_sync_status_idx
    ON akasha.plots (provider_sync_status)
