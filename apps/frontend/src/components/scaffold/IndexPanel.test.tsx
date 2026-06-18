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

describe('IndexPanel — LISS-4 provenance UI (Phase E)', () => {
    it('shows the prefer-high-res toggle when onPreferHighResChange is provided', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
                preferHighRes
                onPreferHighResChange={ () => undefined }
            />,
        );

        expect(screen.getByTestId('analytics-prefer-high-res')).toBeTruthy();
    });

    it('does not show the prefer-high-res toggle when onPreferHighResChange is absent', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        expect(screen.queryByTestId('analytics-prefer-high-res')).toBeNull();
    });

    it('renders the enhanced badge when the statistics response has enhanced=true', async () => {
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
                            acquisitionDate: '2026-04-27',
                            cloudMask,
                            statistics: {
                                min: 0.2,
                                max: 0.7,
                                mean: 0.45,
                                stddev: 0.1,
                                validPixelPercent: 95,
                                cloudMaskedPercent: 3,
                                coveragePercent: 98,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 2,
                                coveragePixels: 98,
                                maskedPixels: 3,
                                validPixels: 95,
                            },
                            enhanced: true,
                            resolvedSourceId: 'resourcesat-2a-liss4',
                            resolutionMeters: 5.8,
                            basisDate: '2026-04-27',
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'], warnings: [] },
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
                            startDate: '2025-10-29',
                            endDate: '2026-04-27',
                            points: [],
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
                preferHighRes
                onPreferHighResChange={ () => undefined }
            />,
        );

        activateTab('index-panel-tab-chart');

        const badge = await screen.findByTestId('analytics-enhanced-badge');
        expect(badge).toBeTruthy();
        expect(badge.textContent).toContain('Enhanced');
        expect(badge.textContent).toContain('5.8 m');
        expect(badge.textContent).toContain('LISS-4');
    });

    it('does not render the enhanced badge when enhanced is false/absent', async () => {
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
                            acquisitionDate: '2026-04-27',
                            cloudMask,
                            statistics: {
                                min: 0.2,
                                max: 0.7,
                                mean: 0.45,
                                stddev: 0.1,
                                validPixelPercent: 95,
                                cloudMaskedPercent: 3,
                                coveragePercent: 98,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 2,
                                coveragePixels: 98,
                                maskedPixels: 3,
                                validPixels: 95,
                            },
                            enhanced: false,
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'], warnings: [] },
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
                            startDate: '2025-10-29',
                            endDate: '2026-04-27',
                            points: [],
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        // Wait for the data to load (mean value is available)
        await screen.findByText('0.45');
        expect(screen.queryByTestId('analytics-enhanced-badge')).toBeNull();
    });

    it('shows the NDMI provenance note when the active index is NDMI', () => {
        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDMI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        const note = screen.getByTestId('analytics-ndmi-note');
        expect(note).toBeTruthy();
        expect(note.textContent).toContain('Moisture served from LISS-3');
        expect(note.textContent).toContain('LISS-4 has no SWIR band');
    });

    it('shows the provenance note from the stats response when present', async () => {
        const customNote = 'Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band.';
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
                            indexType: 'NDMI',
                            sourceId: 'resourcesat-2a-liss3-boa',
                            acquisitionDate: '2026-04-27',
                            cloudMask,
                            statistics: {
                                min: -0.1,
                                max: 0.4,
                                mean: 0.15,
                                stddev: 0.08,
                                validPixelPercent: 92,
                                cloudMaskedPercent: 4,
                                coveragePercent: 96,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 4,
                                coveragePixels: 96,
                                maskedPixels: 4,
                                validPixels: 92,
                            },
                            enhanced: false,
                            provenanceNote: customNote,
                            metadata: { formula: '(NIR-SWIR1)/(NIR+SWIR1)', bands: ['BAND4', 'BAND5'], warnings: [] },
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
                            indexType: 'NDMI',
                            startDate: '2025-10-29',
                            endDate: '2026-04-27',
                            points: [],
                            metadata: { formula: '(NIR-SWIR1)/(NIR+SWIR1)', bands: ['BAND4', 'BAND5'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDMI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        const note = await screen.findByTestId('analytics-ndmi-note');
        expect(note.textContent).toBe(customNote);
    });
});

describe('IndexPanel — cloud/masked clarity label', () => {
    it('shows "Cloud / masked" label for the masked-percent metric when metricsProvisional is false', async () => {
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
                            acquisitionDate: '2026-04-27',
                            cloudMask,
                            statistics: {
                                min: 0.2,
                                max: 0.7,
                                mean: 0.45,
                                stddev: 0.1,
                                validPixelPercent: 92,
                                cloudMaskedPercent: 5,
                                coveragePercent: 97,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 3,
                                coveragePixels: 97,
                                maskedPixels: 5,
                                validPixels: 92,
                            },
                            metricsProvisional: false,
                            maskMethod: 'SCL cloud mask',
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'], warnings: [] },
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
                            startDate: '2025-10-29',
                            endDate: '2026-04-27',
                            points: [],
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        // Wait for stats to load, then check the label
        await screen.findByText('0.45');
        expect(screen.getByText('Cloud / masked')).toBeTruthy();
    });

    it('shows "Masked" label for the masked-percent metric when metricsProvisional is true', async () => {
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
                            acquisitionDate: '2026-04-27',
                            cloudMask,
                            statistics: {
                                min: 0.15,
                                max: 0.65,
                                mean: 0.38,
                                stddev: 0.09,
                                validPixelPercent: 88,
                                cloudMaskedPercent: 8,
                                coveragePercent: 96,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 4,
                                coveragePixels: 96,
                                maskedPixels: 8,
                                validPixels: 88,
                            },
                            metricsProvisional: true,
                            maskMethod: 'Akasha threshold mask v1',
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'], warnings: [] },
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
                            startDate: '2025-10-29',
                            endDate: '2026-04-27',
                            points: [],
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['BAND4', 'BAND3'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        // Wait for stats to load, then check the label
        await screen.findByText('0.38');
        expect(screen.getByText('Masked')).toBeTruthy();
    });
});
