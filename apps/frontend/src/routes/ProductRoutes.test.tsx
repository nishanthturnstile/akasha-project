import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import { ProductRoutes } from '@/routes/ProductRoutes';

vi.mock('@/pages/monitoring/FieldAnalyticsPage', () => ({
  default: () => <div data-testid="map-page">Map workspace</div>,
}));

vi.mock('@/pages/monitoring/AdminIngestionSources', () => ({
  default: () => <div data-testid="admin-ingestion-sources-page">Satellite ingestion</div>,
}));

vi.mock('@/pages/monitoring/IngestionJobsList', () => ({
  default: () => <div data-testid="ingestion-jobs-list-page">Ingestion jobs</div>,
}));

vi.mock('@/pages/monitoring/IngestionJobDetail', () => ({
  default: () => <div data-testid="ingestion-job-detail-page">Ingestion job detail</div>,
}));

// Stub the map renderer so tests don't load the real maplibre-gl/Esri WebGL
// stack (unsupported in jsdom; named-imports from the CJS maplibre-gl module).
vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: () => null,
}));

function accountMeResponse(role: 'owner' | 'admin' | 'member' | 'viewer' = 'owner') {
  return {
    user: {
      id: 'u1',
      username: 'dev',
      email: 'dev@example.test',
      displayName: 'Dev',
      onboardingCompleted: true,
    },
    currentTeam: { id: 't1', name: 'Team', role },
    memberships: [{ teamId: 't1', teamName: 'Team', role }],
    authMode: 'enabled',
  };
}

function renderRoutes(
  path: string,
  role: 'owner' | 'admin' | 'member' | 'viewer' = 'owner',
  options: { preserveFetch?: boolean } = {},
) {
  if (!options.preserveFetch) {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const requestPath = String(input);
        if (requestPath === '/api/account/me') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => accountMeResponse(role),
          });
        }
        return Promise.resolve({
          ok: false,
          status: 500,
          json: async () => ({
            error: {
              code: 'UNEXPECTED_TEST_REQUEST',
              message: `Unexpected route test fetch: ${requestPath}`,
              details: {},
            },
          }),
        });
      }),
    );
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter initialEntries={ [path] }>
        <MapViewProvider>
          <ProductRoutes />
          <LocationProbe />
        </MapViewProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe" data-pathname={ location.pathname } />;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ProductRoutes', () => {
  it('redirects the root URL to the monitoring map workspace', async () => {
    renderRoutes('/');

    await waitFor(
      () =>
        expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
          '/monitoring/field-analytics',
        ),
      { timeout: 8000 },
    );
    expect(screen.getByTestId('nav-link-field-analytics').getAttribute('aria-current')).toBe(
      'page',
    );
  });

  it('redirects unauthenticated product routes to login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({
          error: { code: 'UNAUTHORIZED', message: 'Authentication required.', details: {} },
        }),
      }),
    );

    renderRoutes('/monitoring/field-analytics', 'owner', { preserveFetch: true });

    await waitFor(() =>
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe('/login'),
    );
  });

  it('renders the signup page for new users', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({
          error: { code: 'UNAUTHORIZED', message: 'Authentication required.', details: {} },
        }),
      }),
    );

    renderRoutes('/signup', 'owner', { preserveFetch: true });

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Create account' })).toBeTruthy(),
      { timeout: 8000 },
    );
  });

  it('redirects authenticated users away from signup', async () => {
    renderRoutes('/signup');

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), { timeout: 8000 });
  });

  it('redirects authenticated users without completed onboarding into onboarding', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          user: {
            id: 'u1',
            username: 'new@example.test',
            email: 'new@example.test',
            displayName: 'New User',
            onboardingCompleted: false,
          },
          currentTeam: { id: 't1', name: 'Team', role: 'owner' },
          memberships: [{ teamId: 't1', teamName: 'Team', role: 'owner' }],
          authMode: 'enabled',
        }),
      }),
    );

    renderRoutes('/monitoring/field-analytics', 'owner', { preserveFetch: true });

    await waitFor(
      () => expect(screen.getByText("Let's start with creating your first season")).toBeTruthy(),
      { timeout: 8000 },
    );
  });

  it('redirects users with completed onboarding away from onboarding routes', async () => {
    renderRoutes('/onboarding/step1');

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), { timeout: 8000 });
  });

  it('keeps the legacy map route compatible', async () => {
    renderRoutes('/map');

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), { timeout: 8000 });
  });

  it.each(['owner', 'admin'] as const)(
    'renders canonical satellite ingestion admin page for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion', role);

      await waitFor(
        () => expect(screen.getByTestId('admin-ingestion-sources-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['owner', 'admin'] as const)(
    'renders canonical admin ingestion jobs for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion/jobs', role);

      await waitFor(
        () => expect(screen.getByTestId('ingestion-jobs-list-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['owner', 'admin'] as const)(
    'redirects legacy admin ingestion schedules route to the satellite page for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion/schedules', role);

      await waitFor(
        () => expect(screen.getByTestId('admin-ingestion-sources-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/admin/ingestion',
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'does not render canonical admin ingestion overview for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('admin-ingestion-sources-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'does not render canonical admin ingestion jobs for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion/jobs', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('ingestion-jobs-list-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'does not render canonical admin ingestion schedules for %s users',
    async (role) => {
      renderRoutes('/admin/ingestion/schedules', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('admin-ingestion-sources-page')).toBeNull();
    },
  );

  // Deprecated compatibility aliases: temporary owner/admin-gated redirects only.
  // They must not reintroduce ingestion orchestration content under the product monitoring namespace.
  it.each(['owner', 'admin'] as const)(
    'redirects the deprecated global operator alias to the canonical satellite admin page for %s users',
    async (role) => {
      renderRoutes('/monitoring/global', role);

      await waitFor(
        () => expect(screen.getByTestId('admin-ingestion-sources-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/admin/ingestion',
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'keeps the deprecated global operator alias owner/admin-gated for %s users',
    async (role) => {
      renderRoutes('/monitoring/global', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('admin-ingestion-sources-page')).toBeNull();
    },
  );

  it.each(['owner', 'admin'] as const)(
    'redirects the deprecated ingestion jobs list alias to the canonical admin route for %s users',
    async (role) => {
      renderRoutes('/monitoring/ingestion-jobs', role);

      await waitFor(
        () => expect(screen.getByTestId('ingestion-jobs-list-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/admin/ingestion/jobs',
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'keeps the deprecated ingestion jobs list alias owner/admin-gated for %s users',
    async (role) => {
      renderRoutes('/monitoring/ingestion-jobs', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('ingestion-jobs-list-page')).toBeNull();
    },
  );

  it.each(['owner', 'admin'] as const)(
    'redirects the deprecated ingestion job detail alias to the canonical admin route for %s users',
    async (role) => {
      renderRoutes('/monitoring/ingestion-jobs/job-abc%20123', role);

      await waitFor(
        () => expect(screen.getByTestId('ingestion-job-detail-page')).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/admin/ingestion/jobs/job-abc%20123',
      );
      expect(screen.queryByTestId('map-page')).toBeNull();
    },
  );

  it.each(['member', 'viewer'] as const)(
    'keeps the deprecated ingestion job detail alias owner/admin-gated for %s users',
    async (role) => {
      renderRoutes('/monitoring/ingestion-jobs/job-abc%20123', role);

      await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), {
        timeout: 8000,
      });
      expect(screen.getByTestId('location-probe').getAttribute('data-pathname')).toBe(
        '/monitoring/field-analytics',
      );
      expect(screen.queryByTestId('ingestion-job-detail-page')).toBeNull();
    },
  );

  it('renders planned module placeholders without loading the map workspace', async () => {
    renderRoutes('/vra/sowing');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'VRA Sowing' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.getByTestId('module-placeholder')).toBeTruthy();
    expect(screen.queryByTestId('map-page')).toBeNull();
  });

  it('renders weather pages as planned native-module placeholders', async () => {
    renderRoutes('/weather/forecast');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Weather Forecast' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.getByTestId('module-placeholder')).toBeTruthy();
  });

  it('renders real report pages instead of placeholders', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );
    renderRoutes('/monitoring/field-leaderboard');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Field leaderboard' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.queryByTestId('module-placeholder')).toBeNull();
  });

  it('renders the real diseases and pests page instead of a placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );
    renderRoutes('/monitoring/diseases-pests');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Diseases & Pests' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.queryByTestId('module-placeholder')).toBeNull();
  });

  it('renders VRA vegetation as a planned native-module placeholder', async () => {
    renderRoutes('/vra/vegetation');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'VRA Vegetation' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.getByTestId('module-placeholder')).toBeTruthy();
  });

  it('renders real Phase 10 operations pages instead of placeholders', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );
    const cases = [
      { path: '/activity-log', heading: 'Field activity log' },
      { path: '/scout-tasks', heading: 'Scout tasks' },
      { path: '/data-manager/data', heading: 'Dataset uploads' },
      { path: '/data-manager/connections', heading: 'John Deere' },
      { path: '/field-manager/groups', heading: 'Field groups' },
    ];
    for (const item of cases) {
      const view = renderRoutes(item.path);
      await waitFor(
        () => expect(screen.getByRole('heading', { name: item.heading })).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.queryByTestId('module-placeholder')).toBeNull();
      view.unmount();
    }
  }, 30_000);

  it('renders real Phase 12 account pages instead of placeholders', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          user: {
            id: 'u1',
            email: 'dev@example.test',
            displayName: 'Dev',
            onboardingCompleted: true,
          },
          currentTeam: { id: 't1', name: 'Team', role: 'owner' },
          memberships: [],
          authMode: 'dev',
        }),
      }),
    );
    const cases = [
      { path: '/account/settings', heading: 'Account settings' },
      { path: '/account/api', heading: 'API settings' },
      { path: '/notifications', heading: 'Notifications' },
      { path: '/assistant', heading: 'AI assistant shell' },
    ];
    for (const item of cases) {
      const view = renderRoutes(item.path);
      await waitFor(
        () => expect(screen.getByRole('heading', { name: item.heading })).toBeTruthy(),
        { timeout: 8000 },
      );
      expect(screen.queryByTestId('module-placeholder')).toBeNull();
      view.unmount();
    }
  });

  it('renders a not-found page for unknown product routes', async () => {
    renderRoutes('/missing/module');

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Route not found' })).toBeTruthy(),
    );
  });
});
