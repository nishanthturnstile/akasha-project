import { useEffect } from 'react';
import type maplibregl from 'maplibre-gl';
import type { ZoningMap, ZoningZone } from '@/types/api';

export const VRA_ZONE_SOURCE_ID = 'akasha-vra-zone-source';
export const VRA_ZONE_FILL_LAYER_ID = 'akasha-vra-zone-fill-layer';
export const VRA_ZONE_OUTLINE_LAYER_ID = 'akasha-vra-zone-outline-layer';

type ZoneGeometry = GeoJSON.Polygon | GeoJSON.MultiPolygon;

interface VraZoneProperties {
  zoneId: string;
  color: string;
  areaHa?: number | null;
  areaPercent?: number | null;
  clusterValue?: number | null;
}

export type VraZoneFeatureCollection = GeoJSON.FeatureCollection<
  ZoneGeometry,
  VraZoneProperties
>;

export function buildVraZoneFeatureCollection(zoningMap: ZoningMap): VraZoneFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: zoningMap.zones
      .filter((zone): zone is ZoningZone & { geometry: ZoneGeometry } => Boolean(zone.geometry))
      .map((zone) => ({
        type: 'Feature',
        id: zone.zoneId,
        properties: {
          zoneId: zone.zoneId,
          color: zone.color,
          areaHa: zone.areaHa,
          areaPercent: zone.areaPercent,
          clusterValue: zone.clusterValue,
        },
        geometry: zone.geometry,
      })),
  };
}

function getZoneSource(map: maplibregl.Map): maplibregl.GeoJSONSource | null {
  const source = map.getSource(VRA_ZONE_SOURCE_ID);
  if (!source || !('setData' in source)) return null;
  return source as maplibregl.GeoJSONSource;
}

export function ensureVraZoneOrder(map: maplibregl.Map): void {
  if (!map.getLayer(VRA_ZONE_FILL_LAYER_ID) || !map.getLayer(VRA_ZONE_OUTLINE_LAYER_ID)) {
    return;
  }
  map.moveLayer(VRA_ZONE_FILL_LAYER_ID);
  map.moveLayer(VRA_ZONE_OUTLINE_LAYER_ID);
}

export function upsertVraZoneLayer(map: maplibregl.Map, zoningMap: ZoningMap): void {
  const data = buildVraZoneFeatureCollection(zoningMap);
  const source = getZoneSource(map);
  if (source) {
    source.setData(data);
  } else {
    map.addSource(VRA_ZONE_SOURCE_ID, { type: 'geojson', data });
  }
  if (!map.getLayer(VRA_ZONE_FILL_LAYER_ID)) {
    map.addLayer({
      id: VRA_ZONE_FILL_LAYER_ID,
      type: 'fill',
      source: VRA_ZONE_SOURCE_ID,
      paint: {
        'fill-color': ['coalesce', ['get', 'color'], '#22c55e'],
        'fill-opacity': 0.36,
      },
    });
  }
  if (!map.getLayer(VRA_ZONE_OUTLINE_LAYER_ID)) {
    map.addLayer({
      id: VRA_ZONE_OUTLINE_LAYER_ID,
      type: 'line',
      source: VRA_ZONE_SOURCE_ID,
      paint: {
        'line-color': '#f8fafc',
        'line-opacity': 0.96,
        'line-width': 2,
      },
    });
  }
  ensureVraZoneOrder(map);
}

export function removeVraZoneLayer(map: maplibregl.Map): void {
  if (map.getLayer(VRA_ZONE_OUTLINE_LAYER_ID)) map.removeLayer(VRA_ZONE_OUTLINE_LAYER_ID);
  if (map.getLayer(VRA_ZONE_FILL_LAYER_ID)) map.removeLayer(VRA_ZONE_FILL_LAYER_ID);
  if (map.getSource(VRA_ZONE_SOURCE_ID)) map.removeSource(VRA_ZONE_SOURCE_ID);
}

export interface VraZoneOverlayLayerProps {
  map: maplibregl.Map | null;
  zoningMap: ZoningMap | null;
}

export function VraZoneOverlayLayer({ map, zoningMap }: VraZoneOverlayLayerProps) {
  useEffect(() => {
    if (!map) return undefined;
    return () => {
      try {
        removeVraZoneLayer(map);
      } catch {
        // MapLibre may already be disposed during route teardown.
      }
    };
  }, [map]);

  useEffect(() => {
    if (!map) return undefined;
    if (!zoningMap) {
      removeVraZoneLayer(map);
      return undefined;
    }
    upsertVraZoneLayer(map, zoningMap);
    return undefined;
  }, [map, zoningMap]);

  return null;
}
