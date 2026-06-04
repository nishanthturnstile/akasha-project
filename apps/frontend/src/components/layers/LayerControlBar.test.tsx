import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlBar } from '@/components/layers/LayerControlBar';
import { TooltipProvider } from '@/components/ui/tooltip';
import type { CloudMaskOptions, Plot, Source } from '@/types/api';

const sources: Source[] = [
    {
        id: 'sentinel-2-l2a',
        label: 'Sentinel-2 L2A',
        provider: 'Copernicus',
        kind: 'optical',
        supportedIndices: ['NDVI', 'NDRE', 'NDMI'],
    },
    {
        id: 'sentinel-1-grd',
        label: 'Sentinel-1 GRD',
        provider: 'Copernicus',
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

const cloudMask: CloudMaskOptions = { clouds: true, cloudShadows: true, cirrus: true };

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
        activeSourceId: 'sentinel-2-l2a',
        onSelectSource: vi.fn(),
        displayModes: ['RGB', 'NDVI', 'NDRE'],
        displayMode: 'RGB',
        onDisplayModeChange: vi.fn(),
        cloudMask,
        onCloudMaskChange: vi.fn(),
        compareEnabled: false,
        onCompareEnabledChange: vi.fn(),
        comparableDates: ['2026-04-27', '2026-04-20'],
        activeDate: '2026-04-27',
        compareDate: null,
        onCompareDateChange: vi.fn(),
        blend: 50,
        onBlendChange: vi.fn(),
        selectedPlot: plot,
        selectedDate: '2026-04-27',
        exportSourceId: 'sentinel-2-l2a',
        exportIndexType: 'NDVI',
        selectedScene: null,
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

        expect(screen.getByTestId('layer-source-trigger').textContent).toContain('Sentinel-2 L2A');
        expect(screen.getByTestId('layer-display-trigger').textContent).toContain('RGB');
        expect(screen.getByTestId('layer-cloud-mask-trigger')).toBeTruthy();
        expect(screen.getByTestId('layer-bar-cluster')).toBeTruthy();
        expect(screen.getByTestId('layer-bar-collapse')).toBeTruthy();
    });

    it('opens the source popover and forwards selections to onSelectSource', () => {
        const props = baseProps();
        renderBar(<LayerControlBar { ...props } />);

        fireEvent.click(screen.getByTestId('layer-source-trigger'));
        // SourceSelector renders one tab per source inside the popover.
        const sarTab = screen.getByTestId('source-tab-sentinel-1-grd');
        fireEvent.click(sarTab);
        expect(props.onSelectSource).toHaveBeenCalledWith('sentinel-1-grd');
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
});
