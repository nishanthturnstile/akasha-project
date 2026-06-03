import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import MapPage from '@/pages/MapPage';
import { MapViewProvider, type MapViewState } from '@/state/mapViewContext';
import type { FieldSceneListResponse, Plot, SceneDate } from '@/types/api';

vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: ({
    scene,
    sceneB,
    visible,
  }: {
    scene: { tileUrlTemplate?: string; attribution?: string } | null;
    sceneB?: { tileUrlTemplate?: string } | null;
    visible: boolean;
  }) => (
    <div
      data-testid="map-layer-manager"
      data-tile-template={ scene?.tileUrlTemplate ?? '' }
      data-compare-tile-template={ sceneB?.tileUrlTemplate ?? '' }
      data-attribution={ scene?.attribution ?? '' }
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
  externalProvider: 'eos',
  externalFieldId: 'eos-field-1',
  providerSyncStatus: 'synced',
  providerSyncedAt: '2026-06-03T00:00:00Z',
};

function makeFieldScenes(overrides: Partial<FieldSceneListResponse> = {}): FieldSceneListResponse {
  return {
    plotId: 'plot-1',
    provider: 'eos',
    scope: 'field',
    sourceId: 'sentinel-2-l2a',
    defaultDisplayMode: 'RGB',
    displayModes: ['RGB', 'NDVI'],
    scenes: [
      {
        sceneToken: 'field-scene-a',
        acquisitionDate: '2026-06-01',
        datetime: '2026-06-01T00:00:00Z',
        sensor: 'S2',
        cloudPercent: 5,
        usablePixelPercent: 95,
        cloudMaskedPercent: 5,
        coveragePercent: 100,
        bounds: [77, 12, 77.1, 12.1],
        tileAvailable: true,
        metricsProvisional: false,
        sceneCount: 1,
        layers: [
          {
            displayMode: 'RGB',
            label: 'True colour',
            kind: 'rgb',
            tileUrlTemplate:
              '/api/tiles/fields/plot-1/field-scene-a/RGB/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
            available: true,
            attribution: 'EOSDA API Connect',
          },
          {
            displayMode: 'NDVI',
            label: 'NDVI',
            kind: 'index',
            tileUrlTemplate:
              '/api/tiles/fields/plot-1/field-scene-a/NDVI/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
            available: true,
            attribution: 'EOSDA API Connect',
          },
        ],
      },
      {
        sceneToken: 'field-scene-b',
        acquisitionDate: '2026-05-20',
        datetime: '2026-05-20T00:00:00Z',
        sensor: 'S2',
        cloudPercent: 12,
        usablePixelPercent: 88,
        cloudMaskedPercent: 12,
        coveragePercent: 100,
        tileAvailable: true,
        metricsProvisional: false,
        sceneCount: 1,
        layers: [
          {
            displayMode: 'RGB',
            label: 'True colour',
            kind: 'rgb',
            tileUrlTemplate:
              '/api/tiles/fields/plot-1/field-scene-b/RGB/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
            available: true,
            attribution: 'EOSDA API Connect',
          },
          {
            displayMode: 'NDVI',
            label: 'NDVI',
            kind: 'index',
            tileUrlTemplate:
              '/api/tiles/fields/plot-1/field-scene-b/NDVI/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
            available: true,
            attribution: 'EOSDA API Connect',
          },
        ],
      },
    ],
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
});

function stubAkashaFetch({
  sentinel2Dates = [makeDate('2026-04-27', { isLatestUsable: true })],
  sentinel1Dates = [
    makeDate('2026-04-26', {
      usablePixelPercent: null,
      cloudMaskedPercent: null,
      coveragePercent: null,
      isLatestUsable: true,
    }),
  ],
  plots = [],
  fieldScenes,
}: {
  sentinel2Dates?: SceneDate[];
  sentinel1Dates?: SceneDate[];
  plots?: Plot[];
  fieldScenes?: FieldSceneListResponse;
} = {}) {
  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
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
            maxPolygonAreaHa: 100,
            maxPolygonVertices: 40,
            usablePixelThresholdPercent: 70,
            supportedIndices: ['NDVI'],
            defaultIndex: 'NDVI',
          }),
        );
      }

      if (path === '/api/sources') {
        return Promise.resolve(
          jsonResponse([
            {
              id: 'sentinel-2-l2a',
              label: 'Sentinel-2 L2A',
              provider: 'Copernicus',
              kind: 'optical',
              supportedIndices: ['NDVI'],
              displayModes: ['RGB'],
              defaultDisplayMode: 'RGB',
              attribution: 'Copernicus Sentinel-2',
            },
            {
              id: 'sentinel-1-grd',
              label: 'Sentinel-1 GRD',
              provider: 'Copernicus',
              kind: 'sar',
              supportedIndices: [],
              displayModes: ['VV_GRAYSCALE'],
              defaultDisplayMode: 'VV_GRAYSCALE',
              description: 'VV grayscale radar backscatter.',
              attribution: 'Copernicus Sentinel-1',
            },
          ]),
        );
      }

      if (path === '/api/layers/default') {
        return Promise.resolve(
          jsonResponse({
            sourceId: 'sentinel-2-l2a',
            acquisitionDate: '2026-04-27',
            displayMode: 'RGB',
            tileUrlTemplate: '/api/tiles/sentinel-2-l2a/2026-04-27/RGB/{z}/{x}/{y}.png',
            minzoom: 0,
            maxzoom: 14,
            attribution: 'Copernicus Sentinel-2',
            usablePixelPercent: 90,
            metricsProvisional: false,
          }),
        );
      }

      if (path === '/api/plots') {
        return Promise.resolve(jsonResponse(plots));
      }

      if (path.startsWith('/api/fields/plot-1/scenes')) {
        return Promise.resolve(
          jsonResponse(
            fieldScenes ?? {
              plotId: 'plot-1',
              provider: 'native',
              scope: 'global_fallback',
              sourceId: 'sentinel-2-l2a',
              defaultDisplayMode: 'RGB',
              displayModes: ['RGB'],
              scenes: [],
              fallbackReason: 'Selected field is not synced to the configured provider.',
            },
          ),
        );
      }

      if (path === '/api/fields/plot-1/providers/eos/sync') {
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            provider: 'eos',
            syncStatus: 'synced',
            syncedAt: '2026-06-03T00:00:00Z',
            field: {
              plotId: 'plot-1',
              provider: 'eos',
              externalFieldId: 'eos-field-1',
              syncStatus: 'synced',
              syncedAt: '2026-06-03T00:00:00Z',
            },
          }),
        );
      }

      if (path === '/api/sources/sentinel-2-l2a/dates') {
        return Promise.resolve(jsonResponse(sentinel2Dates));
      }

      if (path === '/api/sources/sentinel-1-grd/dates') {
        return Promise.resolve(jsonResponse(sentinel1Dates));
      }

      throw new Error(`Unexpected request: ${path}`);
    }),
  );
}

describe('MapPage Sentinel-1 source behavior', () => {
  it('shows SAR notes and hides optical index controls after Sentinel-1 selection', async () => {
    stubAkashaFetch();

    renderMapPage();

    await screen.findByTestId('index-panel');

    // Open the Layers surface, then switch to the Sentinel-1 (SAR) source.
    fireEvent.click(screen.getByTestId('layers-toggle'));
    fireEvent.click(await screen.findByTestId('source-tab-sentinel-1-grd'));

    await screen.findByText('Radar layer · cloud-penetrating · not true colour');
    expect(screen.queryByTestId('index-panel')).toBeNull();

    // The nearest-pass note and SAR tile template depend on the Sentinel-1
    // dates query resolving, so wait for them.
    const note = await screen.findByTestId('nearest-pass-note');
    expect(note.textContent).toContain('Nearest radar pass: 2026-04-26.');
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('attribution').textContent).toContain('Copernicus Sentinel-1');
    });
  });

  it('does not render the compare scene while satellite imagery is hidden', async () => {
    stubAkashaFetch({
      sentinel2Dates: [
        makeDate('2026-04-20'),
        makeDate('2026-04-27', { isLatestUsable: true }),
      ],
    });

    renderMapPage({
      visible: false,
      compareEnabled: true,
      compareDate: '2026-04-20',
    });

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/sentinel-2-l2a/2026-04-27/RGB/{z}/{x}/{y}.png',
      );
    });
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-visible')).toBe('false');
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toBe(
      '',
    );
  });

  it('clears the stale compare scene when switching imagery sources', async () => {
    stubAkashaFetch({
      sentinel2Dates: [
        makeDate('2026-04-20'),
        makeDate('2026-04-27', { isLatestUsable: true }),
      ],
    });

    renderMapPage({
      compareEnabled: true,
      compareDate: '2026-04-20',
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template'),
      ).toContain('/api/tiles/sentinel-2-l2a/2026-04-20/RGB/{z}/{x}/{y}.png');
    });

    fireEvent.click(screen.getByTestId('layers-toggle'));
    fireEvent.click(await screen.findByTestId('source-tab-sentinel-1-grd'));

    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-compare-tile-template')).toBe(
      '',
    );
  });
});

describe('MapPage field-aware scene behavior', () => {
  it('uses field scenes when a synced field is selected and keeps RGB as the default', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT], fieldScenes: makeFieldScenes() });

    renderMapPage({ selectedPlotId: 'plot-1' });

    await screen.findByTestId('field-scene-status');
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/fields/plot-1/field-scene-a/RGB/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
      );
    });
    expect(screen.getByTestId('timeline-bar').textContent).toContain('Jun');
    expect(screen.queryByTestId('map-legend')).toBeNull();
  });

  it('switches field display modes and applies cloud mask query params', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT], fieldScenes: makeFieldScenes() });

    renderMapPage({ selectedPlotId: 'plot-1' });

    fireEvent.click(await screen.findByTestId('display-mode-NDVI'));
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/fields/plot-1/field-scene-a/NDVI/{z}/{x}/{y}.png?clouds=true&cloudShadows=true&cirrus=true',
      );
    });

    fireEvent.click(screen.getByTestId('cloud-mask-cloudShadows'));
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        'clouds=true&cloudShadows=false&cirrus=true',
      );
    });
    expect(screen.getByTestId('map-legend').getAttribute('data-display-mode')).toBe('NDVI');
  });

  it('shows sync and download affordances for an unsynced selected field without replacing global imagery', async () => {
    const unsynced = {
      ...FIELD_PLOT,
      externalProvider: null,
      externalFieldId: null,
      providerSyncStatus: 'not_synced' as const,
    };
    const fetchSpy = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === '/api/fields/plot-1/providers/eos/sync') {
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            provider: 'eos',
            syncStatus: 'synced',
            syncedAt: '2026-06-03T00:00:00Z',
          }),
        );
      }
      return (globalThis.fetch as unknown as typeof fetch)(input);
    });
    stubAkashaFetch({ plots: [unsynced] });
    const baseFetch = globalThis.fetch;
    vi.stubGlobal('fetch', (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === '/api/fields/plot-1/providers/eos/sync') return fetchSpy(input);
      return baseFetch(input);
    });

    renderMapPage({ selectedPlotId: 'plot-1' });

    await screen.findByTestId('field-sync-button');
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/sentinel-2-l2a/2026-04-27/RGB/{z}/{x}/{y}.png',
      );
    });

    fireEvent.click(screen.getByTestId('download-menu-toggle'));
    expect((await screen.findByTestId('download-index-tiff') as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.click(screen.getByTestId('field-sync-button'));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
  });

  it('toggles the field legend without changing the selected tile', async () => {
    stubAkashaFetch({ plots: [FIELD_PLOT], fieldScenes: makeFieldScenes() });

    renderMapPage({ selectedPlotId: 'plot-1', displayMode: 'NDVI' });

    await screen.findByTestId('map-legend');
    await waitFor(() => {
      expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
        '/api/tiles/fields/plot-1/field-scene-a/NDVI/',
      );
    });
    const before = screen.getByTestId('map-layer-manager').getAttribute('data-tile-template');
    fireEvent.click(screen.getByTestId('legend-toggle-btn'));
    expect(screen.queryByTestId('map-legend')).toBeNull();
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toBe(before);
  });
});
