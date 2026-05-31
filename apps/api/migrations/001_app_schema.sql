-- Akasha app schema (Slice 1) — PostgreSQL + PostGIS.
--
-- Owned by the `api` (BFF) data model. Catalog data (collections/items/assets)
-- lives in the `pgstac` schema managed by pypgstac — NOT duplicated here.
--
-- Idempotent: safe to run repeatedly. Statements are separated by a `--;;`
-- sentinel so the migration runner can split reliably (dollar-quoted function
-- bodies contain semicolons).

CREATE EXTENSION IF NOT EXISTS postgis
--;;
CREATE SCHEMA IF NOT EXISTS akasha
--;;
-- updated_at trigger helper
CREATE OR REPLACE FUNCTION akasha.set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
--;;
-- Named user plots (WGS84 polygons).
CREATE TABLE IF NOT EXISTS akasha.plots (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    geometry    geometry(Polygon, 4326) NOT NULL,
    area_ha     double precision,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT plots_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT plots_geometry_valid CHECK (ST_IsValid(geometry))
)
--;;
CREATE INDEX IF NOT EXISTS plots_geometry_gix ON akasha.plots USING GIST (geometry)
--;;
CREATE INDEX IF NOT EXISTS plots_created_at_idx ON akasha.plots (created_at DESC)
--;;
DROP TRIGGER IF EXISTS plots_set_updated_at ON akasha.plots
--;;
CREATE TRIGGER plots_set_updated_at BEFORE UPDATE ON akasha.plots
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
-- Optional: index request audit (debugging / rate-limit insight).
CREATE TABLE IF NOT EXISTS akasha.index_requests (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        text NOT NULL,
    acquisition_date date,
    index_type       text NOT NULL,
    plot_id          uuid REFERENCES akasha.plots(id) ON DELETE SET NULL,
    geometry         geometry(Polygon, 4326),
    status           text NOT NULL DEFAULT 'pending',
    duration_ms      integer,
    error_summary    text,
    created_at       timestamptz NOT NULL DEFAULT now()
)
--;;
CREATE INDEX IF NOT EXISTS index_requests_created_at_idx ON akasha.index_requests (created_at DESC)
--;;
-- Optional: key/value app settings (AOI config, defaults, limits).
CREATE TABLE IF NOT EXISTS akasha.app_settings (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
)
--;;
DROP TRIGGER IF EXISTS app_settings_set_updated_at ON akasha.app_settings
--;;
CREATE TRIGGER app_settings_set_updated_at BEFORE UPDATE ON akasha.app_settings
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
--;;
-- Seed default AOI/config rows (idempotent).
INSERT INTO akasha.app_settings (key, value) VALUES
    ('aoi', '{"id":"bangalore","name":"Bangalore","center":[77.59,12.97],"zoom":11,"bounds":[77.4,12.8,77.8,13.2]}'::jsonb),
    ('default_source_id', '"sentinel-2-l2a"'::jsonb),
    ('default_index', '"NDVI"'::jsonb),
    ('max_polygon_area_ha', '50'::jsonb),
    ('max_polygon_vertices', '5000'::jsonb),
    ('usable_pixel_threshold_percent', '70'::jsonb)
ON CONFLICT (key) DO NOTHING
