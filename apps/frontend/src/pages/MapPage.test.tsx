import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import MapPage from '@/pages/MapPage';

vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: ({
    scene,
  }: {
    scene: { tileUrlTemplate?: string; attribution?: string } | null;
  }) => (
    <div
      data-testid="map-layer-manager"
      data-tile-template={scene?.tileUrlTemplate ?? ''}
      data-attribution={scene?.attribution ?? ''}
    />
  ),
}));

function renderMapPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MapPage />
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

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MapPage Sentinel-1 source behavior', () => {
  it('shows SAR notes and hides optical index controls after Sentinel-1 selection', async () => {
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

        if (path === '/api/sources/sentinel-2-l2a/dates') {
          return Promise.resolve(
            jsonResponse([
              {
                acquisitionDate: '2026-04-27',
                datetime: '2026-04-27T00:00:00Z',
                usablePixelPercent: 90,
                cloudMaskedPercent: 10,
                coveragePercent: 100,
                isLatestUsable: true,
                metricsProvisional: false,
                tileAvailable: true,
              },
            ]),
          );
        }

        if (path === '/api/sources/sentinel-1-grd/dates') {
          return Promise.resolve(
            jsonResponse([
              {
                acquisitionDate: '2026-04-26',
                datetime: '2026-04-26T00:00:00Z',
                usablePixelPercent: null,
                cloudMaskedPercent: null,
                coveragePercent: null,
                isLatestUsable: true,
                metricsProvisional: false,
                tileAvailable: true,
              },
            ]),
          );
        }

        throw new Error(`Unexpected request: ${path}`);
      }),
    );

    renderMapPage();

    await screen.findByTestId('index-panel');
    fireEvent.click(screen.getByTestId('source-tab-sentinel-1-grd'));

    await screen.findByText('Radar layer · cloud-penetrating · not true colour');
    expect(screen.queryByTestId('index-panel')).toBeNull();
    expect(screen.getByTestId('nearest-pass-note').textContent).toContain(
      'Nearest radar pass: 2026-04-26.',
    );
    expect(screen.getByTestId('map-layer-manager').getAttribute('data-tile-template')).toContain(
      '/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
    );

    await waitFor(() => {
      expect(screen.getByTestId('attribution').textContent).toContain('Copernicus Sentinel-1');
    });
  });
});
