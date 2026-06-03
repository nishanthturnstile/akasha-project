import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ProductRoutes } from '@/routes/ProductRoutes';

vi.mock('@/pages/monitoring/FieldAnalyticsPage', () => ({
  default: () => <div data-testid="map-page">Map workspace</div>,
}));

function renderRoutes(path: string) {
  return render(
    <MemoryRouter initialEntries={ [path] }>
      <ProductRoutes />
    </MemoryRouter>,
  );
}

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
    renderRoutes('/vra/vegetation');

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'VRA Vegetation' })).toBeTruthy(),
    );
    expect(screen.getByTestId('module-placeholder')).toBeTruthy();
    expect(screen.queryByTestId('map-page')).toBeNull();
  });

  it('renders a not-found page for unknown product routes', () => {
    renderRoutes('/missing/module');

    expect(screen.getByRole('heading', { name: 'Route not found' })).toBeTruthy();
  });
});
