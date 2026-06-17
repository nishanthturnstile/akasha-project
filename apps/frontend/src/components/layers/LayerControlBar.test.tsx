import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlBar } from '@/components/layers/LayerControlBar';
import { TooltipProvider } from '@/components/ui/tooltip';
import type { CloudMaskOptions, Plot, SceneDate, Source } from '@/types/api';

const sources: Source[] = [
    {
        id: 'resourcesat-2a-liss3-boa',
        label: 'ResourceSat-2A LISS-3 BOA',
        provider: 'ISRO/NRSC Bhoonidhi',
        kind: 'optical',
        displayModes: ['FCC', 'NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        defaultDisplayMode: 'FCC',
        mapDisplayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        defaultMapDisplayMode: 'NDVI',
        supportedIndices: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        availableMaskOptions: ['clouds', 'cloudShadows'],
        metricsProvisional: true,
    },
    {
        id: 'eos-04-sar-mrs-l2b',
        label: 'EOS-04 SAR MRS L2B',
        provider: 'ISRO/NRSC Bhoonidhi',
        kind: 'sar',
        displayModes: ['VV_GRAYSCALE'],
        defaultDisplayMode: 'VV_GRAYSCALE',
        supportedIndices: [],
    },
];

const plot: Plot = {
    id: 'plot-1',
    name: 'Test field',
    geometry: {
        type: 'Polygon',
        coordinates: [
            [
                [77.5, 12.9],
                [77.6, 12.9],
                [77.6, 13.0],
                [77.5, 13.0],
                [77.5, 12.9],
            ],
        ],
    },
    areaHa: 4.5,
    createdAt: null,
    updatedAt: null,
};

const cloudMask: CloudMaskOptions = { clouds: true, cloudShadows: true, cirrus: false };

const comparableDates: SceneDate[] = [
    {
        acquisitionDate: '2026-04-20',
        datetime: '2026-04-20T00:00:00Z',
        usablePixelPercent: 85,
        cloudMaskedPercent: 10,
        coveragePercent: 100,
        isLatestUsable: false,
        metricsProvisional: false,
        tileAvailable: true,
    },
    {
        acquisitionDate: '2026-04-27',
        datetime: '2026-04-27T00:00:00Z',
        usablePixelPercent: 90,
        cloudMaskedPercent: 5,
        coveragePercent: 100,
        isLatestUsable: true,
        metricsProvisional: false,
        tileAvailable: true,
    },
];

function renderBar(ui: ReactElement) {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return render(
        <QueryClientProvider client={ queryClient }>
            <TooltipProvider>{ ui }</TooltipProvider>
        </QueryClientProvider>,
    );
}

function baseProps(overrides: Partial<Parameters<typeof LayerControlBar>[0]> = {}) {
    return {
        sources,
        activeSourceId: 'resourcesat-2a-liss3-boa',
        onSelectSource: vi.fn(),
        displayModes: ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'],
        displayMode: 'NDVI',
        onDisplayModeChange: vi.fn(),
        cloudMask,
        onCloudMaskChange: vi.fn(),
        compareEnabled: false,
        onCompareEnabledChange: vi.fn(),
        comparableDates,
        activeDate: '2026-04-27',
        compareDate: null,
        onCompareDateChange: vi.fn(),
        blend: 50,
        onBlendChange: vi.fn(),
        selectedPlot: plot,
        selectedDate: '2026-04-27',
        exportSourceId: 'resourcesat-2a-liss3-boa',
        exportIndexType: 'NDVI',
        collapsed: false,
        onCollapsedChange: vi.fn(),
        ...overrides,
    } satisfies Parameters<typeof LayerControlBar>[0];
}

describe('LayerControlBar', () => {
    it('renders the expand-only affordance when collapsed', () => {
        const props = baseProps({ collapsed: true });
        renderBar(<LayerControlBar { ...props } />);

        const bar = screen.getByTestId('layer-control-bar');
        expect(bar.getAttribute('data-collapsed')).toBe('true');
        expect(screen.getByTestId('layer-bar-expand')).toBeTruthy();
        expect(screen.queryByTestId('layer-source-trigger')).toBeNull();

        fireEvent.click(screen.getByTestId('layer-bar-expand'));
        expect(props.onCollapsedChange).toHaveBeenCalledWith(false);
    });

    it('renders source / layer / cloud-mask / collapse triggers when expanded', () => {
        renderBar(<LayerControlBar { ...baseProps() } />);

        const bar = screen.getByTestId('layer-control-bar');
        expect(bar.getAttribute('data-collapsed')).toBe('false');

        expect(screen.getByTestId('layer-source-trigger').textContent).toContain(
            'ResourceSat-2A LISS-3 BOA',
        );
        expect(screen.getByTestId('layer-display-trigger').textContent).toContain('NDVI');
        expect(screen.getByTestId('layer-cloud-mask-trigger')).toBeTruthy();
        expect(screen.getByTestId('layer-bar-cluster')).toBeTruthy();
        expect(screen.getByTestId('layer-bar-collapse')).toBeTruthy();
    });

    it('opens the source popover and forwards selections to onSelectSource', () => {
        const props = baseProps();
        renderBar(<LayerControlBar { ...props } />);

        fireEvent.click(screen.getByTestId('layer-source-trigger'));
        // SourceSelector renders one tab per source inside the popover.
        const sarTab = screen.getByTestId('source-tab-eos-04-sar-mrs-l2b');
        fireEvent.click(sarTab);
        expect(props.onSelectSource).toHaveBeenCalledWith('eos-04-sar-mrs-l2b');
    });

    it('collapses the bar via the explicit collapse trigger', () => {
        const props = baseProps();
        renderBar(<LayerControlBar { ...props } />);

        fireEvent.click(screen.getByTestId('layer-bar-collapse'));
        expect(props.onCollapsedChange).toHaveBeenCalledWith(true);
    });

    it('disables the Layer popover when only a single display mode is available', () => {
        renderBar(
            <LayerControlBar
                { ...baseProps({ displayModes: ['VV_GRAYSCALE'], displayMode: 'VV_GRAYSCALE' }) }
            />,
        );

        const layerTrigger = screen.getByTestId('layer-display-trigger') as HTMLButtonElement;
        expect(layerTrigger.disabled).toBe(true);
    });

    it('hides unsupported cirrus masking for ResourceSat sources', () => {
        renderBar(
            <LayerControlBar
                { ...baseProps({
                    activeSourceId: 'resourcesat-2a-liss3-boa',
                    displayModes: ['NDVI'],
                    displayMode: 'NDVI',
                    exportSourceId: 'resourcesat-2a-liss3-boa',
                    exportCloudMask: { clouds: true, cloudShadows: true, cirrus: false },
                }) }
            />,
        );

        fireEvent.click(screen.getByTestId('layer-cloud-mask-trigger'));

        expect(screen.getByText('Provisional mask')).toBeTruthy();
        expect(screen.getByTestId('cloud-mask-clouds')).toBeTruthy();
        expect(screen.getByTestId('cloud-mask-cloudShadows')).toBeTruthy();
        expect(screen.queryByTestId('cloud-mask-cirrus')).toBeNull();
    });

    it('hides compare controls when the active mode is field-overlay only', () => {
        renderBar(
            <LayerControlBar
                { ...baseProps({
                    compareAvailable: false,
                }) }
            />,
        );

        expect(screen.queryByTestId('compare-control')).toBeNull();
    });
});
