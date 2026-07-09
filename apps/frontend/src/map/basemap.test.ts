import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  BasemapConfigurationError,
  resolveBasemapConfig,
} from '@/map/basemap';
import type { AppConfig } from '@/types/api';

const CONFIG: AppConfig = {
  appName: 'Akasha',
  defaultSourceId: 'resourcesat-2a-liss3-boa',
  aoi: {
    id: 'bangalore',
    name: 'Bangalore',
    center: [77.59, 12.97],
    zoom: 11,
    bounds: [77.4, 12.8, 77.8, 13.2],
  },
  basemapStyleUrl: '',
  basemap: {
    provider: 'esri',
    style: 'arcgis/imagery',
    styleFamily: 'arcgis',
    usageModel: 'session',
    places: 'none',
    sessionDurationSeconds: 43_200,
  },
  maxPolygonAreaHa: 50,
  maxPolygonVertices: 5000,
  usablePixelThresholdPercent: 70,
  supportedIndices: ['NDVI'],
  defaultIndex: 'NDVI',
  adminIngestionLiveTriggerEnabled: false,
};

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('resolveBasemapConfig', () => {
  it('resolves Esri imagery session settings from app config', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
    vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');

    expect(resolveBasemapConfig(CONFIG)).toEqual({
      provider: 'esri',
      apiKey: 'AAPK_TEST_BASEMAP_KEY',
      style: 'arcgis/imagery',
      styleFamily: 'arcgis',
      places: 'none',
      sessionDurationSeconds: 43_200,
      refreshSafetyMarginSeconds: 300,
    });
  });

  it('rejects missing Esri API keys instead of using a fallback basemap', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
    vi.stubEnv('VITE_ESRI_API_KEY', '');

    expect(() => resolveBasemapConfig(CONFIG)).toThrow(BasemapConfigurationError);
    expect(() => resolveBasemapConfig(CONFIG)).toThrow('VITE_ESRI_API_KEY');
  });

  it('allows explicit Esri build-time overrides', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
    vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
    vi.stubEnv('VITE_ESRI_BASEMAP_STYLE', 'arcgis/imagery/standard');
    vi.stubEnv('VITE_ESRI_BASEMAP_PLACES', 'attributed');
    vi.stubEnv('VITE_ESRI_BASEMAP_SESSION_SECONDS', '3600');

    expect(resolveBasemapConfig(CONFIG)).toMatchObject({
      style: 'arcgis/imagery/standard',
      places: 'attributed',
      sessionDurationSeconds: 3600,
    });
  });

  it('uses VITE_BASEMAP_PROVIDER=osm ahead of the backend Esri config without requiring an Esri key', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', 'osm');
    vi.stubEnv('VITE_ESRI_API_KEY', '');

    expect(resolveBasemapConfig(CONFIG)).toEqual({
      provider: 'osm',
      attribution: '© OpenStreetMap contributors',
    });
  });

  it('uses VITE_BASEMAP_PROVIDER=empty as a no-network basemap without requiring an Esri key', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', 'empty');
    vi.stubEnv('VITE_ESRI_API_KEY', '');

    expect(resolveBasemapConfig(CONFIG)).toEqual({
      provider: 'empty',
    });
  });

  it('uses the backend provider when no frontend provider override is set', () => {
    vi.stubEnv('VITE_BASEMAP_PROVIDER', '');
    vi.stubEnv('VITE_ESRI_API_KEY', '');
    const config = {
      ...CONFIG,
      basemap: {
        ...CONFIG.basemap,
        provider: 'osm',
      },
    } as unknown as AppConfig;

    expect(resolveBasemapConfig(config)).toEqual({
      provider: 'osm',
      attribution: '© OpenStreetMap contributors',
    });
  });
});
