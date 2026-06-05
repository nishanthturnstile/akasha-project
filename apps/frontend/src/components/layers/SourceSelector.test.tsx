import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { SourceSelector } from '@/components/layers/SourceSelector';
import type { Source } from '@/types/api';

const sources: Source[] = [
  {
    id: 'sentinel-2-l2a',
    label: 'Sentinel-2 L2A',
    provider: 'Copernicus',
    kind: 'optical',
    supportedIndices: ['NDVI'],
  },
  {
    id: 'sentinel-1-grd',
    label: 'Sentinel-1 GRD',
    provider: 'Copernicus',
    kind: 'sar',
    supportedIndices: [],
    displayModes: ['VV_GRAYSCALE'],
    defaultDisplayMode: 'VV_GRAYSCALE',
  },
];

describe('SourceSelector', () => {
  it('renders Sentinel-1 as a separate source tab', () => {
    const { getByTestId } = render(
      <SourceSelector sources={sources} value="sentinel-2-l2a" onChange={vi.fn()} />,
    );

    expect(getByTestId('source-tab-sentinel-1-grd').textContent).toContain('Sentinel-1 GRD');
  });

  it('calls onChange when the Sentinel-1 tab is selected', () => {
    const onChange = vi.fn();
    const { getByTestId } = render(
      <SourceSelector sources={sources} value="sentinel-2-l2a" onChange={onChange} />,
    );

    fireEvent.click(getByTestId('source-tab-sentinel-1-grd'));
    expect(onChange).toHaveBeenCalledWith('sentinel-1-grd');
  });
});
