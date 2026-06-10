import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AllFieldsPanel } from '@/components/fields/AllFieldsPanel';
import type { Plot, PlotGeometry } from '@/types/api';

const geometry: PlotGeometry = {
  type: 'Polygon',
  coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12.01], [77, 12]]],
};

const plots: Plot[] = [
  {
    id: 'plot-1',
    name: 'North field',
    geometry,
    areaHa: 12.345,
    createdAt: null,
    updatedAt: null,
    cropType: 'Paddy',
    groupName: 'Farm A',
    status: 'active',
  },
  {
    id: 'plot-2',
    name: 'South field',
    geometry,
    areaHa: 4,
    createdAt: null,
    updatedAt: null,
    cropType: 'Tomato',
  },
];

describe('AllFieldsPanel', () => {
  it('renders field cards, filters search, and emits selection/focus actions', () => {
    const onSelect = vi.fn();
    const onFocus = vi.fn();

    render(
      <AllFieldsPanel
        plots={ plots }
        selectedPlotId="plot-1"
        onSelect={ onSelect }
        onFocus={ onFocus }
      />,
    );

    expect(screen.getByText('North field')).toBeTruthy();
    expect(screen.getByText('12.35 ha')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();

    fireEvent.change(screen.getByTestId('all-fields-search'), { target: { value: 'tomato' } });
    expect(screen.queryByText('North field')).toBeNull();
    expect(screen.getByText('South field')).toBeTruthy();

    fireEvent.click(screen.getByTestId('field-card-focus-plot-2'));
    expect(onSelect).toHaveBeenCalledWith(plots[1]);
    expect(onFocus).toHaveBeenCalledWith(plots[1]);
  });

  it('renders loading, empty, and error states', () => {
    const { rerender } = render(<AllFieldsPanel isLoading />);
    expect(screen.getByTestId('all-fields-loading')).toBeTruthy();

    rerender(<AllFieldsPanel plots={ [] } />);
    expect(screen.getByTestId('all-fields-empty')).toBeTruthy();

    rerender(<AllFieldsPanel error="No field service" onRetry={ vi.fn() } />);
    expect(screen.getByTestId('all-fields-error').textContent).toContain('No field service');
  });
});
