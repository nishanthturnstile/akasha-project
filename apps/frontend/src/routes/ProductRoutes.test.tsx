import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import { ProductRoutes } from '@/routes/ProductRoutes';

vi.mock('@/pages/monitoring/FieldAnalyticsPage', () => ({
  default: () => <div data-testid="map-page">Map workspace</div>,
}));

// Stub the map renderer so tests don't load the real maplibre-gl/Esri WebGL
// stack (unsupported in jsdom; named-imports from the CJS maplibre-gl module).
vi.mock('@/components/map/MapLayerManager', () => ({
  MapLayerManager: () => null,
}));

function renderRoutes(path: string) {
  if (!vi.isMockFunction(globalThis.fetch)) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          user: {
            id: 'u1',
            username: 'dev',
            email: 'dev@example.test',
            displayName: 'Dev',
            onboardingCompleted: true,
          },
          currentTeam: { id: 't1', name: 'Team', role: 'owner' },
          memberships: [{ teamId: 't1', teamName: 'Team', role: 'owner' }],
          authMode: 'enabled',
        }),
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
        </MapViewProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ProductRoutes', () => {
  it('redirects the root URL to the monitoring map workspace', async () => {
    renderRoutes('/');

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy(), { timeout: 8000 });
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

    renderRoutes('/monitoring/field-analytics');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy());
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

    renderRoutes('/signup');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Create account' })).toBeTruthy());
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

    renderRoutes('/monitoring/field-analytics');

    await waitFor(() =>
      expect(screen.getByText("Let's start with creating your first season")).toBeTruthy(),
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
