import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WeatherAnalyticsPage from '@/pages/weather/WeatherAnalyticsPage';
import { MapViewProvider, type MapViewState } from '@/state/mapViewContext';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

function renderPage(initialState?: Partial<MapViewState>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MapViewProvider initialState={ initialState }>
        <WeatherAnalyticsPage />
      </MapViewProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WeatherAnalyticsPage', () => {
  it('renders a field-required empty state', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Weather Analytics' })).toBeTruthy();
    expect(screen.getByText(/Select a field/)).toBeTruthy();
  });

  it('renders weather series charts and unavailable soil moisture copy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/plots') {
          return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        }
        if (path.includes('/weather/soil-moisture')) {
          return Promise.resolve(
            jsonResponse({
              plotId: 'plot-1',
              provider: 'eos',
              scope: 'field',
              startDate: '2026-06-01',
              endDate: '2026-06-30',
              available: false,
              unavailableReason: 'Soil-moisture weather data is not available.',
              metadata: {},
            }),
          );
        }
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            provider: 'eos',
            scope: 'field',
            startDate: '2026-06-01',
            endDate: '2026-06-30',
            series: [
              {
                id: 'dailyPrecipitation',
                label: 'Daily precipitation',
                unit: 'mm',
                available: true,
                points: [{ date: '2026-06-01', value: 4 }],
              },
              {
                id: 'dailyTemperature',
                label: 'Daily temperature',
                unit: 'C',
                available: true,
                points: [{ date: '2026-06-01', value: 26 }],
              },
            ],
            metadata: {},
          }),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Selected field: North Field')).toBeTruthy());
    expect(screen.getAllByRole('img', { name: 'Daily precipitation weather chart' }).length).toBeGreaterThan(0);
    expect(screen.getByText('Soil-moisture weather data is not available.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Daily temperature' }));
    expect(screen.getByText('Latest value: 26.0 C')).toBeTruthy();
  });

  it('renders rate-limit errors without provider internals', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === '/api/plots') {
          return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        }
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'PROVIDER_RATE_LIMITED', message: 'EOS provider rate limit was reached.' } },
            429,
          ),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(
      () =>
        expect(
          screen.getAllByText('Weather provider rate limit was reached. Try again shortly.').length,
        ).toBeGreaterThan(0),
    );
  });
});
