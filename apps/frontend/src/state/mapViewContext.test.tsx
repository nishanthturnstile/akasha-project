import { act, renderHook } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { describe, expect, it } from 'vitest';
import { MapViewProvider, useMapView } from '@/state/mapViewContext';

function wrapper({ children }: PropsWithChildren) {
  return <MapViewProvider>{ children }</MapViewProvider>;
}

describe('MapViewProvider selected field state', () => {
  it('sets and clears selectedPlotId independently of imagery source', () => {
    const { result } = renderHook(() => useMapView(), { wrapper });

    act(() => result.current.setSelectedPlotId('plot-1'));
    expect(result.current.selectedPlotId).toBe('plot-1');

    act(() => result.current.setSource('sentinel-1-grd'));
    expect(result.current.selectedPlotId).toBe('plot-1');

    act(() => result.current.clearSelectedPlot());
    expect(result.current.selectedPlotId).toBeNull();
  });
});
