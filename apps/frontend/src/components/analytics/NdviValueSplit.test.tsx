import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NdviValueSplit } from './NdviValueSplit';
import type { NdviValueSplit as NdviValueSplitData } from '@/types/api';

const VALUE_SPLIT: NdviValueSplitData = {
  indexType: 'NDVI',
  profileId: 'ndvi-density-v1',
  percentageBasis: 'classifiablePixels',
  thresholds: [0.2, 0.4, 0.6],
  totalPixels: 100,
  classifiablePixels: 95,
  noDataPixels: 5,
  unclassifiedPixels: 0,
  categories: [
    { id: 'denseVegetation', label: 'Dense vegetation', minInclusive: 0.6, maxExclusive: null, pixelCount: 40, percentage: 40 },
    { id: 'moderateVegetation', label: 'Moderate vegetation', minInclusive: 0.4, maxExclusive: 0.6, pixelCount: 30, percentage: 30 },
    { id: 'sparseVegetation', label: 'Sparse vegetation', minInclusive: 0.2, maxExclusive: 0.4, pixelCount: 15, percentage: 15 },
    { id: 'openSoil', label: 'Open soil', minInclusive: null, maxExclusive: 0.2, pixelCount: 5, percentage: 5 },
    { id: 'cloudiness', label: 'Cloudiness', minInclusive: null, maxExclusive: null, pixelCount: 5, percentage: 10 },
  ],
};

describe('NdviValueSplit', () => {
  it('renders the five backend-defined categories as one distribution', () => {
    render(<NdviValueSplit valueSplit={ VALUE_SPLIT } selectedDate="2026-07-31" />);

    expect(screen.getByText('NDVI values split')).toBeTruthy();
    expect(screen.getByTestId('ndvi-value-split-date').textContent).toBe("Date: 31 Jul'26");
    expect(screen.getByTestId('ndvi-value-split-bar').getAttribute('aria-label')).toContain(
      'Dense vegetation 40%',
    );
    expect(screen.getByTestId('ndvi-value-split-category-cloudiness').textContent).toBe(
      'Cloudiness',
    );
    expect(screen.getByTestId('ndvi-value-split-segment-openSoil').getAttribute('style')).toContain(
      'height: 3.9%',
    );
  });

  it('shows a bounded empty state when no category has pixels', () => {
    render(
      <NdviValueSplit
        valueSplit={ {
          ...VALUE_SPLIT,
          classifiablePixels: 0,
          categories: VALUE_SPLIT.categories.map((category) => ({ ...category, percentage: 0 })),
        } }
      />,
    );

    expect(screen.getByTestId('ndvi-value-split-empty')).toBeTruthy();
    expect(screen.queryByTestId('ndvi-value-split-bar')).toBeNull();
  });
});