import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import type { BasemapStyle } from '@/map/basemap';
import {
  applySatelliteLayer,
  setSatelliteOpacity,
  setSatelliteVisibility,
  SAT_LAYER_ID,
  SAT_SOURCE_ID,
  type MapLayerHost,
  type SatelliteScene,
} from '@/lib/satelliteLayer';

/** MapLibre's Map satisfies the narrow MapLayerHost structural surface at runtime. */
const asHost = (m: maplibregl.Map): MapLayerHost => m as unknown as MapLayerHost;

interface MapLayerManagerProps {
  basemapStyle: BasemapStyle;
  center: [number, number];
  zoom: number;
  maxBounds?: [[number, number], [number, number]];
  scene: SatelliteScene | null;
  /** 0..1 */
  opacity: number;
  visible: boolean;
  onMapReady?: (map: maplibregl.Map) => void;
}

/**
 * Owns the MapLibre instance for its full lifecycle. The basemap style is set once
 * on creation; subsequent acquisition-date changes only swap the raster source/layer
 * (see lib/satelliteLayer) so the basemap and camera are never disturbed.
 */
export function MapLayerManager({
  basemapStyle,
  center,
  zoom,
  maxBounds,
  scene,
  opacity,
  visible,
  onMapReady,
}: MapLayerManagerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);

  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const stateRef = useRef({ opacity, visible });
  stateRef.current = { opacity, visible };

  // Create the map exactly once.
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: basemapStyle as maplibregl.StyleSpecification,
      center,
      zoom,
      maxBounds,
      attributionControl: false,
      pitchWithRotate: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 96 }), 'bottom-left');

    map.on('load', () => {
      loadedRef.current = true;
      const s = sceneRef.current;
      if (s) applySatelliteLayer(asHost(map), s, stateRef.current);
      onMapReady?.(map);
    });

    return () => {
      loadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap ONLY the satellite raster layer when the active scene changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (scene) {
      applySatelliteLayer(asHost(map), scene, { opacity, visible });
    } else {
      if (map.getLayer(SAT_LAYER_ID)) map.removeLayer(SAT_LAYER_ID);
      if (map.getSource(SAT_SOURCE_ID)) map.removeSource(SAT_SOURCE_ID);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene?.tileUrlTemplate]);

  // Live opacity (no layer rebuild).
  useEffect(() => {
    const map = mapRef.current;
    if (map && loadedRef.current) setSatelliteOpacity(asHost(map), visible ? opacity : 0);
  }, [opacity, visible]);

  // Visibility toggle (independent of basemap).
  useEffect(() => {
    const map = mapRef.current;
    if (map && loadedRef.current) setSatelliteVisibility(asHost(map), visible, opacity);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  return <div ref={containerRef} className="absolute inset-0" data-testid="map-canvas" />;
}
