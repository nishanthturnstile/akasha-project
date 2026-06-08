-- Akasha Phase 1 — field metadata for plots.
--
-- Adds user-editable field metadata to the existing akasha.plots table without
-- changing or duplicating geometry.
--
-- Statements separated by the repo `--;;` sentinel (see app/cli.py).

ALTER TABLE akasha.plots
    ADD COLUMN IF NOT EXISTS group_name text,
    ADD COLUMN IF NOT EXISTS crop_type text,
    ADD COLUMN IF NOT EXISTS variety text,
    ADD COLUMN IF NOT EXISTS season_label text,
    ADD COLUMN IF NOT EXISTS sowing_date date,
    ADD COLUMN IF NOT EXISTS planting_date date,
    ADD COLUMN IF NOT EXISTS status text
--;;
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_status_chk
--;;
ALTER TABLE akasha.plots
    ADD CONSTRAINT plots_status_chk
    CHECK (status IS NULL OR status IN ('planned', 'active', 'inactive', 'archived'))
--;;
CREATE INDEX IF NOT EXISTS plots_status_idx ON akasha.plots (status)
