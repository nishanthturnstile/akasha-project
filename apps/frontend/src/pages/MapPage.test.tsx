import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import MapPage from '@/pages/MapPage';
import { MapViewProvider } from '@/state/mapViewContext';
import type { MapViewState } from '@/state/mapViewState';
import type { FieldStatisticsResponse, FieldTrendResponse, ObservationCandidate, Plot, SceneDate } from '@/types/api';

const coordinateReadoutState = vi.hoisted(() => ({
  lookups: [] as Array<((point: { lng: number; lat: number }) => Promise<unknown>) | undefined>,
}));

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
    indexOverlay?: { url?: string; coordinates?: unknown } | null;
    visible: boolean;
  }) => (
    <div
      data-testid="map-layer-manager"
      data-tile-template={ scene?.tileUrlTemplate ?? '' }
      data-compare-tile-template={ sceneB?.tileUrlTemplate ?? '' }
      data-index-overlay-url={ indexOverlay?.url ?? '' }
      data-index-overlay-coordinates={ JSON.stringify(indexOverlay?.coordinates ?? null) }
      data-attribution={ scene?.attribution ?? '' }
      data-basemap-style={ basemap.style ?? '' }
      data-basemap-places={ basemap.places ?? '' }
      data-visible={ String(visible) }
    />
  ),
}));

vi.mock('@/components/map/CoordinateReadout', () => ({
  CoordinateReadout: ({
    indexLookup,
  }: {
    indexLookup?: (point: { lng: number; lat: number }) => Promise<unknown>;
  }) => {
    coordinateReadoutState.lookups.push(indexLookup);
    return (
      <button
        type="button"
        data-testid="coordinate-readout-mock"
        data-index-lookup={ String(Boolean(indexLookup)) }
        onClick={ () => {
          void indexLookup?.({ lng: 77.5946, lat: 12.9716 });
        } }
      >
        Coordinate readout
      </button>
    );
  },
}));

type MapPageProps = {
  hidePlotToolbar?: boolean;
  simplifiedMapControls?: boolean;
  topLeftCoords?: boolean;
};

function renderMapPage(initialState?: Partial<MapViewState>, props: MapPageProps = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={ queryClient }>
        <TooltipProvider>
          <MapViewProvider initialState={ { overlaysVisible: true, ...initialState } }>
            <MapPage { ...props } />
          </MapViewProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
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
  coordinateReadoutState.lookups.length = 0;
  window.localStorage.clear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function stubAkashaFetch({
  resourcesatDates = [makeDate('2026-03-19', { isLatestUsable: true, metricsProvisional: true })],
  sentinelDates = [makeDate('2026-03-20', { isLatestUsable: true, metricsProvisional: false })],
  liss4Dates = [makeDate('2026-01-15', { isLatestUsable: true, metricsProvisional: true })],
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
  defaultSourceId = 'resourcesat-2a-liss3-boa',
  bestCandidates,
}: {
  resourcesatDates?: SceneDate[];
  sentinelDates?: SceneDate[];
  liss4Dates?: SceneDate[];
  sarDates?: SceneDate[];
  plots?: Plot[];
  fieldStatistics?: FieldStatisticsResponse;
  fieldTrend?: FieldTrendResponse;
  defaultSourceId?: string;
  /** When provided, /api/observations/best returns these candidates (best-mode tests). */
  bestCandidates?: ObservationCandidate[];
} = {}) {
  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  vi.stubEnv('VITE_BASEMAP_PROVIDER', 'osm');
  vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:akasha-index-overlay'),
    revokeObjectURL: vi.fn(),
  });
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
            defaultSourceId,
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
            adminIngestionLiveTriggerEnabled: false,
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
              displayModes: ['FCC', 'NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              defaultDisplayMode: 'FCC',
              mapDisplayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              defaultMapDisplayMode: 'NDVI',
              attribution: 'ISRO-IRS, ISRO/NRSC, Bhoonidhi',
            },
            {
              id: 'sentinel-2-l2a',
              label: 'Sentinel-2 L2A',
              provider: 'pipeline',
              pipelineBacked: true,
              kind: 'optical',
              supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              displayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              defaultDisplayMode: 'NDVI',
              mapDisplayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
              defaultMapDisplayMode: 'NDVI',
              attribution: 'Sentinel-2 via Akasha ingestion pipeline',
            },
            {
              id: 'resourcesat-2a-liss4-mx70-l2',
              label: 'ResourceSat-2A LISS-4 MX70 L2',
              provider: 'ISRO/NRSC Bhoonidhi',
              kind: 'optical',
              supportedIndices: ['NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
              displayModes: ['FCC', 'NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
              defaultDisplayMode: 'FCC',
              mapDisplayModes: ['NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
              defaultMapDisplayMode: 'NDVI',
              attribution: 'ISRO-IRS, ISRO/NRSC, Bhoonidhi',
              resolutionMeters: 5.8,
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
            displayMode: 'NDVI',
            defaultDisplayMode: 'FCC',
            mapDisplayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
            defaultMapDisplayMode: 'NDVI',
            tileUrlTemplate: null,
            minzoom: 0,
            maxzoom: 14,
            attribution: 'ISRO-IRS, ISRO/NRSC, Bhoonidhi',
            usablePixelPercent: 90,
            metricsProvisional: true,
          }),
        );
      }

      if (path === '/api/fields') {
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

      if (path.startsWith('/api/fields/plot-1/overlay/')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({
            'Content-Type': 'image/png',
            'X-Akasha-Overlay-Corners': '[[77.001,13.002],[77.103,13.001],[77.104,12.9],[77,12.901]]',
            'X-Akasha-Overlay-Stretch': '-1.0,1.0',
          }),
          blob: async () => new Blob(['png'], { type: 'image/png' }),
        });
      }

      if (path.startsWith('/api/fields/plot-1/indices/point')) {
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            sourceId: 'sentinel-2-l2a',
            acquisitionDate: '2026-03-20',
            indexType: 'NDVI',
            lng: 77.5946,
            lat: 12.9716,
            value: 0.44,
            masked: false,
            maskClass: null,
          }),
        );
      }

      if (path.startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')) {
        return Promise.resolve(jsonResponse(resourcesatDates));
      }

      if (path.startsWith('/api/sources/sentinel-2-l2a/dates')) {
        return Promise.resolve(jsonResponse(sentinelDates));
      }

      if (path.startsWith('/api/sources/resourcesat-2a-liss4-mx70-l2/dates')) {
        return Promise.resolve(jsonResponse(liss4Dates));
      }

      if (path.startsWith('/api/sources/eos-04-sar-mrs-l2b/dates')) {
        return Promise.resolve(jsonResponse(sarDates));
      }

      if (path.startsWith('/api/observations/best') && bestCandidates !== undefined) {
        return Promise.resolve(
          jsonResponse({
            candidates: bestCandidates,
            query: {
              targetDate: null,
              startDate: null,
              endDate: null,
              lookbackDays: 92,
              indexType: null,
              useCase: 'field',
              allowCoarse: false,
              windowDays: 30,
              maxCandidates: 30,
            },
          }),
        );
      }

      throw new Error(`Unexpected request: ${path}`);
    }),
  );
}

describe('MapPage source defaults', () => {
  it('uses config.defaultSourceId when no persisted active source exists', async () => {
    stubAkashaFetch({ defaultSourceId: 'sentinel-2-l2a' });

    renderMapPage();

    await waitFor(() => {
      expect(screen.getByTestId('layer-source-trigger').textContent).toContain('Sentinel-2 L2A');
    });

    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;
    expect(
      calls.some(([input]) => String(input).startsWith('/api/sources/sentinel-2-l2a/dates')),
    ).toBe(true);
  });

  it('keeps a persisted active source ahead of config.defaultSourceId', async () => {
    stubAkashaFetch({ defaultSourceId: 'sentinel-2-l2a' });

    renderMapPage({ activeSourceId: 'resourcesat-2a-liss3-boa' });

    await waitFor(() => {
      expect(screen.getByTestId('layer-source-trigger').textContent).toContain(
        'ResourceSat-2A LISS-3 BOA',
      );
    });

    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;
    expect(
      calls.some(([input]) => String(input).startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')),
    ).toBe(true);
  });
});

describe('MapPage pipeline point lookup', () => {
  it('wires hover point lookup for pipeline-backed Sentinel sources', async () => {
    stubAkashaFetch({
      defaultSourceId: 'sentinel-2-l2a',
      plots: [FIELD_PLOT],
      fieldStatistics: makeFieldStatistics({
        provider: 'pipeline',
        sourceId: 'sentinel-2-l2a',
        acquisitionDate: '2026-03-20',
      }),
      fieldTrend: makeFieldTrend({
        provider: 'pipeline',
        scope: 'pipeline',
        sourceId: 'sentinel-2-l2a',
        endDate: '2026-03-20',
      }),
    });

    renderMapPage({ selectedPlotId: 'plot-1' }, { topLeftCoords: true });

    await waitFor(() => {
      expect(screen.getByTestId('layer-source-trigger').textContent).toContain('Sentinel-2 L2A');
      expect(screen.getByTestId('coordinate-readout-mock').getAttribute('data-index-lookup')).toBe(
        'true',
      );
    });

    fireEvent.click(screen.getByTestId('coordinate-readout-mock'));

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      expect(calls.some(([input]) => String(input).includes('/indices/point'))).toBe(true);
    });
  });
});

describe('MapPage native source behavior', () => {
  it('shows the empty map state before a field is selected', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('map-layer-manager');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toBe('');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-index-overlay-url')).toBe('');
    expect(screen.getByTestId('attribution').textContent).toContain('OpenStreetMap');
  });

  it('shows SAR notes and hides optical index controls after SAR selection', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('map-layer-manager');

    fireEvent.click(screen.getByTestId('layer-source-trigger'));
    fireEvent.click(await screen.findByTestId('source-tab-eos-04-sar-mrs-l2b'));

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

    await screen.findByTestId('map-layer-manager');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toBe('');
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

    await screen.findByTestId('map-layer-manager');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toBe(
      '',
    );

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
  it('defaults to a field-clipped NDVI overlay when a field is selected', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => {
      const manager = screen.getByTestId('map-layer-manager');
      expect(manager.getAttribute('data-tile-template')).toBe('');
      expect(manager.getAttribute('data-index-overlay-url')).toBe('blob:akasha-index-overlay');
      expect(manager.getAttribute('data-index-overlay-coordinates')).toBe(
        '[[77.001,13.002],[77.103,13.001],[77.104,12.9],[77,12.901]]',
      );
    });
    expect(screen.getByTestId('layer-display-trigger').textContent).toContain('NDVI');
  });

  it('shows only index overlay modes in the layer picker', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1' });

    fireEvent.click(await screen.findByTestId('layer-display-trigger'));
    expect(screen.getByTestId('display-mode-NDVI')).toBeTruthy();
    expect(screen.getByTestId('display-mode-MSAVI')).toBeTruthy();
    expect(screen.getByTestId('display-mode-NDMI')).toBeTruthy();
    expect(screen.getByTestId('display-mode-NDWI_GREEN_NIR')).toBeTruthy();
    expect(screen.queryByTestId('display-mode-FCC')).toBeNull();
  });

  it('updates the field overlay when the native display mode changes', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1' });

    fireEvent.click(await screen.findByTestId('layer-display-trigger'));
    fireEvent.click(await screen.findByTestId('display-mode-MSAVI'));

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-index-overlay-url')).toBe(
        'blob:akasha-index-overlay',
      );
    });

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      expect(calls.some(([input]) => String(input).includes('/overlay/MSAVI.png'))).toBe(true);
    });
  });

  it('updates the overlay URL when the selected date changes from the timeline', async () => {
    stubAkashaFetch({
      plots: [FIELD_PLOT],
      resourcesatDates: [
        makeDate('2026-03-01'),
        makeDate('2026-03-19', { isLatestUsable: true, metricsProvisional: true }),
      ],
    });

    renderMapPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      expect(calls.some(([input]) => String(input).includes('acquisitionDate=2026-03-19'))).toBe(
        true,
      );
    });

    fireEvent.click(screen.getByTestId('date-chip-2026-03-01'));

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      expect(calls.some(([input]) => String(input).includes('acquisitionDate=2026-03-01'))).toBe(
        true,
      );
    });
  });

  it('falls back from a stale FCC selection to NDVI for ResourceSat fields', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT] });

    renderMapPage({ selectedPlotId: 'plot-1', displayMode: 'FCC' });

    await waitFor(() => {
      const manager = screen.getByTestId('map-layer-manager');
      expect(manager.getAttribute('data-tile-template')).toBe('');
      expect(manager.getAttribute('data-index-overlay-url')).toBe('blob:akasha-index-overlay');
    });
    expect(screen.getByTestId('layer-display-trigger').textContent).toContain('NDVI');
  });
});

// ---------------------------------------------------------------------------
// TASK-072: Best-available mode integration tests (outcomes 4, 5)
// ---------------------------------------------------------------------------

describe('MapPage best-available mode', () => {
  it('source-specific timeline is the default — calls source dates, not observations/best', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('map-layer-manager');

    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;

    // Source-specific dates endpoint must be called in the default (source) mode.
    expect(
      calls.some(([input]) => String(input).startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')),
    ).toBe(true);
    // Backend best-observation resolver must NOT be queried in source-specific mode.
    expect(
      calls.some(([input]) => String(input).startsWith('/api/observations/best')),
    ).toBe(false);
  });

  it('in best mode calls /api/observations/best and shows backend-resolved provenance labels', async () => {
    const bestCandidates: ObservationCandidate[] = [
      {
        sourceId: 'resourcesat-2a-liss4-mx70-l2',
        acquisitionDate: '2026-01-14',
        resolutionMeters: 5.8,
        analysisLevel: 'field',
        usablePixelPercent: 88,
        coveragePercent: 95,
        cloudMaskedPercent: 5,
        tileAvailable: true,
        isLatestUsable: true,
        score: 92.0,
        sourcePriority: 100,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: ['NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
        label: 'ResourceSat-2A LISS-4 MX70 L2',
      },
      {
        sourceId: 'resourcesat-2a-liss3-boa',
        acquisitionDate: '2026-01-15',
        resolutionMeters: 24.0,
        analysisLevel: 'field',
        usablePixelPercent: 85,
        coveragePercent: 92,
        cloudMaskedPercent: 8,
        tileAvailable: true,
        isLatestUsable: false,
        score: 78.0,
        sourcePriority: 80,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        label: 'ResourceSat-2A LISS-3 BOA',
      },
    ];

    stubAkashaFetch({ bestCandidates });

    renderMapPage({ bestMode: true, displayMode: 'FCC' });

    // The LISS-4 chip must appear with the provenance label derived from the backend sourceId
    // and resolutionMeters, proving the frontend uses backend-resolved candidates.
    await waitFor(() => {
      expect(screen.getByTestId('date-chip-provenance-2026-01-14').textContent).toBe('LISS-4 · 5.8 m');
    });

    // LISS-3 chip with its own provenance label.
    await waitFor(() => {
      expect(screen.getByTestId('date-chip-provenance-2026-01-15').textContent).toBe('LISS-3 · 24 m');
    });

    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;

    // Backend best-observation endpoint must be called in best mode.
    expect(
      calls.some(([input]) => String(input).startsWith('/api/observations/best')),
    ).toBe(true);
    // Source-specific dates endpoint must NOT be called in best mode.
    expect(
      calls.some(([input]) => String(input).startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')),
    ).toBe(false);
  });

  it('in best mode sends the active analytic intent to the backend resolver', async () => {
    stubAkashaFetch({ bestCandidates: [] });

    renderMapPage({ bestMode: true, displayMode: 'NDMI' });

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      const bestUrl = String(
        calls.find(([input]) => String(input).startsWith('/api/observations/best'))?.[0] ?? '',
      );
      expect(bestUrl).toContain('indexType=NDMI');
      expect(bestUrl).toContain('useCase=field');
      expect(bestUrl).toContain('allowCoarse=false');
    });
  });

  it('selecting a best-mode date preserves the source-specific source when returning to source mode', async () => {
    const bestCandidates: ObservationCandidate[] = [
      {
        sourceId: 'resourcesat-2a-liss4-mx70-l2',
        acquisitionDate: '2026-01-15',
        resolutionMeters: 5.8,
        analysisLevel: 'field',
        usablePixelPercent: 88,
        coveragePercent: 95,
        cloudMaskedPercent: 5,
        tileAvailable: true,
        isLatestUsable: true,
        score: 92.0,
        sourcePriority: 100,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: ['NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
        label: 'ResourceSat-2A LISS-4 MX70 L2',
      },
    ];
    stubAkashaFetch({ bestCandidates });

    renderMapPage({ bestMode: true, activeSourceId: 'resourcesat-2a-liss3-boa' });

    await waitFor(() => {
      expect(screen.getByTestId('date-chip-2026-01-15')).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId('date-chip-2026-01-15'));
    fireEvent.click(screen.getByTestId('timeline-best-mode-toggle'));

    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as {
        mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
      }).mock.calls;
      expect(
        calls.some(([input]) => String(input).startsWith('/api/sources/resourcesat-2a-liss3-boa/dates')),
      ).toBe(true);
      expect(
        calls.some(([input]) => String(input).startsWith('/api/sources/resourcesat-2a-liss4-mx70-l2/dates')),
      ).toBe(false);
    });
  });

  it('in best mode deduplicates same-date candidates and uses the resolved source for overlay requests', async () => {
    const bestCandidates: ObservationCandidate[] = [
      {
        sourceId: 'resourcesat-2a-liss4-mx70-l2',
        acquisitionDate: '2026-01-15',
        resolutionMeters: 5.8,
        analysisLevel: 'field',
        usablePixelPercent: 88,
        coveragePercent: 95,
        cloudMaskedPercent: 5,
        tileAvailable: true,
        isLatestUsable: true,
        score: 92.0,
        sourcePriority: 100,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: ['NDVI', 'MSAVI', 'NDWI_GREEN_NIR'],
        label: 'ResourceSat-2A LISS-4 MX70 L2',
      },
      {
        sourceId: 'resourcesat-2a-liss3-boa',
        acquisitionDate: '2026-01-15',
        resolutionMeters: 24.0,
        analysisLevel: 'field',
        usablePixelPercent: 85,
        coveragePercent: 92,
        cloudMaskedPercent: 8,
        tileAvailable: true,
        isLatestUsable: false,
        score: 78.0,
        sourcePriority: 80,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        label: 'ResourceSat-2A LISS-3 BOA',
      },
    ];

    stubAkashaFetch({ bestCandidates, plots: [FIELD_PLOT] });

    renderMapPage({ bestMode: true, selectedPlotId: 'plot-1' });

    await waitFor(() => {
      expect(screen.getAllByTestId('date-chip-2026-01-15')).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId('date-chip-provenance-2026-01-15').textContent).toBe('LISS-4 · 5.8 m');
    });
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-index-overlay-url')).toBe(
        'blob:akasha-index-overlay',
      );
    });
    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;
    const overlayUrl = String(
      calls.find(([input]) => String(input).includes('/api/fields/plot-1/overlay/'))?.[0] ?? '',
    );
    expect(overlayUrl).toContain('/api/fields/plot-1/overlay/NDVI.png');
    const overlayParams = new URLSearchParams(overlayUrl.split('?')[1] ?? '');
    expect(overlayParams.get('sourceId')).toBe('resourcesat-2a-liss4-mx70-l2');
    expect(overlayParams.get('acquisitionDate')).toBe('2026-01-15');
  });

  it('in best mode renders compare tiles from the compare date resolved source', async () => {
    const bestCandidates: ObservationCandidate[] = [
      {
        sourceId: 'eos-04-sar-mrs-l2b',
        acquisitionDate: '2026-01-15',
        resolutionMeters: 18.0,
        analysisLevel: 'field',
        usablePixelPercent: 92,
        coveragePercent: 98,
        cloudMaskedPercent: 0,
        tileAvailable: true,
        isLatestUsable: true,
        score: 90.0,
        sourcePriority: 70,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: [],
        label: 'EOS-04 SAR MRS L2B',
      },
      {
        sourceId: 'eos-04-sar-mrs-l2b',
        acquisitionDate: '2026-01-14',
        resolutionMeters: 18.0,
        analysisLevel: 'field',
        usablePixelPercent: 89,
        coveragePercent: 96,
        cloudMaskedPercent: 0,
        tileAvailable: true,
        isLatestUsable: false,
        score: 84.0,
        sourcePriority: 70,
        provenanceNote: null,
        isCoarse: false,
        supportedIndices: [],
        label: 'EOS-04 SAR MRS L2B',
      },
    ];

    stubAkashaFetch({ bestCandidates });

    renderMapPage({
      activeSourceId: 'eos-04-sar-mrs-l2b',
      bestMode: true,
      compareEnabled: true,
      compareDate: '2026-01-14',
      displayMode: 'VV_GRAYSCALE',
    });

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toContain(
        '/api/tiles/eos-04-sar-mrs-l2b/2026-01-14/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });
  });
});
