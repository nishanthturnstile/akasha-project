import { render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import type { EsriBasemapResolvedConfig } from '@/map/basemap';
import { resetSharedEsriBasemapSessionForTests } from '@/map/esriBasemapSession';

const hoisted = vi.hoisted(() => ({
  mapHandlers: new Map<string, Array<(...args: unknown[]) => void>>(),
  mapOnceHandlers: new Map<string, Array<(...args: unknown[]) => void>>(),
  applyStyle: vi.fn(),
  createBasemapStyle: vi.fn(),
  startSession: vi.fn(),
  setStyle: vi.fn(),
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
    constructor() {}
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
  places: 'none',
  sessionDurationSeconds: 43_200,
  refreshSafetyMarginSeconds: 300,
};

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
  hoisted.applyStyle.mockReset();
  hoisted.createBasemapStyle.mockReset();
  hoisted.startSession.mockReset();
  hoisted.setStyle.mockReset();
  hoisted.applySatelliteLayer.mockReset();
  hoisted.applyCompareLayer.mockReset();
  hoisted.removeCompareLayer.mockReset();
  hoisted.setSatelliteOpacity.mockReset();
  hoisted.setSatelliteVisibility.mockReset();
  basemapStyleHandlers = {};
});

describe('MapLayerManager Esri basemap lifecycle', () => {
  it('starts one Esri session, applies imagery with places disabled, and waits before overlays', async () => {
    const session = {
      on: vi.fn(),
    };
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
    hoisted.startSession.mockResolvedValue({ on: vi.fn() });
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
    hoisted.startSession.mockResolvedValue({ on: vi.fn() });
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
