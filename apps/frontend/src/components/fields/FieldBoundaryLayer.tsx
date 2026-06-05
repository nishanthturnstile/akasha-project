import { useEffect } from 'react';
import type maplibregl from 'maplibre-gl';
import type { Plot } from '@/types/api';

export const FIELD_BOUNDARY_SOURCE_ID = 'akasha-field-boundary-source';
export const FIELD_BOUNDARY_FILL_LAYER_ID = 'akasha-field-boundary-fill-layer';
export const FIELD_BOUNDARY_OUTLINE_LAYER_ID = 'akasha-field-boundary-outline-layer';

type FieldBoundaryGeometry = GeoJSON.Polygon | GeoJSON.MultiPolygon;

interface FieldBoundaryProperties {
  name: string;
  plotId: string;
}

export type FieldBoundaryFeatureCollection = GeoJSON.FeatureCollection<
  FieldBoundaryGeometry,
  FieldBoundaryProperties
>;

const FIELD_BOUNDARY_FILL_LAYER: maplibregl.LayerSpecification = {
  id: FIELD_BOUNDARY_FILL_LAYER_ID,
  type: 'fill',
  source: FIELD_BOUNDARY_SOURCE_ID,
  paint: {
    'fill-color': '#f8fafc',
    'fill-opacity': 0.16,
  },
};

const FIELD_BOUNDARY_OUTLINE_LAYER: maplibregl.LayerSpecification = {
  id: FIELD_BOUNDARY_OUTLINE_LAYER_ID,
  type: 'line',
  source: FIELD_BOUNDARY_SOURCE_ID,
  paint: {
    'line-color': '#ffffff',
    'line-opacity': 0.96,
    'line-width': 4.5,
    'line-blur': 0.35,
  },
};

export function buildFieldBoundaryFeatureCollection(
  plot: Plot,
): FieldBoundaryFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: plot.id,
        properties: {
          name: plot.name,
          plotId: plot.id,
        },
        geometry: plot.geometry as FieldBoundaryGeometry,
      },
    ],
  };
}

function getFieldBoundarySource(map: maplibregl.Map): maplibregl.GeoJSONSource | null {
  const source = map.getSource(FIELD_BOUNDARY_SOURCE_ID);
  if (!source || !('setData' in source)) return null;
  return source as maplibregl.GeoJSONSource;
}

export function ensureFieldBoundaryOrder(map: maplibregl.Map): void {
  if (!map.getLayer(FIELD_BOUNDARY_FILL_LAYER_ID) || !map.getLayer(FIELD_BOUNDARY_OUTLINE_LAYER_ID)) {
    return;
  }

  const layers = map.getStyle().layers ?? [];
  const topLayerIds = layers.slice(-2).map((layer) => layer.id);
  if (
    topLayerIds[0] === FIELD_BOUNDARY_FILL_LAYER_ID &&
    topLayerIds[1] === FIELD_BOUNDARY_OUTLINE_LAYER_ID
  ) {
    return;
  }

  map.moveLayer(FIELD_BOUNDARY_FILL_LAYER_ID);
  map.moveLayer(FIELD_BOUNDARY_OUTLINE_LAYER_ID);
}

export function upsertFieldBoundaryLayer(map: maplibregl.Map, plot: Plot): void {
  const data = buildFieldBoundaryFeatureCollection(plot);
  const source = getFieldBoundarySource(map);

  if (source) {
    source.setData(data);
  } else {
    map.addSource(FIELD_BOUNDARY_SOURCE_ID, {
      type: 'geojson',
      data,
    });
  }

  if (!map.getLayer(FIELD_BOUNDARY_FILL_LAYER_ID)) {
    map.addLayer(FIELD_BOUNDARY_FILL_LAYER);
  }
  if (!map.getLayer(FIELD_BOUNDARY_OUTLINE_LAYER_ID)) {
    map.addLayer(FIELD_BOUNDARY_OUTLINE_LAYER);
  }

  ensureFieldBoundaryOrder(map);
}

export function removeFieldBoundaryLayer(map: maplibregl.Map): void {
  if (map.getLayer(FIELD_BOUNDARY_OUTLINE_LAYER_ID)) {
    map.removeLayer(FIELD_BOUNDARY_OUTLINE_LAYER_ID);
  }
  if (map.getLayer(FIELD_BOUNDARY_FILL_LAYER_ID)) {
    map.removeLayer(FIELD_BOUNDARY_FILL_LAYER_ID);
  }
  if (map.getSource(FIELD_BOUNDARY_SOURCE_ID)) {
    map.removeSource(FIELD_BOUNDARY_SOURCE_ID);
  }
}

function safelyRemoveFieldBoundaryLayer(map: maplibregl.Map): void {
  try {
    removeFieldBoundaryLayer(map);
  } catch {
    // MapLibre may already be disposed during page teardown.
  }
}

export interface FieldBoundaryLayerProps {
  map: maplibregl.Map | null;
  plot: Plot | null;
}

export function FieldBoundaryLayer({ map, plot }: FieldBoundaryLayerProps) {
  useEffect(() => {
    if (!map) return undefined;
    return () => safelyRemoveFieldBoundaryLayer(map);
  }, [map]);

  useEffect(() => {
    if (!map) return undefined;

    if (!plot) {
      removeFieldBoundaryLayer(map);
      return undefined;
    }

    upsertFieldBoundaryLayer(map, plot);

    const keepBoundaryOnTop = () => ensureFieldBoundaryOrder(map);
    map.on('styledata', keepBoundaryOnTop);
    map.on('idle', keepBoundaryOnTop);

    return () => {
      map.off('styledata', keepBoundaryOnTop);
      map.off('idle', keepBoundaryOnTop);
    };
  }, [map, plot]);

  return null;
}
