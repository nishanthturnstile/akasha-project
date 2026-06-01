import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import type { BasemapStyle } from '@/map/basemap';
import {
  applySatelliteLayer,
  isValidSceneBounds,
  setSatelliteOpacity,
  setSatelliteVisibility,
  SAT_LAYER_ID,
  SAT_SOURCE_ID,
  type MapLayerHost,
  type SatelliteScene,
} from '@/lib/satelliteLayer';

/** MapLibre's Map satisfies the narrow MapLayerHost structural surface at runtime. */
const asHost = (m: maplibregl.Map): MapLayerHost => m as unknown as MapLayerHost;

const MIN_SCENE_FIT_GUTTER = 48;

function sceneFitPadding(map: maplibregl.Map) {
  const canvas = map.getCanvas();
  const width = canvas.clientWidth || canvas.width || 800;
  const height = canvas.clientHeight || canvas.height || 600;

  const horizontalBudget = Math.max(0, width - MIN_SCENE_FIT_GUTTER);
  const left = Math.min(320, Math.floor(width * 0.28), Math.floor(horizontalBudget * 0.62));
  const right = Math.min(
    220,
    Math.floor(width * 0.16),
    Math.max(0, horizontalBudget - left),
  );

  const verticalBudget = Math.max(0, height - MIN_SCENE_FIT_GUTTER);
  const top = Math.min(96, Math.floor(height * 0.14), Math.floor(verticalBudget * 0.55));
  const bottom = Math.min(80, Math.floor(height * 0.12), Math.max(0, verticalBudget - top));

  return { top, bottom, left, right };
}

function sceneLayerKey(scene: SatelliteScene | null): string | null {
  if (!scene) return null;
  return [
    scene.tileUrlTemplate,
    scene.bounds?.join(',') ?? '',
    scene.minzoom ?? '',
    scene.maxzoom ?? '',
  ].join('|');
}

function viewportIntersectsScene(map: maplibregl.Map, scene: SatelliteScene): boolean {
  if (!isValidSceneBounds(scene.bounds)) return true;
  const [west, south, east, north] = scene.bounds;
  const viewport = map.getBounds();
  return (
    west <= viewport.getEast() &&
    east >= viewport.getWest() &&
    south <= viewport.getNorth() &&
    north >= viewport.getSouth()
  );
}

function fitSceneBoundsIfNeeded(map: maplibregl.Map, scene: SatelliteScene): void {
  if (!isValidSceneBounds(scene.bounds) || viewportIntersectsScene(map, scene)) return;
  const [west, south, east, north] = scene.bounds;
  map.fitBounds(
    [
      [west, south],
      [east, north],
    ],
    {
      padding: sceneFitPadding(map),
      maxZoom: Math.min(scene.maxzoom ?? 14, 14),
      duration: 650,
    },
  );
}

interface MapLayerManagerProps {
  basemapStyle: BasemapStyle;
  center: [number, number];
  zoom: number;
  scene: SatelliteScene | null;
  /** 0..1 */
  opacity: number;
  visible: boolean;
  onMapReady?: (map: maplibregl.Map) => void;
}

/**
 * Owns the MapLibre instance for its full lifecycle. The basemap style is set once
 * on creation; subsequent acquisition-date changes only swap the raster source/layer
 * (see lib/satelliteLayer). If the active satellite footprint is completely off
 * screen, the camera is gently fitted to it so toggling the layer reveals imagery.
 */
export function MapLayerManager({
  basemapStyle,
  center,
  zoom,
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
  const sceneKey = sceneLayerKey(scene);

  // Create the map exactly once.
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: basemapStyle as maplibregl.StyleSpecification,
      center,
      zoom,
      attributionControl: false,
      pitchWithRotate: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 96 }), 'bottom-left');

    map.on('load', () => {
      loadedRef.current = true;
      const s = sceneRef.current;
      if (s) {
        applySatelliteLayer(asHost(map), s, stateRef.current);
        if (stateRef.current.visible) fitSceneBoundsIfNeeded(map, s);
      }
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
      if (visible) fitSceneBoundsIfNeeded(map, scene);
    } else {
      if (map.getLayer(SAT_LAYER_ID)) map.removeLayer(SAT_LAYER_ID);
      if (map.getSource(SAT_SOURCE_ID)) map.removeSource(SAT_SOURCE_ID);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneKey]);

  // Live opacity (no layer rebuild).
  useEffect(() => {
    const map = mapRef.current;
    if (map && loadedRef.current) setSatelliteOpacity(asHost(map), visible ? opacity : 0);
  }, [opacity, visible]);

  // Visibility toggle (independent of basemap).
  useEffect(() => {
    const map = mapRef.current;
    if (map && loadedRef.current) {
      setSatelliteVisibility(asHost(map), visible, opacity);
      if (visible && sceneRef.current) fitSceneBoundsIfNeeded(map, sceneRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  return <div ref={ containerRef } className="absolute inset-0" data-testid="map-canvas" />;
}
