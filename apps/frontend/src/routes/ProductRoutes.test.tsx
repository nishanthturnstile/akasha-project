import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import { ProductRoutes } from '@/routes/ProductRoutes';

vi.mock('@/pages/monitoring/FieldAnalyticsPage', () => ({
  default: () => <div data-testid="map-page">Map workspace</div>,
}));

function renderRoutes(path: string) {
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

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy());
    expect(screen.getByTestId('nav-link-field-analytics').getAttribute('aria-current')).toBe(
      'page',
    );
  });

  it('keeps the legacy map route compatible', async () => {
    renderRoutes('/map');

    await waitFor(() => expect(screen.getByTestId('map-page')).toBeTruthy());
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

  it('renders real weather pages instead of placeholders', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );
    renderRoutes('/weather/forecast');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Weather Forecast' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.queryByTestId('module-placeholder')).toBeNull();
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

  it('renders the real VRA vegetation page instead of a placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );
    renderRoutes('/vra/vegetation');

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'VRA Vegetation' })).toBeTruthy(),
      { timeout: 8000 },
    );
    expect(screen.queryByTestId('module-placeholder')).toBeNull();
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
  });

  it('renders a not-found page for unknown product routes', () => {
    renderRoutes('/missing/module');

    expect(screen.getByRole('heading', { name: 'Route not found' })).toBeTruthy();
  });
});
