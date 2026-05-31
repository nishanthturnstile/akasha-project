import type { StyleSpecification } from 'maplibre-gl';
import type { AppConfig } from '@/types/api';

/**
 * Default basemap: OpenStreetMap raster tiles, full world coverage (zooms 0–19).
 * This is the development default so the whole world is visible out of the box and
 * zooming in reveals street-level detail. For production, set `VITE_BASEMAP_STYLE_URL`
 * (or `config.basemapStyleUrl`) to a self-hosted style — see `resolveBasemapStyle`.
 */
export const OSM_RASTER_STYLE: StyleSpecification = {
  version: 8,
  name: 'OpenStreetMap',
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
    },
  ],
};

export type BasemapStyle = string | StyleSpecification;

/**
 * Resolve the basemap style by precedence:
 *   1) config.basemapStyleUrl (operator-provided, if non-empty)
 *   2) VITE_BASEMAP_STYLE_URL (build-time override, if set)
 *   3) OpenStreetMap raster world basemap (default; self-host in production)
 */
export function resolveBasemapStyle(config: AppConfig | undefined): BasemapStyle {
  const fromConfig = config?.basemapStyleUrl?.trim();
  if (fromConfig) return fromConfig;

  const fromEnv = import.meta.env.VITE_BASEMAP_STYLE_URL?.trim();
  if (fromEnv && !fromEnv.startsWith('<')) return fromEnv;

  return OSM_RASTER_STYLE;
}

/**
 * Human-readable credit for the basemap that `resolveBasemapStyle` would select,
 * so the on-map attribution always matches what is actually rendered.
 */
export function basemapAttribution(config: AppConfig | undefined): string {
  if (config?.basemapStyleUrl?.trim()) return 'Operator basemap';

  const fromEnv = import.meta.env.VITE_BASEMAP_STYLE_URL?.trim();
  if (fromEnv && !fromEnv.startsWith('<')) return 'Operator basemap';

  return '© OpenStreetMap contributors';
}
