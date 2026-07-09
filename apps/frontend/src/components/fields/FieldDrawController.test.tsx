import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FieldDrawController } from '@/components/fields/FieldDrawController';
import type { Plot } from '@/types/api';

const start = vi.fn();
const stop = vi.fn();
const clear = vi.fn();
const setMode = vi.fn();
const on = vi.fn();

vi.mock('terra-draw', () => ({
  TerraDraw: vi.fn().mockImplementation(() => ({
    addFeatures: vi.fn(() => []),
    clear,
    getSnapshot: vi.fn(() => []),
    getSnapshotFeature: vi.fn(),
    on,
    selectFeature: vi.fn(),
    setMode,
    start,
    stop,
  })),
  TerraDrawPolygonMode: vi.fn(),
  TerraDrawCircleMode: vi.fn(),
  TerraDrawFreehandLineStringMode: vi.fn(),
  TerraDrawSelectMode: vi.fn(),
}));

vi.mock('terra-draw-maplibre-gl-adapter', () => ({
  TerraDrawMapLibreGLAdapter: vi.fn(),
}));

const map = {} as never;

const plot: Plot = {
  id: 'plot-1',
  name: 'North field',
  geometry: {
    type: 'Polygon',
    coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12.01], [77, 12]]],
  },
  areaHa: 1,
  createdAt: null,
  updatedAt: null,
};

describe('FieldDrawController map tool ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('stops its Terra Draw session when another map tool becomes active', async () => {
    const props = {
      activeTool: 'field-draw' as const,
      map,
      mode: 'draw' as const,
      selectedPlot: plot,
      onCancel: vi.fn(),
      onCreateField: vi.fn(),
      onUpdateField: vi.fn(),
      onReleaseTool: vi.fn(),
      onRequestTool: vi.fn(() => true),
    };

    const { rerender } = render(<FieldDrawController { ...props } />);

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(setMode).toHaveBeenCalledWith('polygon');

    rerender(<FieldDrawController { ...props } activeTool="measure" />);

    await waitFor(() => expect(stop).toHaveBeenCalledTimes(1));
    expect(clear).toHaveBeenCalled();
    expect(props.onReleaseTool).toHaveBeenCalledWith('field-draw');
  });

  it('keeps cleanup idempotent when Terra Draw has already stopped', async () => {
    const props = {
      activeTool: 'field-draw' as const,
      map,
      mode: 'draw' as const,
      selectedPlot: plot,
      onCancel: vi.fn(),
      onCreateField: vi.fn(),
      onUpdateField: vi.fn(),
      onReleaseTool: vi.fn(),
      onRequestTool: vi.fn(() => true),
    };

    const { rerender } = render(<FieldDrawController { ...props } />);

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    clear.mockImplementationOnce(() => {
      throw new Error('Terra Draw is not enabled');
    });

    expect(() => rerender(<FieldDrawController { ...props } activeTool="measure" />)).not.toThrow();

    await waitFor(() => expect(stop).toHaveBeenCalledTimes(1));
    expect(props.onReleaseTool).toHaveBeenCalledWith('field-draw');
  });

  it('requests field ownership before starting when measure currently owns the map', async () => {
    const props = {
      activeTool: 'measure' as const,
      map,
      mode: 'draw' as const,
      selectedPlot: plot,
      onCancel: vi.fn(),
      onCreateField: vi.fn(),
      onUpdateField: vi.fn(),
      onReleaseTool: vi.fn(),
      onRequestTool: vi.fn(() => true),
    };

    const { rerender } = render(<FieldDrawController { ...props } />);

    expect(props.onRequestTool).toHaveBeenCalledWith('field-draw');
    expect(start).not.toHaveBeenCalled();

    rerender(<FieldDrawController { ...props } activeTool="field-draw" />);

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(setMode).toHaveBeenCalledWith('polygon');
  });
});
