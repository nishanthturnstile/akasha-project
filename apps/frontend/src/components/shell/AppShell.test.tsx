import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import { AppShell } from '@/components/shell/AppShell';

// Stub the map renderer so tests don't load the real maplibre-gl/Esri WebGL
// stack (unsupported in jsdom; named-imports from the CJS maplibre-gl module).
vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: () => null,
}));

type TeamRole = 'owner' | 'admin' | 'member' | 'viewer';

function renderShell(path = '/weather/forecast', role: TeamRole = 'owner') {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const requestPath = String(input);
      if (requestPath === '/api/account/me') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            user: { id: 'u1', username: 'dev', email: 'dev@example.test', displayName: 'Dev' },
            currentTeam: { id: 't1', name: 'Team', role },
            memberships: [{ teamId: 't1', teamName: 'Team', role }],
            authMode: 'enabled',
          }),
        });
      }
      if (requestPath === '/api/seasons' || requestPath === '/api/fields') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => [],
        });
      }
      return Promise.resolve({
        ok: false,
        status: 500,
        json: async () => ({
          error: {
            code: 'UNEXPECTED_TEST_REQUEST',
            message: `Unexpected shell test fetch: ${requestPath}`,
            details: {},
          },
        }),
      });
    }),
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <MapViewProvider>
      <QueryClientProvider client={ queryClient }>
        <MemoryRouter initialEntries={ [path] }>
          <Routes>
            <Route element={ <AppShell /> }>
              <Route path="weather/forecast" element={ <div data-testid="forecast-page">Forecast</div> } />
              <Route
                path="monitoring/field-analytics"
                element={ <div data-testid="field-analytics-page">Field analytics</div> }
              />
              <Route
                path="admin/ingestion/jobs"
                element={ <div data-testid="admin-ingestion-jobs-page">Ingestion jobs</div> }
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MapViewProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AppShell', () => {
  it('renders persistent product navigation and outlet content', () => {
    renderShell();

    expect(screen.getByTestId('product-shell')).toBeTruthy();
    expect(screen.getByTestId('forecast-page')).toBeTruthy();
    expect(screen.getByTestId('nav-link-forecast').getAttribute('aria-current')).toBe('page');
  });

  it('keeps non-active nav groups collapsed until expanded', () => {
    renderShell();

    // Monitoring group is collapsed by default because the active route is in Weather.
    expect(screen.queryByTestId('nav-link-field-analytics')).toBeNull();

    fireEvent.click(screen.getByTestId('nav-group-toggle-monitoring'));

    expect(screen.getByTestId('nav-link-field-analytics')).toBeTruthy();
  });

  it('highlights the selected monitoring route', () => {
    renderShell('/monitoring/field-analytics');

    expect(screen.getByTestId('field-analytics-page')).toBeTruthy();
    expect(screen.getByTestId('nav-link-field-analytics').getAttribute('aria-current')).toBe(
      'page',
    );
  });

  it.each(['owner', 'admin'] as const)(
    'shows admin navigation in the desktop rail and mobile nav for %s users',
    async (role) => {
      renderShell('/admin/ingestion/jobs', role);

      expect(screen.getByTestId('admin-ingestion-jobs-page')).toBeTruthy();
      await waitFor(() =>
        expect(screen.getByTestId('nav-link-satellite-ingestion').getAttribute('aria-current'))
          .toBe('page'),
      );
      expect(screen.getByTestId('nav-group-toggle-operations-admin')).toBeTruthy();
      expect(screen.getByTestId('mobile-nav-link-satellite-ingestion')).toBeTruthy();
      expect(screen.queryByRole('heading', { name: 'Global View' })).toBeNull();
    },
  );

  it('keeps the product Global View panel out of admin ingestion routes', async () => {
    renderShell('/admin/ingestion/jobs', 'owner');

    expect(screen.getByTestId('admin-ingestion-jobs-page')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Team')).toBeTruthy());
    expect(screen.queryByRole('heading', { name: 'Global View' })).toBeNull();
    expect(screen.queryByPlaceholderText('Search fields, seasons…')).toBeNull();
  });

  it.each(['member', 'viewer'] as const)(
    'hides admin navigation from the desktop rail and mobile nav for %s users',
    async (role) => {
      renderShell('/weather/forecast', role);

      expect(screen.getByTestId('forecast-page')).toBeTruthy();
      await waitFor(() => expect(screen.getByText('Team')).toBeTruthy());
      expect(screen.queryByTestId('nav-group-toggle-operations-admin')).toBeNull();
      expect(screen.queryByTestId('nav-link-satellite-ingestion')).toBeNull();
      expect(screen.queryByTestId('mobile-nav-link-satellite-ingestion')).toBeNull();
    },
  );

  it('exposes sign out in the mobile account menu', async () => {
    renderShell('/weather/forecast');

    await waitFor(() => expect(screen.getByText('Team')).toBeTruthy());
    fireEvent.click(screen.getByTestId('mobile-account-menu-trigger'));

    expect(screen.getByTestId('mobile-sign-out-action')).toBeTruthy();
  });

  it.each(['member', 'viewer'] as const)(
    'keeps ingestion overview out of the product Monitoring navigation for %s users',
    async (role) => {
      renderShell('/weather/forecast', role);

      await waitFor(() => expect(screen.getByText('Team')).toBeTruthy());
      fireEvent.click(screen.getByTestId('nav-group-toggle-monitoring'));

      expect(screen.getByTestId('nav-link-field-analytics')).toBeTruthy();
      expect(screen.queryByTestId('nav-link-satellite-ingestion')).toBeNull();
      expect(screen.queryByTestId('mobile-nav-link-satellite-ingestion')).toBeNull();
    },
  );
});
