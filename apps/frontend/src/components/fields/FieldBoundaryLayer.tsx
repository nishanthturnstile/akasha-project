import { useEffect } from 'react';
import type maplibregl from 'maplibre-gl';
import type { Plot, PlotGeometry } from '@/types/api';
import {
  ensureFieldBoundaryOrder,
  removeFieldBoundaryLayer,
  upsertFieldBoundaryLayer,
} from '@/components/fields/fieldBoundaryLayerHelpers';

function safelyRemoveFieldBoundaryLayer(map: maplibregl.Map): void {
  try {
    removeFieldBoundaryLayer(map);
  } catch {
    // MapLibre may already be disposed during page teardown.
  }
}

export interface FieldBoundaryLayerProps {
  featureId?: string;
  geometry?: PlotGeometry | null;
  map: maplibregl.Map | null;
  name?: string;
  plot: Plot | null;
}

export function FieldBoundaryLayer({
  featureId = 'draft-field',
  geometry,
  map,
  name = 'Draft field',
  plot,
}: FieldBoundaryLayerProps) {
  useEffect(() => {
    if (!map) return undefined;
    return () => safelyRemoveFieldBoundaryLayer(map);
  }, [map]);

  useEffect(() => {
    if (!map) return undefined;

    if (!plot && !geometry) {
      removeFieldBoundaryLayer(map);
      return undefined;
    }

    upsertFieldBoundaryLayer(map, plot, geometry, featureId, name);

    const keepBoundaryOnTop = () => ensureFieldBoundaryOrder(map);
    map.on('styledata', keepBoundaryOnTop);
    map.on('idle', keepBoundaryOnTop);

    return () => {
      map.off('styledata', keepBoundaryOnTop);
      map.off('idle', keepBoundaryOnTop);
    };
  }, [featureId, geometry, map, name, plot]);

  return null;
}
