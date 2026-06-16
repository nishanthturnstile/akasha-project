import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { SourceSelector } from '@/components/layers/SourceSelector';
import type { Source } from '@/types/api';

const sources: Source[] = [
  {
    id: 'resourcesat-2a-liss3-boa',
    label: 'ResourceSat-2A LISS-3 BOA',
    provider: 'ISRO/NRSC Bhoonidhi',
    kind: 'optical',
    supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
    displayModes: ['FCC'],
    defaultDisplayMode: 'FCC',
  },
  {
    id: 'eos-06-ocm-lac-ndvi-8day-360m',
    label: 'EOS-06 OCM-LAC NDVI',
    provider: 'ISRO/NRSC Bhoonidhi',
    kind: 'context',
    supportedIndices: [],
    displayModes: ['NDVI_CONTEXT'],
    defaultDisplayMode: 'NDVI_CONTEXT',
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
      <SourceSelector sources={sources} value="resourcesat-2a-liss3-boa" onChange={vi.fn()} />,
    );

    expect(getByTestId('source-tab-sentinel-1-grd').textContent).toContain('Sentinel-1 GRD');
  });

  it('calls onChange when the Sentinel-1 tab is selected', () => {
    const onChange = vi.fn();
    const { getByTestId } = render(
      <SourceSelector sources={sources} value="resourcesat-2a-liss3-boa" onChange={onChange} />,
    );

    fireEvent.click(getByTestId('source-tab-sentinel-1-grd'));
    expect(onChange).toHaveBeenCalledWith('sentinel-1-grd');
  });

  it('labels context sources in the tab title', () => {
    const { getByTestId } = render(
      <SourceSelector sources={sources} value="resourcesat-2a-liss3-boa" onChange={vi.fn()} />,
    );

    expect(getByTestId('source-tab-eos-06-ocm-lac-ndvi-8day-360m').getAttribute('title')).toContain(
      'Context',
    );
  });
});
