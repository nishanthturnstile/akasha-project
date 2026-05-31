import { describe, expect, it, vi } from 'vitest';
import {
  applySatelliteLayer,
  resolveTileUrl,
  SAT_LAYER_ID,
  SAT_SOURCE_ID,
  type MapLayerHost,
} from '@/lib/satelliteLayer';

function createMockMap() {
  const sources = new Map<string, unknown>();
  const layers = new Map<string, unknown>();
  return {
    // setStyle is intentionally present so we can assert it is NEVER called.
    setStyle: vi.fn(),
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, src: Record<string, unknown>) => {
      sources.set(id, src);
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    getLayer: vi.fn((id: string) => layers.get(id)),
    addLayer: vi.fn((layer: Record<string, unknown>) => {
      layers.set(layer.id as string, layer);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    setPaintProperty: vi.fn(),
    setLayoutProperty: vi.fn(),
  };
}

describe('resolveTileUrl', () => {
  it('prepends the same-origin to a relative template', () => {
    expect(
      resolveTileUrl('/api/tiles/s/d/rgb/{z}/{x}/{y}.png', 'http://localhost'),
    ).toBe('http://localhost/api/tiles/s/d/rgb/{z}/{x}/{y}.png');
  });

  it('leaves an already-absolute URL unchanged', () => {
    expect(resolveTileUrl('https://x/y/{z}.png', 'http://localhost')).toBe('https://x/y/{z}.png');
  });
});

describe('applySatelliteLayer (date change touches only the raster layer)', () => {
  it('adds the raster source+layer and never calls setStyle', () => {
    const map = createMockMap();
    applySatelliteLayer(
      map as unknown as MapLayerHost,
      { tileUrlTemplate: '/api/tiles/a/2025-09-14/rgb/{z}/{x}/{y}.png' },
      { opacity: 1, visible: true },
      'http://localhost',
    );
    expect(map.setStyle).not.toHaveBeenCalled();
    expect(map.addSource).toHaveBeenCalledWith(
      SAT_SOURCE_ID,
      expect.objectContaining({ type: 'raster' }),
    );
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ id: SAT_LAYER_ID, type: 'raster' }),
    );
  });

  it('swaps the raster layer on date change without disturbing the basemap', () => {
    const map = createMockMap();
    const host = map as unknown as MapLayerHost;
    applySatelliteLayer(
      host,
      { tileUrlTemplate: '/api/tiles/a/2025-09-14/rgb/{z}/{x}/{y}.png' },
      { opacity: 1, visible: true },
      'http://localhost',
    );
    map.addSource.mockClear();
    map.addLayer.mockClear();

    applySatelliteLayer(
      host,
      { tileUrlTemplate: '/api/tiles/a/2025-08-30/rgb/{z}/{x}/{y}.png' },
      { opacity: 1, visible: true },
      'http://localhost',
    );

    expect(map.removeLayer).toHaveBeenCalledWith(SAT_LAYER_ID);
    expect(map.removeSource).toHaveBeenCalledWith(SAT_SOURCE_ID);
    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addLayer).toHaveBeenCalledTimes(1);
    // The basemap style is never replaced when changing dates.
    expect(map.setStyle).not.toHaveBeenCalled();
  });
});
