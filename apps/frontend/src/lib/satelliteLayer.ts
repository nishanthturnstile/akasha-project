// Pure satellite-overlay layer management for MapLibre.
//
// The single most important Phase 4 invariant: changing the acquisition date must
// ONLY swap the raster source/layer. These helpers never call `setStyle`, so the
// basemap and camera are left completely untouched.

export const SAT_SOURCE_ID = 'akasha-satellite';
export const SAT_LAYER_ID = 'akasha-satellite-layer';

export interface SatelliteScene {
  /** Same-origin `/api/tiles/.../{z}/{x}/{y}.png` template. */
  tileUrlTemplate: string;
  bounds?: [number, number, number, number];
  minzoom?: number;
  maxzoom?: number;
  attribution?: string;
}

export interface SatelliteLayerState {
  /** 0..1 */
  opacity: number;
  visible: boolean;
}

export type SceneBounds = [number, number, number, number];

/** Minimal structural surface so the swap logic is unit-testable without real MapLibre. */
export interface MapLayerHost {
  getSource(id: string): unknown;
  addSource(id: string, source: Record<string, unknown>): void;
  removeSource(id: string): void;
  getLayer(id: string): unknown;
  addLayer(layer: Record<string, unknown>, beforeId?: string): void;
  removeLayer(id: string): void;
  setPaintProperty(layerId: string, name: string, value: unknown): void;
  setLayoutProperty(layerId: string, name: string, value: unknown): void;
}

export function isValidSceneBounds(bounds?: SatelliteScene['bounds']): bounds is SceneBounds {
  if (!bounds || bounds.length !== 4) return false;
  const [west, south, east, north] = bounds;
  return [west, south, east, north].every(Number.isFinite) && west < east && south < north;
}

/** Resolve the API tile template to a same-origin absolute URL for MapLibre. */
export function resolveTileUrl(template: string, origin?: string): string {
  const base = (origin ?? (typeof window !== 'undefined' ? window.location.origin : '')).replace(
    /\/$/,
    '',
  );

  if (/^https?:\/\//i.test(template)) {
    const url = new URL(template);
    if (base && url.origin !== base) {
      throw new Error('Satellite tile template must be same-origin.');
    }
    if (!url.pathname.startsWith('/api/tiles/')) {
      throw new Error('Satellite tile template must use the /api/tiles contract.');
    }
    return template;
  }

  const path = template.startsWith('/') ? template : `/${template}`;
  if (!path.startsWith('/api/tiles/')) {
    throw new Error('Satellite tile template must use the /api/tiles contract.');
  }

  return base ? `${base}${path}` : path;
}

/**
 * Add or replace ONLY the satellite raster source+layer. Never touches the basemap.
 */
export function applySatelliteLayer(
  map: MapLayerHost,
  scene: SatelliteScene,
  state: SatelliteLayerState,
  origin?: string,
): void {
  if (map.getLayer(SAT_LAYER_ID)) map.removeLayer(SAT_LAYER_ID);
  if (map.getSource(SAT_SOURCE_ID)) map.removeSource(SAT_SOURCE_ID);

  const source: Record<string, unknown> = {
    type: 'raster',
    tiles: [resolveTileUrl(scene.tileUrlTemplate, origin)],
    tileSize: 256,
  };
  // Constrain requests to the STAC footprint. TiTiler returns 404 for tiles outside
  // the COG footprint, which MapLibre surfaces as tile errors; bounds prevent the
  // UI from asking for imagery where this scene cannot render.
  if (isValidSceneBounds(scene.bounds)) source.bounds = scene.bounds;
  if (scene.minzoom != null) source.minzoom = scene.minzoom;
  if (scene.maxzoom != null) source.maxzoom = scene.maxzoom;
  if (scene.attribution) source.attribution = scene.attribution;

  map.addSource(SAT_SOURCE_ID, source);
  map.addLayer({
    id: SAT_LAYER_ID,
    type: 'raster',
    source: SAT_SOURCE_ID,
    layout: { visibility: state.visible ? 'visible' : 'none' },
    paint: {
      'raster-opacity': state.visible ? state.opacity : 0,
      // Crossfade incoming imagery per design-system motion (§6) — basemap untouched.
      'raster-opacity-transition': { duration: 360, delay: 0 },
    },
  });
}

export function setSatelliteOpacity(map: MapLayerHost, opacity: number): void {
  if (map.getLayer(SAT_LAYER_ID)) {
    map.setPaintProperty(SAT_LAYER_ID, 'raster-opacity', opacity);
  }
}

export function setSatelliteVisibility(
  map: MapLayerHost,
  visible: boolean,
  opacity: number,
): void {
  if (map.getLayer(SAT_LAYER_ID)) {
    map.setLayoutProperty(SAT_LAYER_ID, 'visibility', visible ? 'visible' : 'none');
    map.setPaintProperty(SAT_LAYER_ID, 'raster-opacity', visible ? opacity : 0);
  }
}
