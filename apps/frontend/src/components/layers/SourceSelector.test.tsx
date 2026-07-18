import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
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
    id: 'eos-04-sar-mrs-l2b',
    label: 'EOS-04 SAR MRS L2B',
    provider: 'ISRO/NRSC Bhoonidhi',
    kind: 'sar',
    productRole: 'support',
    supportedIndices: [],
    displayModes: ['VV_GRAYSCALE'],
    defaultDisplayMode: 'VV_GRAYSCALE',
  },
];

describe('SourceSelector', () => {
  it('keeps support-only SAR out of the primary imagery tabs', () => {
    const { queryByTestId } = render(
      <SourceSelector sources={sources} value="resourcesat-2a-liss3-boa" onChange={vi.fn()} />,
    );

    expect(queryByTestId('source-tab-eos-04-sar-mrs-l2b')).toBeNull();
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
