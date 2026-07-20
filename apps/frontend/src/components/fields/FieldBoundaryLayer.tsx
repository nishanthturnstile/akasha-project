import { useEffect } from 'react';
import type maplibregl from 'maplibre-gl';
import type { Plot, PlotGeometry } from '@/types/api';
import {
  ensureFieldBoundaryOrder,
  removeFieldBoundaryLayer,
  upsertFieldBoundaryLayer,
} from '@/components/fields/fieldBoundaryLayerHelpers';

function safelyRemoveFieldBoundaryLayer(map: maplibregl.Map, prefix = ''): void {
  try {
    removeFieldBoundaryLayer(map, prefix);
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
  layerPrefix?: string;
  /**
   * Keep re-asserting this layer to the very top of the style on every
   * styledata/idle event. Defaults to true (existing behavior) for a single
   * draft/selected/edited field. Set to false for passive background
   * reference layers (e.g. rendering many other fields alongside an actively
   * drawn/edited one) -- multiple instances all fighting to stay on top would
   * otherwise perpetually bury whichever field is actively being edited,
   * hiding its fill/outline under the background layers.
   */
  keepOnTop?: boolean;
}

export function FieldBoundaryLayer({
  featureId = 'draft-field',
  geometry,
  map,
  name = 'Draft field',
  plot,
  layerPrefix = '',
  keepOnTop = true,
}: FieldBoundaryLayerProps) {
  useEffect(() => {
    if (!map) return undefined;
    return () => safelyRemoveFieldBoundaryLayer(map, layerPrefix);
  }, [map, layerPrefix]);

  useEffect(() => {
    if (!map) return undefined;

    if (!plot && !geometry) {
      removeFieldBoundaryLayer(map, layerPrefix);
      return undefined;
    }

    upsertFieldBoundaryLayer(map, plot, geometry, featureId, name, layerPrefix);

    if (!keepOnTop) return undefined;

    const keepBoundaryOnTop = () => ensureFieldBoundaryOrder(map, layerPrefix);
    map.on('styledata', keepBoundaryOnTop);
    map.on('idle', keepBoundaryOnTop);

    return () => {
      map.off('styledata', keepBoundaryOnTop);
      map.off('idle', keepBoundaryOnTop);
    };
  }, [featureId, geometry, map, name, plot, layerPrefix, keepOnTop]);

  return null;
}
