import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import type { Field, FieldStatisticsResponse, FieldTrendResponse, SceneDate, Source } from '@/types/api';

vi.mock('@/pages/MapPage', () => ({
  default: () => <div data-testid="map-page" />,
}));

vi.mock('@/components/seasons/EditFieldDialog', () => ({
  default: () => null,
}));

let FieldAnalyticsPage: typeof import('@/pages/monitoring/FieldAnalyticsPage').default;

beforeEach(async () => {
  FieldAnalyticsPage = (await import('@/pages/monitoring/FieldAnalyticsPage')).default;
});

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => payload,
  };
}

const field: Field = {
  id: 'field-1',
  userId: 'user-1',
  name: 'Pipeline field',
  areaHa: 3.2,
  geometry: {
    type: 'Polygon',
    coordinates: [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]],
  },
  groupId: null,
  seasonIds: [],
  vegetationData: [],
  createdAt: null,
  updatedAt: null,
};

const sentinelSource: Source = {
  id: 'sentinel-2-l2a',
  label: 'Sentinel-2 L2A',
  provider: 'Copernicus',
  kind: 'optical',
  displayModes: ['RGB', 'NDVI'],
  defaultDisplayMode: 'RGB',
  mapDisplayModes: ['NDVI'],
  defaultMapDisplayMode: 'NDVI',
  supportedIndices: ['NDVI'],
  maskMethod: 'Sentinel-2 pipeline mask',
  availableMaskOptions: ['clouds', 'cloudShadows', 'cirrus'],
  metricsProvisional: true,
  analysisLevel: 'field',
  availabilityStatus: 'active',
};

const sceneDate: SceneDate = {
  acquisitionDate: '2026-01-13',
  datetime: '2026-01-13T00:00:00Z',
  usablePixelPercent: 92,
  cloudMaskedPercent: 4,
  coveragePercent: 100,
  isLatestUsable: true,
  metricsProvisional: true,
  tileAvailable: false,
  sensor: 'S2',
};

function makeStatistics(): FieldStatisticsResponse {
  return {
    plotId: 'field-1',
    provider: 'native',
    scope: 'field',
    indexType: 'NDVI',
    sourceId: 'sentinel-2-l2a',
    acquisitionDate: '2026-01-13',
    cloudMask: { clouds: true, cloudShadows: true, cirrus: true },
    statistics: {
      min: 0.1,
      max: 0.8,
      mean: 0.54,
      stddev: 0.08,
      validPixelPercent: 92,
      cloudMaskedPercent: 4,
      coveragePercent: 100,
    },
    pixelCounts: {
      totalPixels: 100,
      nodataPixels: 0,
      coveragePixels: 100,
      maskedPixels: 4,
      validPixels: 92,
    },
    metadata: {
      formula: '(NIR - RED) / (NIR + RED)',
      bands: ['B08', 'B04'],
      warnings: [],
      pipeline: {
        source: 'sentinel-2-l2a',
        providerRoute: 'earthsearch:sentinel-2-l2a',
        requestedDate: '2026-01-13',
        selectedSceneDate: '2026-01-13',
        freshness: { status: 'AVAILABLE', aoiId: 'bangalore_60km_geodesic_aoi' },
      },
    },
  };
}

function makeTrend(): FieldTrendResponse {
  return {
    plotId: 'field-1',
    provider: 'native',
    scope: 'native_fallback',
    sourceId: 'sentinel-2-l2a',
    indexType: 'NDVI',
    startDate: '2025-07-17',
    endDate: '2026-01-13',
    points: [],
    metadata: { bands: ['B08', 'B04'] },
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={ queryClient }>
        <MapViewProvider
          initialState={ {
            overlaysVisible: true,
            activeSourceId: 'sentinel-2-l2a',
            selectedPlotId: 'field-1',
          } }
        >
          <FieldAnalyticsPage />
        </MapViewProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FieldAnalyticsPage pipeline integration', () => {
  it('renders the real index panel and posts selected field stats to the Sentinel-2 pipeline source', async () => {
    const requests: Array<{ url: string; body?: unknown }> = [];
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      requests.push({
        url,
        body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
      });
      if (url === '/api/config') {
        return jsonResponse({
          appName: 'Akasha',
          aoi: { id: 'aoi', name: 'AOI', center: [77, 13], zoom: 10, bounds: [76, 12, 78, 14] },
          basemapStyleUrl: '',
          basemap: {
            provider: 'empty',
            style: 'empty',
            styleFamily: 'empty',
            usageModel: 'session',
            places: 'none',
            sessionDurationSeconds: 3600,
          },
          maxPolygonAreaHa: 1000,
          maxPolygonVertices: 500,
          usablePixelThresholdPercent: 70,
          supportedIndices: ['NDVI'],
          defaultIndex: 'NDVI',
          adminIngestionLiveTriggerEnabled: false,
        });
      }
      if (url === '/api/sources') return jsonResponse([sentinelSource]);
      if (url.startsWith('/api/fields/field-1/dates')) return jsonResponse([sceneDate]);
      if (url.startsWith('/api/sources/sentinel-2-l2a/dates')) return jsonResponse([sceneDate]);
      if (url === '/api/fields') return jsonResponse([field]);
      if (url.startsWith('/api/seasons')) return jsonResponse([]);
      if (url === '/api/fields/field-1/indices/statistics') return jsonResponse(makeStatistics());
      if (url.startsWith('/api/fields/field-1/analytics/trend')) return jsonResponse(makeTrend());
      return jsonResponse({});
    });

    renderPage();

    await waitFor(
      () => {
        expect(
          requests.some(
            (request) => request.url === '/api/fields/field-1/indices/statistics',
          ),
        ).toBe(true);
      },
      { timeout: 15_000 },
    );
    expect(requests.some((request) => request.url.startsWith('/api/fields/field-1/dates'))).toBe(true);
    expect(requests.some((request) => request.url.startsWith('/api/sources/sentinel-2-l2a/dates'))).toBe(false);

    const statsRequest = requests.find((request) => request.url === '/api/fields/field-1/indices/statistics');
    expect(statsRequest?.body).toMatchObject({
      sourceId: 'sentinel-2-l2a',
      acquisitionDate: '2026-01-13',
      indexType: 'NDVI',
    });
    expect(screen.getByTestId('index-panel')).toBeTruthy();
  });
});
