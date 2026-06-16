import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import MapPage from '@/pages/MapPage';
import { MapViewProvider } from '@/state/mapViewContext';
import type { MapViewState } from '@/state/mapViewState';
import type { FieldStatisticsResponse, FieldTrendResponse, Plot, SceneDate } from '@/types/api';

vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: ({
    basemap,
    scene,
    sceneB,
    indexOverlay,
    visible,
  }: {
    basemap: { style?: string; places?: string };
    scene: { tileUrlTemplate?: string; attribution?: string } | null;
    sceneB?: { tileUrlTemplate?: string } | null;
    indexOverlay?: { url?: string } | null;
    visible: boolean;
  }) => (
    <div
      data-testid="map-layer-manager"
      data-tile-template={ scene?.tileUrlTemplate ?? '' }
      data-compare-tile-template={ sceneB?.tileUrlTemplate ?? '' }
      data-index-overlay-url={ indexOverlay?.url ?? '' }
      data-attribution={ scene?.attribution ?? '' }
      data-basemap-style={ basemap.style ?? '' }
      data-basemap-places={ basemap.places ?? '' }
      data-visible={ String(visible) }
    />
  ),
}));

function renderMapPage(initialState?: Partial<MapViewState>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={ queryClient }>
      <TooltipProvider>
        <MapViewProvider initialState={ initialState }>
          <MapPage />
        </MapViewProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  };
}

function makeDate(acquisitionDate: string, overrides: Partial<SceneDate> = {}): SceneDate {
  return {
    acquisitionDate,
    datetime: `${acquisitionDate}T00:00:00Z`,
    usablePixelPercent: 90,
    cloudMaskedPercent: 10,
    coveragePercent: 100,
    isLatestUsable: false,
    metricsProvisional: false,
    tileAvailable: true,
    ...overrides,
  };
}

const FIELD_PLOT: Plot = {
  id: 'plot-1',
  name: 'North Field',
  geometry: {
    type: 'Polygon',
    coordinates: [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12]]],
  },
  areaHa: 5,
  createdAt: null,
  updatedAt: null,
};

function makeFieldStatistics(overrides: Partial<FieldStatisticsResponse> = {}): FieldStatisticsResponse {
  return {
    plotId: 'plot-1',
    provider: 'native',
    scope: 'field',
    indexType: 'NDVI',
    sourceId: 'resourcesat-2a-liss3-boa',
    acquisitionDate: '2026-03-19',
    cloudMask: { clouds: true, cloudShadows: true, cirrus: false },
    statistics: {
      min: 0.1,
      max: 0.8,
      mean: 0.56,
      stddev: 0.12,
      validPixelPercent: 91,
      cloudMaskedPercent: 6,
      coveragePercent: 97,
    },
    pixelCounts: {
      totalPixels: 100,
      nodataPixels: 3,
      coveragePixels: 97,
      maskedPixels: 6,
      validPixels: 91,
    },
    metadata: {
      formula: '(BAND4 - BAND3) / (BAND4 + BAND3)',
      bands: ['BAND4', 'BAND3'],
      warnings: [],
    },
    ...overrides,
  };
}

function makeFieldTrend(overrides: Partial<FieldTrendResponse> = {}): FieldTrendResponse {
  return {
    plotId: 'plot-1',
    provider: 'native',
    scope: 'native_fallback',
    sourceId: 'resourcesat-2a-liss3-boa',
    indexType: 'NDVI',
    startDate: '2025-12-03',
    endDate: '2026-03-19',
    points: [
      {
        acquisitionDate: '2026-03-01',
        mean: 0.5,
        min: 0.1,
        max: 0.75,
        stddev: 0.1,
        validPixelPercent: 88,
        cloudMaskedPercent: 12,
        coveragePercent: 100,
        metricsProvisional: true,
      },
      {
        acquisitionDate: '2026-03-19',
        mean: 0.56,
        min: 0.1,
        max: 0.8,
        stddev: 0.12,
        validPixelPercent: 91,
        cloudMaskedPercent: 6,
        coveragePercent: 97,
        metricsProvisional: true,
      },
    ],
    metadata: {
      formula: '(BAND4 - BAND3) / (BAND4 + BAND3)',
      bands: ['BAND4', 'BAND3'],
    },
    ...overrides,
  };
}

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function stubAkashaFetch({
  resourcesatDates = [makeDate('2026-03-19', { isLatestUsable: true, metricsProvisional: true })],
  sarDates = [
    makeDate('2026-04-26', {
      usablePixelPercent: null,
      cloudMaskedPercent: null,
      coveragePercent: null,
      isLatestUsable: true,
    }),
  ],
  plots = [],
  fieldStatistics = makeFieldStatistics(),
  fieldTrend = makeFieldTrend(),
}: {
  resourcesatDates?: SceneDate[];
  sarDates?: SceneDate[];
  plots?: Plot[];
  fieldStatistics?: FieldStatisticsResponse;
  fieldTrend?: FieldTrendResponse;
} = {}) {
  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);

      if (path === '/api/config') {
        return Promise.resolve(
          jsonResponse({
            appName: 'Akasha',
            aoi: {
              id: 'south-india',
              name: 'South India',
              center: [78, 12],
              zoom: 8,
              bounds: [74, 8, 81, 14],
            },
            basemapStyleUrl: '',
            basemap: {
              provider: 'esri',
              style: 'arcgis/imagery',
              styleFamily: 'arcgis',
              usageModel: 'session',
              places: 'none',
              sessionDurationSeconds: 43200,
            },
            maxPolygonAreaHa: 100,
            maxPolygonVertices: 40,
            usablePixelThresholdPercent: 70,
            supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
            defaultIndex: 'NDVI',
          }),
        );
      }

      if (path === '/api/sources') {
        return Promise.resolve(
          jsonResponse([
            {
              id: 'resourcesat-2a-liss3-boa',
              label: 'ResourceSat-2A LISS-3 BOA',
              provider: 'ISRO/NRSC Bhoonidhi',
              kind: 'optical',
              supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              displayModes: ['FCC', 'NDVI'],
              defaultDisplayMode: 'FCC',
              attribution: 'ISRO-IRS, ISRO/NRSC, Bhoonidhi',
            },
            {
              id: 'eos-04-sar-mrs-l2b',
              label: 'EOS-04 SAR MRS L2B',
              provider: 'ISRO/NRSC Bhoonidhi',
              kind: 'sar',
              supportedIndices: [],
              displayModes: ['VV_GRAYSCALE'],
              defaultDisplayMode: 'VV_GRAYSCALE',
              description: 'VV grayscale radar backscatter.',
              attribution: 'ISRO/NRSC Bhoonidhi',
            },
          ]),
        );
      }

      if (path === '/api/layers/default') {
        return Promise.resolve(
          jsonResponse({
            sourceId: 'resourcesat-2a-liss3-boa',
            acquisitionDate: '2026-03-19',
            displayMode: 'FCC',
            tileUrlTemplate:
              '/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png',
            minzoom: 0,
            maxzoom: 14,
            attribution: 'ISRO-IRS, ISRO/NRSC, Bhoonidhi',
            usablePixelPercent: 90,
            metricsProvisional: true,
          }),
        );
      }

      if (path === '/api/plots') {
        return Promise.resolve(jsonResponse(plots));
      }

      if (path === '/api/fields/plot-1/indices/statistics') {
        const requestBody = typeof init?.body === 'string' ? JSON.parse(init.body) : {};
        return Promise.resolve(
          jsonResponse({
            ...fieldStatistics,
            indexType: requestBody.indexType ?? fieldStatistics.indexType,
          }),
        );
      }

      if (path.startsWith('/api/fields/plot-1/analytics/trend')) {
        return Promise.resolve(jsonResponse(fieldTrend));
      }

      if (path.startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')) {
        return Promise.resolve(jsonResponse(resourcesatDates));
      }

      if (path.startsWith('/api/sources/eos-04-sar-mrs-l2b/dates')) {
        return Promise.resolve(jsonResponse(sarDates));
      }

      throw new Error(`Unexpected request: ${path}`);
    }),
  );
}

describe('MapPage native source behavior', () => {
  it('shows the field-required analytics state before a field is selected', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('index-panel');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-basemap-style')).toBe(
      'arcgis/imagery',
    );
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-basemap-places')).toBe(
      'none',
    );
    expect(screen.getByTestId('attribution').textContent).toBe('ISRO-IRS, ISRO/NRSC, Bhoonidhi');
    expect(
      screen.getByText('Select a field to view cloud-masked statistics and trend analytics.'),
    ).toBeTruthy();
  });

  it('shows SAR notes and hides optical index controls after SAR selection', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('index-panel');

    fireEvent.click(screen.getByTestId('layer-source-trigger'));
    fireEvent.click(await screen.findByTestId('source-tab-eos-04-sar-mrs-l2b'));

    await waitFor(() => {
      expect(screen.queryByTestId('index-panel')).toBeNull();
    });

    await waitFor(() => {
      expect(screen.getByTestId('nearest-pass-note').textContent).toContain(
        'Nearest radar pass: 2026-04-26.',
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/eos-04-sar-mrs-l2b/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('attribution').textContent).toContain('ISRO/NRSC Bhoonidhi');
    });
  });

  it('does not render the compare scene while satellite imagery is hidden', async () => {
    stubAkashaFetch({
      resourcesatDates: [
        makeDate('2026-03-01'),
        makeDate('2026-03-19', { isLatestUsable: true, metricsProvisional: true }),
      ],
    });

    renderMapPage({
      visible: false,
      compareEnabled: true,
      compareDate: '2026-04-20',
    });

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png',
      );
    });
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-visible')).toBe('false');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toBe(
      '',
    );
  });

  it('clears the stale compare scene when switching imagery sources', async () => {
    stubAkashaFetch({
      resourcesatDates: [
        makeDate('2026-03-01'),
        makeDate('2026-03-19', { isLatestUsable: true, metricsProvisional: true }),
      ],
    });

    renderMapPage({
      compareEnabled: true,
      compareDate: '2026-03-01',
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template'),
      ).toContain('/api/tiles/resourcesat-2a-liss3-boa/2026-03-01/FCC/{z}/{x}/{y}.png');
    });

    fireEvent.click(screen.getByTestId('layer-source-trigger'));
    fireEvent.click(await screen.findByTestId('source-tab-eos-04-sar-mrs-l2b'));

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/eos-04-sar-mrs-l2b/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toBe(
      '',
    );
  });
});

describe('MapPage selected-field native analytics', () => {
  it('keeps native source-date imagery active when a field is selected', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1' });

    await screen.findByTestId('index-panel');
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/resourcesat-2a-liss3-boa/2026-03-19/FCC/{z}/{x}/{y}.png',
      );
    });

    const chartTab = await screen.findByTestId('index-panel-tab-chart');
    fireEvent.mouseDown(chartTab);
    fireEvent.click(chartTab);

    expect((await screen.findAllByText('0.56')).length).toBeGreaterThan(0);
    expect(screen.getByTestId('field-trend-chart')).toBeTruthy();
    expect(screen.getByText('Akasha masked-raster analytics')).toBeTruthy();
  });

  it('switches native display modes and refetches selected-field statistics', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1' });

    fireEvent.click(await screen.findByTestId('layer-display-trigger'));
    fireEvent.click(await screen.findByTestId('display-mode-NDVI'));
    await waitFor(() => {
      const manager = screen.getByTestId('map-layer-manager');
      // EOS-style: full-scene raster is hidden (basemap imagery shows around the
      // field) and the index is painted via a field-clipped overlay image.
      expect(manager.getAttribute('data-tile-template')).toBe('');
      expect(manager.getAttribute('data-index-overlay-url')).toContain(
        '/api/fields/plot-1/overlay/NDVI.png',
      );
    });
    expect(screen.getByTestId('map-legend').getAttribute('data-display-mode')).toBe('NDVI');

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      const statsCall = calls
        .filter(([input]) => String(input) === '/api/fields/plot-1/indices/statistics')
        .map(([, init]) => (typeof init?.body === 'string' ? init.body : ''))
        .find((body) => body.includes('"indexType":"NDVI"'));
      expect(statsCall).toBeTruthy();
    });
  });
});
