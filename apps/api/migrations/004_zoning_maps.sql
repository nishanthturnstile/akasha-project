-- Akasha Phase 8 — persistent public IDs for provider-backed zoning maps.
--
-- Raw provider map/request identifiers stay server-side in this table. Public API
-- responses expose only the Akasha UUID `id` as mapId.

CREATE TABLE IF NOT EXISTS akasha.zoning_maps (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plot_id             uuid NOT NULL REFERENCES akasha.plots(id) ON DELETE CASCADE,
    provider            text NOT NULL,
    external_zmap_id    text,
    provider_request_id text,
    status              text NOT NULL,
    map_type            text NOT NULL DEFAULT 'vegetation',
    index_type          text,
    image_date          date,
    zone_count          integer,
    min_zone_area_ha    numeric,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT zoning_maps_status_chk CHECK (
        status IN ('processing', 'ready', 'failed', 'unknown')
    ),
    CONSTRAINT zoning_maps_metadata_object_chk CHECK (jsonb_typeof(metadata) = 'object')
)
--;;
CREATE UNIQUE INDEX IF NOT EXISTS zoning_maps_provider_external_uidx
    ON akasha.zoning_maps (provider, external_zmap_id)
    WHERE external_zmap_id IS NOT NULL
--;;
CREATE INDEX IF NOT EXISTS zoning_maps_plot_created_idx
    ON akasha.zoning_maps (plot_id, created_at DESC)
--;;
DROP TRIGGER IF EXISTS zoning_maps_set_updated_at ON akasha.zoning_maps
--;;
CREATE TRIGGER zoning_maps_set_updated_at BEFORE UPDATE ON akasha.zoning_maps
    FOR EACH ROW EXECUTE FUNCTION akasha.set_updated_at()
