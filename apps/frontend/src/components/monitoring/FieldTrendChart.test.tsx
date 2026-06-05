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
});
