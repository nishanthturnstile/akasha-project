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

    it('labels an enabled Landsat source as optical with its provider', () => {
        const source: Source = {
            id: 'landsat-c2-l2',
            label: 'Landsat 8/9 Collection 2 Level 2',
            provider: 'USGS via Microsoft Planetary Computer',
            kind: 'optical',
            analysisLevel: 'field',
            availabilityStatus: 'active',
            resolutionMeters: 30,
            supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
            displayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        };

        const { getByTestId } = render(<SourceMetadata source={ source } />);

        expect(getByTestId('source-meta-landsat-c2-l2').textContent).toContain(
            'Optical · USGS via Microsoft Planetary Computer',
        );
    });
});
