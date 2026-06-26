import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SourceMetadata } from '@/components/layers/SourceMetadata';
import type { Source } from '@/types/api';

describe('SourceMetadata', () => {
    it('labels gated context sources distinctly from field analytics sources', () => {
        const source: Source = {
            id: 'eos-06-ocm-lac-ndvi-8day-360m',
            label: 'EOS-06 OCM-LAC NDVI 8-day 360m',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'context',
            analysisLevel: 'context',
            availabilityStatus: 'gated',
            supportedIndices: [],
            displayModes: ['NDVI_CONTEXT'],
        };

        const { getByTestId } = render(<SourceMetadata source={ source } />);

        expect(getByTestId('source-meta-eos-06-ocm-lac-ndvi-8day-360m').textContent).toContain(
            'Context gated',
        );
    });

    it('labels gated regional optical sources distinctly from field analytics sources', () => {
        const source: Source = {
            id: 'resourcesat-2a-awifs-boa',
            label: 'ResourceSat-2A AWiFS BOA',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'optical',
            analysisLevel: 'regional',
            availabilityStatus: 'gated',
            supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
            displayModes: ['FCC', 'NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        };

        const { getByTestId } = render(<SourceMetadata source={ source } />);

        expect(getByTestId('source-meta-resourcesat-2a-awifs-boa').textContent).toContain(
            'Regional gated',
        );
    });
});
