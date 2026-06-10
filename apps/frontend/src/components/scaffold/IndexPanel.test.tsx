import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type React from 'react';
import { describe, expect, it } from 'vitest';

import { IndexPanel } from '@/components/scaffold/IndexPanel';
import type { CloudMaskOptions, Plot } from '@/types/api';

const cloudMask: CloudMaskOptions = {
    clouds: true,
    cloudShadows: true,
    cirrus: true,
};

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

function renderPanel(ui: React.ReactElement) {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return render(<QueryClientProvider client={ queryClient }>{ ui }</QueryClientProvider>);
}

// Radix Tabs switches the active value on mousedown (not click). Fire both
// for fidelity with real pointer interaction.
function activateTab(testId: string) {
    const trigger = screen.getByTestId(testId);
    fireEvent.mouseDown(trigger);
    fireEvent.click(trigger);
    return trigger;
}

describe('IndexPanel tabbed analytics (Phase F)', () => {
    it('renders the empty-state guidance when no field is selected', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ null }
                selectedDate="2026-04-27"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDRE', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        expect(screen.getByTestId('index-panel')).toBeTruthy();
        expect(screen.getByTestId('index-panel-no-field')).toBeTruthy();
        expect(screen.queryByTestId('index-panel-tabs')).toBeNull();
    });

    it('renders three tabs with Crop info active by default when a field is selected', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDRE', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        const tabs = screen.getByTestId('index-panel-tabs');
        expect(tabs).toBeTruthy();
        expect(screen.getByTestId('index-panel-tab-crop-info')).toBeTruthy();
        expect(screen.getByTestId('index-panel-tab-chart')).toBeTruthy();
        expect(screen.getByTestId('index-panel-tab-activities')).toBeTruthy();

        expect(screen.getByTestId('index-panel-tab-crop-info').getAttribute('data-state')).toBe(
            'active',
        );
        expect(screen.getByTestId('index-panel-content-crop-info')).toBeTruthy();

        // All six Crop info placeholder cards are present on the default tab.
        expect(screen.getByTestId('crop-info-card-crop-rotation')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-sown-area')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-management-guide')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-growth-stages')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-current-risks')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-ndvi-split')).toBeTruthy();
    });

    it('switches to the Chart tab and exposes the index selector and trend chart', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDRE', 'NDMI'] }
                cloudMask={ cloudMask }
                periodFrom="2026-03-01"
                periodTo="2026-04-27"
            />,
        );

        activateTab('index-panel-tab-chart');

        expect(screen.getByTestId('index-panel-tab-chart').getAttribute('data-state')).toBe('active');
        expect(screen.getByTestId('index-panel-content-chart')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-NDVI')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-NDRE')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-NDMI')).toBeTruthy();
        expect(screen.getByTestId('analytics-chart-section')).toBeTruthy();
        expect(screen.getByTestId('analytics-year-toggles')).toBeTruthy();
        expect(screen.getByTestId('analytics-year-2025')).toBeTruthy();
        expect(screen.getByTestId('analytics-year-2024')).toBeTruthy();
        expect(screen.getByTestId('analytics-year-2023')).toBeTruthy();
        expect(screen.getByTestId('analytics-year-2022')).toBeTruthy();
        expect(screen.getByTestId('analytics-date-bounds')).toBeTruthy();
        expect(screen.getByTestId('analytics-weather-overlay')).toBeTruthy();
    });

    it('switches to Activities tab and shows the empty state with a disabled add button', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-activities');

        expect(screen.getByTestId('index-panel-tab-activities').getAttribute('data-state')).toBe(
            'active',
        );
        expect(screen.getByTestId('activities-tab')).toBeTruthy();
        expect(screen.getByTestId('activities-empty-state')).toBeTruthy();
        expect(screen.getByText('No activities added to this field.')).toBeTruthy();

        const addButton = screen.getByTestId('activities-add-button') as HTMLButtonElement;
        expect(addButton.disabled).toBe(true);
        const addTrigger = screen.getByTestId('activities-add-trigger') as HTMLButtonElement;
        expect(addTrigger.disabled).toBe(true);
    });
});
