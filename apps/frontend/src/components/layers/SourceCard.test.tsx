import { fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SourceCard } from '@/components/layers/SourceCard';
import type { Source } from '@/types/api';

const source: Source = {
    id: 'eos-06-ocm-lac-ndvi-8day-360m',
    label: 'EOS-06 OCM-LAC NDVI 8-day 360m',
    provider: 'ISRO/NRSC Bhoonidhi',
    kind: 'context',
    analysisLevel: 'context',
    availabilityStatus: 'gated',
    gatedReason: 'No validated EOS-06 NDVI context COG has been ingested.',
    supportedIndices: [],
    displayModes: ['NDVI_CONTEXT'],
    defaultDisplayMode: 'NDVI_CONTEXT',
    description: 'Gated coarse regional precomputed NDVI context source.',
    limitations: ['Precomputed NDVI only; not raw reflectance for plot statistics.'],
};

function renderCard(overrides: Partial<React.ComponentProps<typeof SourceCard>> = {}) {
    const props = {
        source,
        active: true,
        selectedDate: '2026-04-16',
        displayMode: 'NDVI_CONTEXT',
        visible: true,
        opacity: 70,
        onSelect: vi.fn(),
        onDisplayModeChange: vi.fn(),
        onVisibleChange: vi.fn(),
        onOpacityChange: vi.fn(),
        ...overrides,
    };
    return { props, ...render(<SourceCard { ...props } />) };
}

describe('SourceCard', () => {
    beforeEach(() => {
        class ResizeObserverMock {
            observe() {}
            unobserve() {}
            disconnect() {}
        }

        vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('surfaces source limitations for gated context sources', () => {
        const { getByTestId } = renderCard();

        expect(getByTestId('source-gated-note').textContent).toContain(
            'No validated EOS-06 NDVI context COG has been ingested.',
        );
        expect(getByTestId('source-limitations').textContent).toContain(
            'Precomputed NDVI only; not raw reflectance for plot statistics.',
        );
    });

    it('does not render expanded limitations while inactive', () => {
        const { queryByTestId } = renderCard({ active: false });

        expect(queryByTestId('source-limitations')).toBeNull();
    });

    it('forwards selection from the compact card button', () => {
        const { props, getByTestId } = renderCard({ active: false });

        fireEvent.click(getByTestId('source-tab-eos-06-ocm-lac-ndvi-8day-360m'));

        expect(props.onSelect).toHaveBeenCalledTimes(1);
    });
});
