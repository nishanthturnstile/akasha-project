import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WeatherForecastPage from '@/pages/weather/WeatherForecastPage';
import { MemoryRouter } from 'react-router-dom';
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
      <MemoryRouter>
        <MapViewProvider initialState={ initialState }>
          <WeatherForecastPage />
        </MapViewProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WeatherForecastPage', () => {
  it('renders a field-required empty state without calling weather APIs', () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);
    renderPage();

    expect(screen.getByRole('heading', { name: 'Weather Forecast' })).toBeTruthy();
    expect(screen.getByText(/Select a field/)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/weather/forecast'),
      expect.anything(),
    );
  });

  it('renders forecast cards and timeline for a selected field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/plots') {
          return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        }
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            provider: 'eos',
            scope: 'field',
            startDate: '2026-06-01',
            endDate: '2026-06-07',
            cards: [
              { id: 'temperature', label: 'Temperature', value: 25, unit: 'C', summary: '25.0 C' },
              { id: 'precipitation', label: 'Precipitation', value: 3, unit: 'mm', summary: '3.0 mm' },
              { id: 'relativeHumidity', label: 'Relative humidity', value: 80, unit: '%', summary: '80.0 %' },
              { id: 'clouds', label: 'Clouds', value: 20, unit: '%', summary: '20.0 %' },
              { id: 'wind', label: 'Wind', value: 2, unit: 'm/s', summary: '2.0 m/s NE' },
            ],
            timeline: [
              {
                date: '2026-06-01',
                temperatureAvgC: 25,
                precipitationMm: 3,
                humidityPercent: 80,
                cloudinessPercent: 20,
                windMps: 2,
                windDirection: 'NE',
                conditions: 'Clear',
              },
            ],
            metadata: {},
          }),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Selected field: North Field')).toBeTruthy());
    expect(screen.getAllByText('25.0 C').length).toBeGreaterThan(0);
    expect(screen.getByText('Clear')).toBeTruthy();
  });

  it('renders provider-unavailable errors calmly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === '/api/plots') {
          return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        }
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'PROVIDER_UNAVAILABLE', message: 'Weather provider is unavailable.' } },
            503,
          ),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Weather provider is unavailable.')).toBeTruthy());
  });
});
