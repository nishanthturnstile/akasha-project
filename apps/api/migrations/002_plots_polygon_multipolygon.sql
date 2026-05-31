-- Akasha Slice 3 — allow BOTH Polygon and MultiPolygon plot geometries.
--
-- Wave 1 product docs accept GeoJSON Polygon and MultiPolygon, but the Slice 1
-- table restricted the column to geometry(Polygon, 4326). This migration relaxes
-- the column to a generic geometry(Geometry, 4326) and enforces the allowed
-- subtypes + topological validity via a CHECK constraint instead.
--
-- Idempotent and non-destructive:
--   * preserves existing rows (no Polygon -> MultiPolygon coercion),
--   * keeps SRID 4326,
--   * keeps an ST_IsValid() check,
--   * preserves/recreates the GIST index.
--
-- Statements separated by the repo `--;;` sentinel (see app/cli.py).

-- 1) Relax the column geometry type (Polygon -> generic Geometry), keeping SRID.
ALTER TABLE akasha.plots
    ALTER COLUMN geometry TYPE geometry(Geometry, 4326)
    USING ST_SetSRID(geometry, 4326)
--;;
-- 2) Drop the old validity-only constraint (Slice 1) if present.
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_geometry_valid
--;;
-- 3) Drop our type constraint too (so re-running this migration is idempotent).
ALTER TABLE akasha.plots DROP CONSTRAINT IF EXISTS plots_geometry_type_chk
--;;
-- 4) Enforce: only POLYGON or MULTIPOLYGON, and only valid topology.
ALTER TABLE akasha.plots
    ADD CONSTRAINT plots_geometry_type_chk
    CHECK (
        GeometryType(geometry) IN ('POLYGON', 'MULTIPOLYGON')
        AND ST_IsValid(geometry)
    )
--;;
-- 5) Ensure the spatial GIST index still exists (recreated if the type change
--    dropped it).
CREATE INDEX IF NOT EXISTS plots_geometry_gix ON akasha.plots USING GIST (geometry)
