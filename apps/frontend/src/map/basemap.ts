import type { StyleSpecification } from 'maplibre-gl';
import type { AppConfig } from '@/types/api';

/**
 * Local "ink" fallback basemap — a plain dark background with NO external sources,
 * so the app never reaches a public CDN/OSM and the satellite overlay stays usable.
 * Colour matches the design-system dark page background (`--background` 222 38% 7%).
 */
export const INK_FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  name: 'Akasha Ink (offline fallback)',
  sources: {},
  layers: [
    {
      id: 'akasha-ink-background',
      type: 'background',
      paint: { 'background-color': '#0b1019' },
    },
  ],
};

export type BasemapStyle = string | StyleSpecification;

/**
 * Resolve the basemap style by precedence:
 *   1) config.basemapStyleUrl (operator-provided, if non-empty)
 *   2) VITE_BASEMAP_STYLE_URL (build-time override, if set)
 *   3) bundled local ink fallback style (no public CDN)
 */
export function resolveBasemapStyle(config: AppConfig | undefined): BasemapStyle {
  const fromConfig = config?.basemapStyleUrl?.trim();
  if (fromConfig) return fromConfig;

  const fromEnv = import.meta.env.VITE_BASEMAP_STYLE_URL?.trim();
  if (fromEnv && !fromEnv.startsWith('<')) return fromEnv;

  return INK_FALLBACK_STYLE;
}
