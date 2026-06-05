import { describe, expect, it, vi } from 'vitest';
import {
  applyCompareLayer,
  applySatelliteLayer,
  isValidSceneBounds,
  removeCompareLayer,
  resolveTileUrl,
  SAT_LAYER_ID,
  SAT_LAYER_ID_B,
  SAT_SOURCE_ID,
  SAT_SOURCE_ID_B,
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

  it('allows an already-absolute same-origin /api/tiles URL', () => {
    expect(
      resolveTileUrl('http://localhost/api/tiles/s/d/rgb/{z}/{x}/{y}.png', 'http://localhost'),
    ).toBe('http://localhost/api/tiles/s/d/rgb/{z}/{x}/{y}.png');
  });

  it('allows field-scoped same-origin tile templates', () => {
    expect(
      resolveTileUrl(
        '/api/tiles/fields/plot-1/scene-token/NDVI/{z}/{x}/{y}.png?clouds=true',
        'http://localhost',
      ),
    ).toBe(
      'http://localhost/api/tiles/fields/plot-1/scene-token/NDVI/{z}/{x}/{y}.png?clouds=true',
    );
  });

  it('rejects external absolute tile URLs', () => {
    expect(() => resolveTileUrl('https://tiles.example.com/y/{z}.png', 'http://localhost')).toThrow(
      /same-origin/,
    );
  });

  it('rejects same-origin paths outside the /api/tiles contract', () => {
    expect(() => resolveTileUrl('/tiles/s/d/{z}.png', 'http://localhost')).toThrow(
      /\/api\/tiles/,
    );
  });
});

describe('applySatelliteLayer (date change touches only the raster layer)', () => {
  it('validates scene bounds before using them in a raster source', () => {
    expect(isValidSceneBounds([77.7, 11.6, 78.8, 12.7])).toBe(true);
    expect(isValidSceneBounds([78.8, 11.6, 77.7, 12.7])).toBe(false);
    expect(isValidSceneBounds([77.7, 12.7, 78.8, 11.6])).toBe(false);
    expect(isValidSceneBounds(undefined)).toBe(false);
  });

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

  it('passes valid scene bounds to MapLibre so out-of-footprint tiles are not requested', () => {
    const map = createMockMap();
    const bounds: [number, number, number, number] = [77.751, 11.647, 78.771, 12.65];
    applySatelliteLayer(
      map as unknown as MapLayerHost,
      { tileUrlTemplate: '/api/tiles/a/2025-09-14/rgb/{z}/{x}/{y}.png', bounds },
      { opacity: 1, visible: true },
      'http://localhost',
    );

    expect(map.addSource).toHaveBeenCalledWith(
      SAT_SOURCE_ID,
      expect.objectContaining({ bounds }),
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

describe('applyCompareLayer / removeCompareLayer (opacity-blend compare mode)', () => {
  it('adds the B layer beneath A and never calls setStyle', () => {
    const map = createMockMap();
    const host = map as unknown as MapLayerHost;
    applySatelliteLayer(
      host,
      { tileUrlTemplate: '/api/tiles/a/2025-09-14/rgb/{z}/{x}/{y}.png' },
      { opacity: 0.5, visible: true },
      'http://localhost',
    );
    map.addLayer.mockClear();

    applyCompareLayer(
      host,
      { tileUrlTemplate: '/api/tiles/a/2025-08-30/rgb/{z}/{x}/{y}.png' },
      'http://localhost',
    );

    expect(map.addSource).toHaveBeenCalledWith(
      SAT_SOURCE_ID_B,
      expect.objectContaining({ type: 'raster' }),
    );
    // B is inserted before (beneath) the A layer.
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ id: SAT_LAYER_ID_B, type: 'raster' }),
      SAT_LAYER_ID,
    );
    expect(map.setStyle).not.toHaveBeenCalled();
  });

  it('removes the B source+layer when compare is turned off', () => {
    const map = createMockMap();
    const host = map as unknown as MapLayerHost;
    applyCompareLayer(
      host,
      { tileUrlTemplate: '/api/tiles/a/2025-08-30/rgb/{z}/{x}/{y}.png' },
      'http://localhost',
    );
    removeCompareLayer(host);

    expect(map.removeLayer).toHaveBeenCalledWith(SAT_LAYER_ID_B);
    expect(map.removeSource).toHaveBeenCalledWith(SAT_SOURCE_ID_B);
  });
});
