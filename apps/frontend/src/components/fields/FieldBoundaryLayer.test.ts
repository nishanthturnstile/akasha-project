import { describe, expect, it, vi } from 'vitest';
import {
  FIELD_BOUNDARY_FILL_LAYER_ID,
  FIELD_BOUNDARY_OUTLINE_LAYER_ID,
  FIELD_BOUNDARY_SOURCE_ID,
  buildFieldBoundaryFeatureCollection,
  removeFieldBoundaryLayer,
  upsertFieldBoundaryLayer,
} from '@/components/fields/FieldBoundaryLayer';
import type { Plot } from '@/types/api';

const plot: Plot = {
  id: 'plot-1',
  name: 'North field',
  geometry: {
    type: 'Polygon',
    coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12.01], [77, 12]]],
  },
  areaHa: 1,
  createdAt: null,
  updatedAt: null,
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
    getStyle: vi.fn(() => ({ layers: Array.from(layers).map((id) => ({ id })) })),
    moveLayer: vi.fn(),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    source,
  };
}

describe('FieldBoundaryLayer helpers', () => {
  it('builds a selected-field feature collection', () => {
    expect(buildFieldBoundaryFeatureCollection(plot)).toEqual({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          id: 'plot-1',
          properties: { name: 'North field', plotId: 'plot-1' },
          geometry: plot.geometry,
        },
      ],
    });
  });

  it('adds, updates, and removes namespaced field layers', () => {
    const map = makeMap();

    upsertFieldBoundaryLayer(map as never, plot);
    expect(map.addSource).toHaveBeenCalledWith(FIELD_BOUNDARY_SOURCE_ID, expect.anything());
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: FIELD_BOUNDARY_FILL_LAYER_ID }));
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: FIELD_BOUNDARY_OUTLINE_LAYER_ID }));

    upsertFieldBoundaryLayer(map as never, plot);
    expect(map.source.setData).toHaveBeenCalled();

    removeFieldBoundaryLayer(map as never);
    expect(map.removeLayer).toHaveBeenCalledWith(FIELD_BOUNDARY_OUTLINE_LAYER_ID);
    expect(map.removeLayer).toHaveBeenCalledWith(FIELD_BOUNDARY_FILL_LAYER_ID);
    expect(map.removeSource).toHaveBeenCalledWith(FIELD_BOUNDARY_SOURCE_ID);
  });
});
