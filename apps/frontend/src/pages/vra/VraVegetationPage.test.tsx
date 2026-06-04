import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import VraVegetationPage from '@/pages/vra/VraVegetationPage';
import { MemoryRouter } from 'react-router-dom';
import { MapViewProvider, type MapViewState } from '@/state/mapViewContext';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

function renderPage(initialState?: Partial<MapViewState>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter>
        <MapViewProvider initialState={ initialState }>
          <VraVegetationPage />
        </MapViewProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('VraVegetationPage', () => {
  it('renders a selected-field requirement before requests can create maps', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])));
    renderPage();

    expect(screen.getByRole('heading', { name: 'VRA Vegetation' })).toBeTruthy();
    expect(screen.getByText(/Select a field/)).toBeTruthy();
  });

  it('creates a vegetation map and renders ready zones', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === '/api/plots') return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
      if (path === '/api/fields/plot-1/scenes?provider=auto') {
        return Promise.resolve(
          jsonResponse({
            scenes: [{ acquisitionDate: '2026-06-01', tileAvailable: true }],
          }),
        );
      }
      if (path === '/api/fields/plot-1/zoning/maps' && init?.method !== 'POST') {
        return Promise.resolve(jsonResponse({ maps: [] }));
      }
      if (path === '/api/fields/plot-1/zoning/vegetation') {
        return Promise.resolve(jsonResponse({ mapId: 'map-1', status: 'processing' }));
      }
      if (path === '/api/fields/plot-1/zoning/maps/map-1') {
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            mapId: 'map-1',
            provider: 'provider',
            status: 'ready',
            mapType: 'vegetation',
            indexType: 'NDVI',
            zones: [
              {
                zoneId: 'zone-1',
                color: '#22c55e',
                areaHa: 1.2,
                areaPercent: 24,
                clusterValue: 0.72,
              },
            ],
            metadata: { source: 'provider-adapter' },
          }),
        );
      }
      return Promise.resolve(jsonResponse({}));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Selected field: North Field')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Create vegetation zones' }));

    await waitFor(() => expect(screen.getByText('Status: ready')).toBeTruthy());
    expect(screen.getAllByText('zone-1').length).toBeGreaterThan(0);
    expect(screen.getByText('0.720')).toBeTruthy();
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('api-connect');
  });

  it('shows sanitized provider errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/plots') return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        if (path.includes('/scenes')) {
          return Promise.resolve(jsonResponse({ scenes: [{ acquisitionDate: '2026-06-01', tileAvailable: true }] }));
        }
        if (path.includes('/zoning/maps')) return Promise.resolve(jsonResponse({ maps: [] }));
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'FIELD_PROVIDER_NOT_SYNCED', message: 'Sync the selected field.' } },
            409,
          ),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Selected field: North Field')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Create vegetation zones' }));

    await waitFor(() =>
      expect(screen.getByText('Sync the selected field before creating a vegetation zoning map.')).toBeTruthy(),
    );
  });
});
