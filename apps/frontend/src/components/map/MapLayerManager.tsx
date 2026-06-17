import { useEffect, useRef } from 'react';
import { BasemapStyle } from '@esri/maplibre-arcgis';
import maplibregl from 'maplibre-gl';
import type { ResolvedBasemapConfig } from '@/map/basemap';
import { getSharedEsriBasemapSession } from '@/map/esriBasemapSession';
import {
  applySatelliteLayer,
  applyCompareLayer,
  isValidSceneBounds,
  removeCompareLayer,
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
const EMPTY_MAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [],
};
const OSM_SOURCE_ID = 'osm-raster';
const OSM_BASEMAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    [OSM_SOURCE_ID]: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    {
      id: 'osm-raster-layer',
      type: 'raster',
      source: OSM_SOURCE_ID,
    },
  ],
};

const INDEX_OVERLAY_SOURCE_ID = 'akasha-index-overlay';
const INDEX_OVERLAY_LAYER_ID = 'akasha-index-overlay-layer';

/** EOS-style field-clipped index image: a colorized PNG (transparent outside the
 *  polygon) georeferenced to the field's lng/lat bbox corners. */
export interface IndexOverlay {
  url: string;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
}

function removeIndexOverlay(map: maplibregl.Map): void {
  if (map.getLayer(INDEX_OVERLAY_LAYER_ID)) map.removeLayer(INDEX_OVERLAY_LAYER_ID);
  if (map.getSource(INDEX_OVERLAY_SOURCE_ID)) map.removeSource(INDEX_OVERLAY_SOURCE_ID);
}

/** Add or update the field-clipped index image on top of the base imagery. */
function applyIndexOverlay(map: maplibregl.Map, overlay: IndexOverlay | null): void {
  if (!overlay) {
    removeIndexOverlay(map);
    return;
  }
  const existing = map.getSource(INDEX_OVERLAY_SOURCE_ID) as maplibregl.ImageSource | undefined;
  if (existing) {
    existing.updateImage({ url: overlay.url, coordinates: overlay.coordinates });
    return;
  }
  map.addSource(INDEX_OVERLAY_SOURCE_ID, {
    type: 'image',
    url: overlay.url,
    coordinates: overlay.coordinates,
  });
  map.addLayer({
    id: INDEX_OVERLAY_LAYER_ID,
    type: 'raster',
    source: INDEX_OVERLAY_SOURCE_ID,
    paint: { 'raster-opacity': 1, 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
  });
}

function setIndexOverlayOpacity(map: maplibregl.Map, opacity: number): void {
  if (map.getLayer(INDEX_OVERLAY_LAYER_ID)) {
    map.setPaintProperty(INDEX_OVERLAY_LAYER_ID, 'raster-opacity', opacity);
  }
}

function overlayKeyOf(overlay: IndexOverlay | null | undefined): string | null {
  return overlay ? `${overlay.url}|${overlay.coordinates.flat().join(',')}` : null;
}

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
  // Reserve room for the bottom timeline filmstrip (~110px tall).
  const bottom = Math.min(140, Math.floor(height * 0.2), Math.max(0, verticalBudget - top));

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
  basemap: ResolvedBasemapConfig;
  center: [number, number];
  zoom: number;
  scene: SatelliteScene | null;
  /** Compare ("B") scene rendered beneath `scene`; `null` disables compare. */
  sceneB?: SatelliteScene | null;
  /** EOS-style field-clipped index image painted over the base imagery; `null` off. */
  indexOverlay?: IndexOverlay | null;
  /** 0..1 */
  opacity: number;
  visible: boolean;
  onBasemapError?: (error: Error) => void;
  onMapReady?: (map: maplibregl.Map) => void;
}

/**
 * Owns the MapLibre instance for its full lifecycle. The Esri basemap session/style
 * is applied once; subsequent acquisition-date changes only swap the Akasha raster
 * source/layer (see lib/satelliteLayer). If the active satellite footprint is
 * completely off screen, the camera is gently fitted to it so toggling the layer
 * reveals imagery.
 */
export function MapLayerManager({
  basemap,
  center,
  zoom,
  scene,
  sceneB,
  indexOverlay,
  opacity,
  visible,
  onBasemapError,
  onMapReady,
}: MapLayerManagerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);

  const sceneRef = useRef(scene);
  sceneRef.current = scene;
  const sceneBRef = useRef(sceneB ?? null);
  sceneBRef.current = sceneB ?? null;
  const overlayRef = useRef(indexOverlay ?? null);
  overlayRef.current = indexOverlay ?? null;
  const stateRef = useRef({ opacity, visible });
  stateRef.current = { opacity, visible };
  const sceneKey = sceneLayerKey(scene);
  const sceneKeyB = sceneLayerKey(sceneB ?? null);
  const overlayKey = overlayKeyOf(indexOverlay);

  // Create the map exactly once.
  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: EMPTY_MAP_STYLE,
      center,
      zoom,
      attributionControl: false,
      pitchWithRotate: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 96 }), 'bottom-left');

    const applyOverlays = () => {
      if (disposed) return;
      loadedRef.current = true;
      const s = sceneRef.current;
      if (s) {
        applySatelliteLayer(asHost(map), s, stateRef.current);
        if (stateRef.current.visible) fitSceneBoundsIfNeeded(map, s);
      }
      if (sceneBRef.current) applyCompareLayer(asHost(map), sceneBRef.current);
      if (overlayRef.current) {
        applyIndexOverlay(map, overlayRef.current);
        setIndexOverlayOpacity(map, stateRef.current.visible ? stateRef.current.opacity : 0);
      }
      onMapReady?.(map);
    };

    const reportBasemapError = (error: unknown) => {
      if (disposed) return;
      const normalized = error instanceof Error ? error : new Error(String(error));
      console.error('Esri basemap error', normalized);
      onBasemapError?.(normalized);
    };

    if (basemap.provider === 'esri') {
      const session = getSharedEsriBasemapSession(basemap).catch((error: unknown) => {
        reportBasemapError(error);
        throw error;
      });
      void session.then((startedSession) => {
        startedSession.on('BasemapSessionError', (error) => {
          reportBasemapError(error);
        });
      }).catch(() => {
        // Already reported above. Keep the rejection handled for React/browser logs.
      });

      const esriStyle = new BasemapStyle({
        style: basemap.style,
        session,
        preferences: { places: basemap.places },
      });

      esriStyle.on('BasemapStyleLoad', () => {
        map.once('styledata', applyOverlays);
      });
      esriStyle.on('BasemapStyleError', (error) => {
        reportBasemapError(error);
      });
      void esriStyle.loadStyle().then(() => {
        if (!disposed) esriStyle.applyTo(map);
      }).catch(reportBasemapError);
    } else if (basemap.provider === 'osm') {
      map.once('styledata', applyOverlays);
      map.setStyle(OSM_BASEMAP_STYLE);
    } else {
      map.once('styledata', applyOverlays);
    }

    return () => {
      disposed = true;
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

  // Compare ("B") layer: add/replace beneath A, or remove when compare is off.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (sceneB) {
      applyCompareLayer(asHost(map), sceneB);
    } else {
      removeCompareLayer(asHost(map));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneKeyB]);

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

  // Field-clipped index overlay image: add/update/remove when it changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyIndexOverlay(map, overlayRef.current);
    setIndexOverlayOpacity(map, visible ? opacity : 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey]);

  // Live overlay opacity/visibility (no image refetch).
  useEffect(() => {
    const map = mapRef.current;
    if (map && loadedRef.current) setIndexOverlayOpacity(map, visible ? opacity : 0);
  }, [opacity, visible]);

  return <div ref={ containerRef } className="absolute inset-0 size-full" data-testid="map-canvas" />;
}
