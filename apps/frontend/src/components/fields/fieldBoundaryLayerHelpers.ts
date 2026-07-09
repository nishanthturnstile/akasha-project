import type maplibregl from 'maplibre-gl';
import type { Plot, PlotGeometry } from '@/types/api';

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

function srcId(prefix: string): string {
  return prefix ? `${prefix}${FIELD_BOUNDARY_SOURCE_ID}` : FIELD_BOUNDARY_SOURCE_ID;
}
function fillId(prefix: string): string {
  return prefix ? `${prefix}${FIELD_BOUNDARY_FILL_LAYER_ID}` : FIELD_BOUNDARY_FILL_LAYER_ID;
}
function outlineId(prefix: string): string {
  return prefix ? `${prefix}${FIELD_BOUNDARY_OUTLINE_LAYER_ID}` : FIELD_BOUNDARY_OUTLINE_LAYER_ID;
}

function makeFillLayer(prefix: string): maplibregl.LayerSpecification {
  return {
    id: fillId(prefix),
    type: 'fill',
    source: srcId(prefix),
    paint: {
      'fill-color': '#3b82f6',
      'fill-opacity': 0.22,
    },
  };
}

function makeOutlineLayer(prefix: string): maplibregl.LayerSpecification {
  return {
    id: outlineId(prefix),
    type: 'line',
    source: srcId(prefix),
    paint: {
      'line-color': '#1d4ed8',
      'line-opacity': 0.96,
      'line-width': 4.5,
      'line-blur': 0.35,
    },
  };
}

export function buildFieldBoundaryFeatureCollectionFromGeometry(
  geometry: FieldBoundaryGeometry,
  featureId: string,
  name: string,
): FieldBoundaryFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: featureId,
        properties: {
          name,
          plotId: featureId,
        },
        geometry: geometry as FieldBoundaryGeometry,
      },
    ],
  };
}

export function buildFieldBoundaryFeatureCollection(plot: Plot): FieldBoundaryFeatureCollection {
  return buildFieldBoundaryFeatureCollectionFromGeometry(
    plot.geometry as FieldBoundaryGeometry,
    plot.id,
    plot.name,
  );
}

function getFieldBoundarySource(map: maplibregl.Map, prefix = ''): maplibregl.GeoJSONSource | null {
  const id = srcId(prefix);
  const source = map.getSource(id);
  if (!source || !('setData' in source)) return null;
  return source as maplibregl.GeoJSONSource;
}

export function ensureFieldBoundaryOrder(map: maplibregl.Map, prefix = ''): void {
  const fill = fillId(prefix);
  const outline = outlineId(prefix);
  if (!map.getLayer(fill) || !map.getLayer(outline)) {
    return;
  }

  const layers = map.getStyle().layers ?? [];
  const topLayerIds = layers.slice(-2).map((layer) => layer.id);
  if (
    topLayerIds[0] === fill &&
    topLayerIds[1] === outline
  ) {
    return;
  }

  map.moveLayer(fill);
  map.moveLayer(outline);
}

export function upsertFieldBoundaryLayer(
  map: maplibregl.Map,
  plot: Plot | null,
  geometry?: PlotGeometry | null,
  featureId = 'draft-field',
  name = 'Draft field',
  prefix = '',
): void {
  const activeGeometry = (geometry ?? plot?.geometry) as FieldBoundaryGeometry | undefined;
  if (!activeGeometry) return;

  const isDraft = Boolean(geometry);
  const data = buildFieldBoundaryFeatureCollectionFromGeometry(
    activeGeometry,
    isDraft ? featureId : (plot?.id ?? 'field-boundary'),
    isDraft ? name : (plot?.name ?? 'Field'),
  );
  const source = getFieldBoundarySource(map, prefix);

  if (source) {
    source.setData(data);
  } else {
    map.addSource(srcId(prefix), {
      type: 'geojson',
      data,
    });
  }

  const fill = fillId(prefix);
  const outline = outlineId(prefix);

  if (!map.getLayer(fill)) {
    map.addLayer(makeFillLayer(prefix));
  }
  if (!map.getLayer(outline)) {
    map.addLayer(makeOutlineLayer(prefix));
  }

  ensureFieldBoundaryOrder(map, prefix);
}

export function removeFieldBoundaryLayer(map: maplibregl.Map, prefix = ''): void {
  const outline = outlineId(prefix);
  const fill = fillId(prefix);
  const source = srcId(prefix);
  if (map.getLayer(outline)) {
    map.removeLayer(outline);
  }
  if (map.getLayer(fill)) {
    map.removeLayer(fill);
  }
  if (map.getSource(source)) {
    map.removeSource(source);
  }
}