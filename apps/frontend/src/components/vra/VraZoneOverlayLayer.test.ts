import { describe, expect, it, vi } from 'vitest';
import {
  VRA_ZONE_FILL_LAYER_ID,
  VRA_ZONE_OUTLINE_LAYER_ID,
  VRA_ZONE_SOURCE_ID,
  buildVraZoneFeatureCollection,
  removeVraZoneLayer,
  upsertVraZoneLayer,
} from '@/components/vra/VraZoneOverlayLayer';
import type { ZoningMap } from '@/types/api';

const zoningMap: ZoningMap = {
  plotId: 'plot-1',
  mapId: 'map-1',
  provider: 'provider',
  status: 'ready',
  mapType: 'vegetation',
  indexType: 'NDVI',
  zoneCount: 1,
  minZoneAreaHa: 0.25,
  metadata: { source: 'provider-adapter' },
  zones: [
    {
      zoneId: 'zone-1',
      color: '#22c55e',
      areaHa: 1,
      areaPercent: 50,
      clusterValue: 0.6,
      geometry: {
        type: 'Polygon',
        coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12]]],
      },
    },
  ],
};

function makeMap() {
  const sources = new Map<string, unknown>();
  const layers = new Set<string>();
  const source = { setData: vi.fn() };
  return {
    addLayer: vi.fn((layer: { id: string }) => layers.add(layer.id)),
    addSource: vi.fn((id: string) => sources.set(id, source)),
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    getSource: vi.fn((id: string) => sources.get(id)),
    moveLayer: vi.fn(),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    source,
  };
}

describe('VraZoneOverlayLayer helpers', () => {
  it('builds zone feature collections without provider identifiers', () => {
    const collection = buildVraZoneFeatureCollection(zoningMap);

    expect(collection.features[0].properties).toEqual({
      zoneId: 'zone-1',
      color: '#22c55e',
      areaHa: 1,
      areaPercent: 50,
      clusterValue: 0.6,
    });
    expect(JSON.stringify(collection)).not.toContain('external');
  });

  it('adds, updates, and removes namespaced VRA zone layers', () => {
    const map = makeMap();

    upsertVraZoneLayer(map as never, zoningMap);
    expect(map.addSource).toHaveBeenCalledWith(VRA_ZONE_SOURCE_ID, expect.anything());
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: VRA_ZONE_FILL_LAYER_ID }));
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: VRA_ZONE_OUTLINE_LAYER_ID }));

    upsertVraZoneLayer(map as never, zoningMap);
    expect(map.source.setData).toHaveBeenCalled();

    removeVraZoneLayer(map as never);
    expect(map.removeLayer).toHaveBeenCalledWith(VRA_ZONE_OUTLINE_LAYER_ID);
    expect(map.removeLayer).toHaveBeenCalledWith(VRA_ZONE_FILL_LAYER_ID);
    expect(map.removeSource).toHaveBeenCalledWith(VRA_ZONE_SOURCE_ID);
  });
});
