import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';

describe('FieldTrendChart', () => {
  it('renders an accessible SVG trend when mean values exist', () => {
    render(
      <FieldTrendChart
        indexType="NDVI"
        points={ [
          {
            acquisitionDate: '2026-05-20',
            mean: 0.5,
            min: 0.1,
            max: 0.7,
            stddev: 0.1,
            metricsProvisional: false,
          },
          {
            acquisitionDate: '2026-06-01',
            mean: 0.56,
            min: 0.2,
            max: 0.8,
            stddev: 0.12,
            metricsProvisional: false,
          },
        ] }
      />,
    );

    expect(screen.getByRole('img', { name: 'NDVI trend chart' })).toBeTruthy();
    expect(screen.getAllByText(/2026-06-01: 0.560/).length).toBeGreaterThan(0);
  });

  it('renders an empty state when no mean values are available', () => {
    render(
      <FieldTrendChart
        indexType="NDVI"
        points={ [
          {
            acquisitionDate: '2026-06-01',
            mean: null,
            min: null,
            max: null,
            stddev: null,
            metricsProvisional: true,
            unavailableReason: 'No valid pixels.',
          },
        ] }
      />,
    );

    expect(screen.getByTestId('field-trend-empty')).toBeTruthy();
  });

  it('pins the y-axis domain to [0, 1] for NDVI', () => {
    render(
      <FieldTrendChart
        indexType="NDVI"
        points={ [
          { acquisitionDate: '2026-05-20', mean: 0.5, min: 0.1, max: 0.7, stddev: 0.1, metricsProvisional: false },
          { acquisitionDate: '2026-06-01', mean: 0.56, min: 0.2, max: 0.8, stddev: 0.12, metricsProvisional: false },
        ] }
      />,
    );

    expect(screen.getByTestId('trend-y-max').textContent).toBe('1.00');
    expect(screen.getByTestId('trend-y-min').textContent).toBe('0.00');
  });

  it('uses auto-scale y-axis domain for non-NDVI indices', () => {
    render(
      <FieldTrendChart
        indexType="NDMI"
        points={ [
          { acquisitionDate: '2026-05-20', mean: -0.1, min: -0.2, max: 0.1, stddev: 0.05, metricsProvisional: false },
          { acquisitionDate: '2026-06-01', mean: 0.3, min: 0.1, max: 0.4, stddev: 0.06, metricsProvisional: false },
        ] }
      />,
    );

    // Auto-scale: max of data = 0.30, min of data = -0.10
    expect(screen.getByTestId('trend-y-max').textContent).toBe('0.30');
    expect(screen.getByTestId('trend-y-min').textContent).toBe('-0.10');
  });

  it('renders NDVI points with negative mean without dropping them from data', () => {
    render(
      <FieldTrendChart
        indexType="NDVI"
        points={ [
          { acquisitionDate: '2026-05-20', mean: -0.05, min: -0.1, max: 0.0, stddev: 0.02, metricsProvisional: false },
          { acquisitionDate: '2026-06-01', mean: 0.4, min: 0.2, max: 0.6, stddev: 0.08, metricsProvisional: false },
        ] }
      />,
    );

    expect(screen.getByRole('img', { name: 'NDVI trend chart' })).toBeTruthy();
    // Both data points appear in accessible summary text — none dropped.
    expect(screen.getAllByText(/2026-05-20: -0.050/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/2026-06-01: 0.400/).length).toBeGreaterThan(0);
    // Fixed domain labels remain [0, 1] regardless of out-of-range values.
    expect(screen.getByTestId('trend-y-max').textContent).toBe('1.00');
    expect(screen.getByTestId('trend-y-min').textContent).toBe('0.00');
  });
});
