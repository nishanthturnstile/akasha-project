import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { IndexPanel } from '@/components/scaffold/IndexPanel';
import type { CloudMaskOptions, Plot } from '@/types/api';

const cloudMask: CloudMaskOptions = {
    clouds: true,
    cloudShadows: true,
    cirrus: false,
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

function jsonResponse(payload: unknown) {
    return {
        ok: true,
        status: 200,
        json: async () => payload,
    };
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('IndexPanel tabbed analytics (Phase F)', () => {
    it('renders the empty-state guidance when no field is selected', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ null }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'MSAVI', 'NDMI'] }
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
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'MSAVI', 'NDMI'] }
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
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'MSAVI', 'NDMI'] }
                cloudMask={ cloudMask }
                periodFrom="2026-03-01"
                periodTo="2026-04-27"
            />,
        );

        activateTab('index-panel-tab-chart');

        expect(screen.getByTestId('index-panel-tab-chart').getAttribute('data-state')).toBe('active');
        expect(screen.getByTestId('index-panel-content-chart')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-NDVI')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-MSAVI')).toBeTruthy();
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

    it('labels ResourceSat statistics with provisional mask provenance', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-03-19"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="FCC"
                supportedIndices={ ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'] }
                cloudMask={ { clouds: true, cloudShadows: true, cirrus: false } }
                sourceMaskMethod="Akasha threshold mask v1"
                sourceMetricsProvisional
            />,
        );

        activateTab('index-panel-tab-chart');

        expect(screen.getByText('Akasha provisional-mask analytics')).toBeTruthy();
        expect(screen.getByTestId('analytics-mask-method').textContent).toContain(
            'Provisional mask: Akasha threshold mask v1',
        );
        expect(screen.getByTestId('analytics-index-NDVI')).toBeTruthy();
        expect(screen.getByTestId('analytics-index-NDWI_GREEN_NIR').textContent).toBe('NDWI');
        expect(screen.queryByTestId('analytics-index-NDRE')).toBeNull();
    });

    it('uses response-level mask provenance and masked pixel count for statistics', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path === '/api/fields/plot-1/indices/statistics') {
                    return Promise.resolve(
                        jsonResponse({
                            plotId: 'plot-1',
                            provider: 'native',
                            scope: 'field',
                            indexType: 'NDVI',
                            sourceId: 'resourcesat-2a-liss3-boa',
                            acquisitionDate: '2026-03-19',
                            cloudMask,
                            statistics: {
                                min: 0.1,
                                max: 0.8,
                                mean: 0.42,
                                stddev: 0.12,
                                validPixelPercent: 91,
                                cloudMaskedPercent: 6,
                                coveragePercent: 97,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 3,
                                coveragePixels: 97,
                                maskedPixels: 6,
                                validPixels: 91,
                            },
                            maskedPixels: 6,
                            maskMethod: 'Akasha threshold mask v1',
                            metricsProvisional: true,
                            metadata: {
                                formula: '(BAND4 - BAND3) / (BAND4 + BAND3)',
                                bands: ['BAND4', 'BAND3'],
                                warnings: [],
                            },
                        }),
                    );
                }
                if (path.startsWith('/api/fields/plot-1/analytics/trend')) {
                    return Promise.resolve(
                        jsonResponse({
                            plotId: 'plot-1',
                            provider: 'native',
                            scope: 'native_fallback',
                            sourceId: 'resourcesat-2a-liss3-boa',
                            indexType: 'NDVI',
                            startDate: '2025-09-20',
                            endDate: '2026-03-19',
                            points: [],
                            metadata: {
                                formula: '(BAND4 - BAND3) / (BAND4 + BAND3)',
                                bands: ['BAND4', 'BAND3'],
                            },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-03-19"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="FCC"
                supportedIndices={ ['NDVI', 'MSAVI', 'NDMI', 'NDWI_GREEN_NIR'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        expect(await screen.findByText('0.42')).toBeTruthy();
        expect(screen.getByText('Akasha provisional-mask analytics')).toBeTruthy();
        expect(screen.getByTestId('analytics-masked-pixels').textContent).toContain('6');
        expect(screen.getByTestId('analytics-mask-method').textContent).toContain(
            'Provisional mask: Akasha threshold mask v1',
        );
    });

    it('switches to Activities tab and shows the empty state with a disabled add button', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
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
