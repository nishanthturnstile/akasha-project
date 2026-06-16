import { act, renderHook } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { describe, expect, it } from 'vitest';
import { MapViewProvider } from '@/state/mapViewContext';
import { useMapView } from '@/state/useMapView';

function wrapper({ children }: PropsWithChildren) {
  return <MapViewProvider>{ children }</MapViewProvider>;
}

describe('MapViewProvider selected field state', () => {
  it('sets and clears selectedPlotId independently of imagery source', () => {
    const { result } = renderHook(() => useMapView(), { wrapper });

    act(() => result.current.setSelectedPlotId('plot-1'));
    expect(result.current.selectedPlotId).toBe('plot-1');

    act(() => result.current.setSource('eos-04-sar-mrs-l2b'));
    expect(result.current.selectedPlotId).toBe('plot-1');

    act(() => result.current.clearSelectedPlot());
    expect(result.current.selectedPlotId).toBeNull();
  });

  it('stores cloud mask and legend visibility as client view state', () => {
    const { result } = renderHook(() => useMapView(), { wrapper });

    act(() =>
      result.current.setCloudMask({
        clouds: true,
        cloudShadows: false,
        cirrus: true,
      }),
    );
    expect(result.current.cloudMask.cloudShadows).toBe(false);

    act(() => result.current.setLegendOpen(false));
    expect(result.current.legendOpen).toBe(false);
  });
});
