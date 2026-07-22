import { act, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import type { EsriBasemapResolvedConfig } from '@/map/basemap';
import { resetSharedEsriBasemapSessionForTests } from '@/map/esriBasemapSession';

const hoisted = vi.hoisted(() => ({
  mapHandlers: new Map<string, Array<(...args: unknown[]) => void>>(),
  mapOnceHandlers: new Map<string, Array<(...args: unknown[]) => void>>(),
  layerIds: new Set<string>(),
  applyStyle: vi.fn(),
  createBasemapStyle: vi.fn(),
  createMap: vi.fn(),
  startSession: vi.fn(),
  setStyle: vi.fn(),
  addSource: vi.fn(),
  addLayer: vi.fn(),
  setPaintProperty: vi.fn(),
  applySatelliteLayer: vi.fn(),
  applyCompareLayer: vi.fn(),
  removeCompareLayer: vi.fn(),
  setSatelliteOpacity: vi.fn(),
  setSatelliteVisibility: vi.fn(),
}));

function triggerMapEvent(eventName: string) {
  const handlers = hoisted.mapHandlers.get(eventName) ?? [];
  for (const handler of handlers) handler();
  const onceHandlers = hoisted.mapOnceHandlers.get(eventName) ?? [];
  hoisted.mapOnceHandlers.delete(eventName);
  for (const handler of onceHandlers) handler();
}

let basemapStyleHandlers: Record<string, (event?: unknown) => void> = {};

vi.mock('@esri/maplibre-arcgis', () => ({
  BasemapSession: {
    start: hoisted.startSession,
  },
  BasemapStyle: class BasemapStyleMock {
    on = vi.fn((eventName: string, handler: (event?: unknown) => void) => {
      basemapStyleHandlers[eventName] = handler;
    });
    loadStyle = vi.fn(() => Promise.resolve({}));
    applyTo = hoisted.applyStyle;
    constructor(options: unknown) {
      hoisted.createBasemapStyle(options);
    }
  },
}));

vi.mock('maplibre-gl', () => {
  class MapMock {
    constructor() {
      hoisted.createMap();
    }
    addControl = vi.fn();
    on = vi.fn((eventName: string, handler: (...args: unknown[]) => void) => {
      const handlers = hoisted.mapHandlers.get(eventName) ?? [];
      handlers.push(handler);
      hoisted.mapHandlers.set(eventName, handlers);
    });
    once = vi.fn((eventName: string, handler: (...args: unknown[]) => void) => {
      const handlers = hoisted.mapOnceHandlers.get(eventName) ?? [];
      handlers.push(handler);
      hoisted.mapOnceHandlers.set(eventName, handlers);
    });
    setStyle = hoisted.setStyle;
    getLayer = vi.fn((id: string) => (hoisted.layerIds.has(id) ? {} : undefined));
    getSource = vi.fn(() => undefined);
    addSource = hoisted.addSource;
    addLayer = vi.fn((layer: { id: string }) => {
      hoisted.addLayer(layer);
      hoisted.layerIds.add(layer.id);
    });
    removeLayer = vi.fn((id: string) => {
      hoisted.layerIds.delete(id);
    });
    removeSource = vi.fn();
    setPaintProperty = hoisted.setPaintProperty;
    remove = vi.fn();
    getCanvas = vi.fn(() => ({ clientWidth: 800, clientHeight: 600 }));
    getBounds = vi.fn(() => ({
      getEast: () => 78,
      getWest: () => 77,
      getNorth: () => 13,
      getSouth: () => 12,
    }));
  }

  return {
    default: {
      Map: MapMock,
      ScaleControl: vi.fn(),
    },
  };
});

vi.mock('@/lib/satelliteLayer', () => ({
  applySatelliteLayer: hoisted.applySatelliteLayer,
  applyCompareLayer: hoisted.applyCompareLayer,
  isValidSceneBounds: vi.fn(() => false),
  removeCompareLayer: hoisted.removeCompareLayer,
  setSatelliteOpacity: hoisted.setSatelliteOpacity,
  setSatelliteVisibility: hoisted.setSatelliteVisibility,
  SAT_LAYER_ID: 'akasha-satellite',
  SAT_SOURCE_ID: 'akasha-satellite-source',
}));

const BASEMAP: EsriBasemapResolvedConfig = {
  provider: 'esri',
  apiKey: 'AAPK_TEST_BASEMAP_KEY',
  style: 'arcgis/imagery',
  styleFamily: 'arcgis',
  usageModel: 'session',
  places: 'none',
  sessionDurationSeconds: 43_200,
  refreshSafetyMarginSeconds: 300,
};

const TILE_BASEMAP: EsriBasemapResolvedConfig = {
  provider: 'esri',
  apiKey: 'AAPK_TEST_BASEMAP_KEY',
  style: 'arcgis/imagery',
  styleFamily: 'arcgis',
  usageModel: 'tile',
  places: 'none',
};

function sessionMock() {
  return { on: vi.fn(), off: vi.fn() };
}

const OSM_BASEMAP = {
  provider: 'osm',
  attribution: '© OpenStreetMap contributors',
} as const;

const EMPTY_BASEMAP = {
  provider: 'empty',
} as const;

afterEach(() => {
  resetSharedEsriBasemapSessionForTests();
  hoisted.mapHandlers.clear();
  hoisted.mapOnceHandlers.clear();
  hoisted.layerIds.clear();
  hoisted.applyStyle.mockReset();
  hoisted.createBasemapStyle.mockReset();
  hoisted.createMap.mockReset();
  hoisted.startSession.mockReset();
  hoisted.setStyle.mockReset();
  hoisted.addSource.mockReset();
  hoisted.addLayer.mockReset();
  hoisted.setPaintProperty.mockReset();
  hoisted.applySatelliteLayer.mockReset();
  hoisted.applyCompareLayer.mockReset();
  hoisted.removeCompareLayer.mockReset();
  hoisted.setSatelliteOpacity.mockReset();
  hoisted.setSatelliteVisibility.mockReset();
  basemapStyleHandlers = {};
});

describe('MapLayerManager Esri basemap lifecycle', () => {
  it('starts one Esri session, applies imagery with places disabled, and waits before overlays', async () => {
    const session = sessionMock();
    hoisted.startSession.mockResolvedValue(session);
    hoisted.applyStyle.mockReturnValue({});

    render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/a/{z}/{x}/{y}.png' } }
        opacity={ 0.75 }
        visible
      />,
    );

    expect(hoisted.startSession).toHaveBeenCalledWith({
      token: 'AAPK_TEST_BASEMAP_KEY',
      styleFamily: 'arcgis',
      duration: 43_200,
      autoRefresh: true,
      safetyMargin: 300,
    });
    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(1));
    expect(hoisted.createBasemapStyle).toHaveBeenCalledWith(
      expect.objectContaining({
        style: 'arcgis/imagery',
        preferences: { places: 'none' },
      }),
    );
    expect(hoisted.applySatelliteLayer).not.toHaveBeenCalled();

    basemapStyleHandlers.BasemapStyleLoad?.();
    expect(hoisted.applySatelliteLayer).not.toHaveBeenCalled();

    triggerMapEvent('styledata');
    expect(hoisted.applyStyle.mock.calls[0][0]).toBeTruthy();
    expect(hoisted.applySatelliteLayer).toHaveBeenCalledWith(
      expect.anything(),
      { tileUrlTemplate: '/api/tiles/a/{z}/{x}/{y}.png' },
      { opacity: 0.75, visible: true },
    );
  });

  it('swaps Akasha overlay scenes without reapplying the Esri basemap', async () => {
    hoisted.startSession.mockResolvedValue(sessionMock());
    hoisted.applyStyle.mockReturnValue({});

    const { rerender } = render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/a/{z}/{x}/{y}.png' } }
        opacity={ 1 }
        visible
      />,
    );
    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(1));
    basemapStyleHandlers.BasemapStyleLoad?.();
    triggerMapEvent('styledata');

    rerender(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/b/{z}/{x}/{y}.png' } }
        opacity={ 1 }
        visible
      />,
    );

    expect(hoisted.startSession).toHaveBeenCalledTimes(1);
    expect(hoisted.applyStyle).toHaveBeenCalledTimes(1);
    expect(hoisted.applySatelliteLayer).toHaveBeenCalledTimes(2);
    expect(hoisted.applySatelliteLayer.mock.calls[1][1]).toEqual({
      tileUrlTemplate: '/api/tiles/b/{z}/{x}/{y}.png',
    });
  });

  it('reuses one Esri session across equivalent map mounts in the same runtime', async () => {
    hoisted.startSession.mockResolvedValue(sessionMock());
    hoisted.applyStyle.mockReturnValue({});

    const first = render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
      />,
    );
    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(1));
    first.unmount();

    render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
      />,
    );

    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(2));
    expect(hoisted.startSession).toHaveBeenCalledTimes(1);
  });

  it('uses the API key directly in tile mode without starting a basemap session', async () => {
    hoisted.applyStyle.mockReturnValue({});

    render(
      <MapLayerManager
        basemap={ TILE_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/tile/{z}/{x}/{y}.png' } }
        opacity={ 0.8 }
        visible
      />,
    );

    expect(hoisted.startSession).not.toHaveBeenCalled();
    expect(hoisted.createBasemapStyle).toHaveBeenCalledWith({
      style: 'arcgis/imagery',
      token: 'AAPK_TEST_BASEMAP_KEY',
      preferences: { places: 'none' },
    });
    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(1));

    basemapStyleHandlers.BasemapStyleLoad?.();
    triggerMapEvent('styledata');
    expect(hoisted.applySatelliteLayer).toHaveBeenCalledWith(
      expect.anything(),
      { tileUrlTemplate: '/api/tiles/tile/{z}/{x}/{y}.png' },
      { opacity: 0.8, visible: true },
    );
  });

  it('does not recreate the tile basemap when Akasha layer state changes', async () => {
    hoisted.applyStyle.mockReturnValue({});
    const { rerender } = render(
      <MapLayerManager
        basemap={ TILE_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/a/{z}/{x}/{y}.png' } }
        indexOverlay={ null }
        opacity={ 1 }
        visible
      />,
    );
    await waitFor(() => expect(hoisted.applyStyle).toHaveBeenCalledTimes(1));
    basemapStyleHandlers.BasemapStyleLoad?.();
    triggerMapEvent('styledata');

    rerender(
      <MapLayerManager
        basemap={ TILE_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/b/{z}/{x}/{y}.png' } }
        indexOverlay={ {
          url: '/api/fields/f/overlay/NDVI.png',
          coordinates: [[77, 13], [78, 13], [78, 12], [77, 12]],
        } }
        opacity={ 0.5 }
        visible={ false }
      />,
    );

    expect(hoisted.createMap).toHaveBeenCalledTimes(1);
    expect(hoisted.createBasemapStyle).toHaveBeenCalledTimes(1);
    expect(hoisted.applyStyle).toHaveBeenCalledTimes(1);
    expect(hoisted.startSession).not.toHaveBeenCalled();
    expect(hoisted.applySatelliteLayer).toHaveBeenLastCalledWith(
      expect.anything(),
      { tileUrlTemplate: '/api/tiles/b/{z}/{x}/{y}.png' },
      { opacity: 0.5, visible: false },
    );
    expect(hoisted.applyCompareLayer).not.toHaveBeenCalled();
    expect(hoisted.addSource).toHaveBeenCalledWith(
      'akasha-index-overlay',
      expect.objectContaining({
        type: 'image',
        url: '/api/fields/f/overlay/NDVI.png',
      }),
    );
    expect(hoisted.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'akasha-index-overlay-layer', type: 'raster' }),
    );
    expect(hoisted.setPaintProperty).toHaveBeenCalledWith(
      'akasha-index-overlay-layer',
      'raster-opacity',
      0,
    );
    expect(hoisted.setSatelliteVisibility).toHaveBeenLastCalledWith(
      expect.anything(),
      false,
      0.5,
    );
  });

  it('sanitizes vendor authentication state before logging or reporting errors', () => {
    const onBasemapError = vi.fn();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const vendorError = Object.assign(
      new Error(`Request failed?token=${TILE_BASEMAP.apiKey}`),
      {
        code: 'ARC_REQUEST_FAILED',
        options: { authentication: { key: TILE_BASEMAP.apiKey } },
      },
    );

    render(
      <MapLayerManager
        basemap={ TILE_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
        onBasemapError={ onBasemapError }
      />,
    );

    basemapStyleHandlers.BasemapStyleError?.(vendorError);

    const reported = onBasemapError.mock.calls[0][0] as Error & { code?: string };
    expect(reported).not.toBe(vendorError);
    expect(reported.message).toBe('Request failed?token=[REDACTED]');
    expect(reported.message).not.toContain(TILE_BASEMAP.apiKey);
    expect(reported.code).toBe('ARC_REQUEST_FAILED');
    expect('options' in reported).toBe(false);
    expect(consoleError).toHaveBeenCalledWith('Esri basemap error', reported);
    expect(consoleError.mock.calls.flat()).not.toContain(vendorError);

    consoleError.mockRestore();
  });

  it('does not attach a session error listener after unmounting before resolution', async () => {
    let resolveSession!: (session: ReturnType<typeof sessionMock>) => void;
    const session = sessionMock();
    hoisted.startSession.mockReturnValue(new Promise((resolve) => {
      resolveSession = resolve;
    }));
    hoisted.applyStyle.mockReturnValue({});

    const mounted = render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
      />,
    );
    mounted.unmount();

    await act(async () => {
      resolveSession(session);
      await Promise.resolve();
    });

    expect(session.on).not.toHaveBeenCalled();
    expect(session.off).not.toHaveBeenCalled();
  });

  it('removes shared-session error listeners between sequential map mounts', async () => {
    const session = sessionMock();
    hoisted.startSession.mockResolvedValue(session);
    hoisted.applyStyle.mockReturnValue({});

    const first = render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
      />,
    );
    await waitFor(() => expect(session.on).toHaveBeenCalledTimes(1));
    const firstHandler = session.on.mock.calls[0][1];
    first.unmount();
    expect(session.off).toHaveBeenCalledWith('BasemapSessionError', firstHandler);

    const second = render(
      <MapLayerManager
        basemap={ BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ null }
        opacity={ 1 }
        visible
      />,
    );
    await waitFor(() => expect(session.on).toHaveBeenCalledTimes(2));
    const secondHandler = session.on.mock.calls[1][1];
    expect(secondHandler).not.toBe(firstHandler);
    second.unmount();
    expect(session.off).toHaveBeenCalledWith('BasemapSessionError', secondHandler);
    expect(session.off).toHaveBeenCalledTimes(2);
  });

  it('uses an OSM raster style without starting an Esri session and still applies overlays', () => {
    render(
      <MapLayerManager
        basemap={ OSM_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/osm-scene/{z}/{x}/{y}.png' } }
        opacity={ 0.6 }
        visible
      />,
    );

    expect(hoisted.startSession).not.toHaveBeenCalled();
    expect(hoisted.createBasemapStyle).not.toHaveBeenCalled();
    expect(hoisted.applyStyle).not.toHaveBeenCalled();
    expect(hoisted.setStyle).toHaveBeenCalledWith(
      expect.objectContaining({
        version: 8,
        sources: expect.objectContaining({
          'osm-raster': expect.objectContaining({ type: 'raster' }),
        }),
      }),
    );
    expect(hoisted.applySatelliteLayer).not.toHaveBeenCalled();

    triggerMapEvent('styledata');
    expect(hoisted.applySatelliteLayer).toHaveBeenCalledWith(
      expect.anything(),
      { tileUrlTemplate: '/api/tiles/osm-scene/{z}/{x}/{y}.png' },
      { opacity: 0.6, visible: true },
    );
  });

  it('uses an empty style without external basemap APIs and still applies overlays', () => {
    render(
      <MapLayerManager
        basemap={ EMPTY_BASEMAP }
        center={ [77.59, 12.97] }
        zoom={ 11 }
        scene={ { tileUrlTemplate: '/api/tiles/empty-scene/{z}/{x}/{y}.png' } }
        opacity={ 1 }
        visible
      />,
    );

    expect(hoisted.startSession).not.toHaveBeenCalled();
    expect(hoisted.createBasemapStyle).not.toHaveBeenCalled();
    expect(hoisted.applyStyle).not.toHaveBeenCalled();
    expect(hoisted.setStyle).not.toHaveBeenCalled();
    expect(hoisted.applySatelliteLayer).not.toHaveBeenCalled();

    triggerMapEvent('styledata');
    expect(hoisted.applySatelliteLayer).toHaveBeenCalledWith(
      expect.anything(),
      { tileUrlTemplate: '/api/tiles/empty-scene/{z}/{x}/{y}.png' },
      { opacity: 1, visible: true },
    );
  });
});
