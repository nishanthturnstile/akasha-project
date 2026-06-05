import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WeatherSeriesChart } from '@/components/weather/WeatherSeriesChart';

describe('WeatherSeriesChart', () => {
  it('renders an accessible weather series chart', () => {
    render(
      <WeatherSeriesChart
        series={{
          id: 'dailyPrecipitation',
          label: 'Daily precipitation',
          unit: 'mm',
          available: true,
          points: [
            { date: '2026-06-01', value: 2 },
            { date: '2026-06-02', value: 5 },
          ],
        }}
      />,
    );

    expect(screen.getByRole('img', { name: 'Daily precipitation weather chart' })).toBeTruthy();
    expect(screen.getAllByText(/2026-06-01: 2.0 mm/).length).toBeGreaterThan(0);
  });

  it('renders unavailable copy when no values exist', () => {
    render(
      <WeatherSeriesChart
        series={{
          id: 'dailyTemperature',
          label: 'Daily temperature',
          unit: 'C',
          available: false,
          unavailableReason: 'No data.',
          points: [],
        }}
      />,
    );

    expect(screen.getByText('No data.')).toBeTruthy();
  });
});
