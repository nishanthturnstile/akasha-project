import { render, screen, fireEvent, within } from '@testing-library/react';
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
    it('presents field-clipped EOS-04 evidence as support, not NDVI', async () => {
        const onRadarEvidenceVisibleChange = vi.fn();
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path.startsWith('/api/fields/plot-1/monitoring/evidence')) {
                    return Promise.resolve(jsonResponse({
                        fieldId: 'plot-1',
                        targetDate: '2026-07-18',
                        optical: {
                            status: 'quality_limited',
                            sourceId: 'sentinel-2-l2a',
                            indexType: 'NDVI',
                            latestCandidateDate: '2026-07-17',
                            latestQualifyingDate: null,
                            ageDays: null,
                            staleAfterDays: 10,
                            requirements: {
                                minimumCoveragePercent: 95,
                                minimumUsablePixelPercent: 80,
                                maximumCombinedCloudShadowPercent: 20,
                            },
                        },
                        radar: {
                            status: 'AVAILABLE',
                            sourceId: 'eos-04-sar-mrs-l2b',
                            triggered: true,
                            triggerReason: 'Optical quality gap.',
                            acquisitionDate: '2026-07-17',
                            coveragePercent: 100,
                            quality: { qualified: true, confidence: 'high', warnings: [] },
                            comparison: {
                                status: 'INSUFFICIENT_BASELINE',
                                previousComparableDate: '2026-06-13',
                                comparableObservationCount: 2,
                                excludedObservationCount: 0,
                            },
                            change: {
                                status: 'AVAILABLE',
                                referenceDate: '2026-06-13',
                                bands: [
                                    {
                                        polarization: 'HH',
                                        currentMedianDb: -8,
                                        referenceMedianDb: -10,
                                        medianDeltaDb: 2,
                                    },
                                ],
                                features: {},
                            },
                            baseline: {
                                status: 'AVAILABLE',
                                requiredPriorObservations: 5,
                                priorObservationCount: 5,
                                bands: [
                                    {
                                        polarization: 'HH',
                                        currentValue: -7.22,
                                        baselineMedian: -6.47,
                                        mad: 0.5,
                                        robustDeviation: -1,
                                    },
                                    {
                                        polarization: 'HV',
                                        currentValue: -14.74,
                                        baselineMedian: -13.43,
                                        mad: 0.78,
                                        robustDeviation: -1.13,
                                    },
                                ],
                            },
                            overlayUrl: '/api/fields/plot-1/sar/overlay.png?targetDate=2026-07-18',
                        },
                    }));
                }
                if (path.startsWith('/api/seasons')) return Promise.resolve(jsonResponse([]));
                if (path === '/api/fields/plot-1/indices/statistics') {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'pipeline',
                        scope: 'field',
                        sourceId: 'sentinel-2-l2a',
                        acquisitionDate: '2026-07-18',
                        indexType: 'NDVI',
                        cloudMask,
                        statistics: {
                            min: 0.1,
                            max: 0.8,
                            mean: 0.5,
                            stddev: 0.1,
                            validPixelPercent: 90,
                            cloudMaskedPercent: 5,
                            coveragePercent: 95,
                        },
                        pixelCounts: {
                            totalPixels: 100,
                            nodataPixels: 5,
                            coveragePixels: 95,
                            maskedPixels: 5,
                            validPixels: 90,
                        },
                        metadata: { bands: [], warnings: [] },
                    }));
                }
                if (path.startsWith('/api/fields/plot-1/analytics/trend')) {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'pipeline',
                        scope: 'pipeline',
                        sourceId: 'sentinel-2-l2a',
                        indexType: 'NDVI',
                        startDate: '2026-01-01',
                        endDate: '2026-07-18',
                        points: [],
                        metadata: { bands: [] },
                    }));
                }
                return Promise.resolve(jsonResponse({}));
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-07-18"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
                onRadarEvidenceVisibleChange={ onRadarEvidenceVisibleChange }
            />,
        );

        expect(await screen.findByText(/provides structural and moisture-sensitive evidence, not NDVI/i)).toBeTruthy();
        expect(
            (globalThis.fetch as unknown as { mock: { calls: Array<[RequestInfo | URL]> } })
                .mock.calls.some(([input]) =>
                    String(input).includes('/monitoring/evidence?') &&
                    String(input).includes('targetDate=2026-07-18') &&
                    String(input).includes('includeRadar=true')),
        ).toBe(true);
        expect(screen.getByTestId('radar-temporal-change').textContent).toContain('HH +2.00 dB');
        expect(screen.getByTestId('radar-baseline-status').textContent).toContain('Field baseline (5 prior passes)');
        expect(screen.getByTestId('radar-baseline-status').textContent).toContain('HH -1.00 · HV -1.13 relative deviation');
        expect(screen.getByText(/It is not NDVI or a diagnosis/i)).toBeTruthy();
        fireEvent.click(screen.getByTestId('toggle-radar-evidence'));
        expect(onRadarEvidenceVisibleChange).toHaveBeenCalledWith(true);
    });

    it('shows selected NISAR evidence alongside a usable optical observation', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path.startsWith('/api/fields/plot-1/monitoring/evidence')) {
                    return Promise.resolve(jsonResponse({
                        fieldId: 'plot-1',
                        targetDate: '2026-01-02',
                        optical: { status: 'usable' },
                        radar: {
                            status: 'AVAILABLE',
                            sourceId: 'nisar-ssar-beta-gcov',
                            triggered: true,
                            triggerReason: 'Radar evidence was explicitly requested.',
                            acquisitionDate: '2026-01-03',
                            coveragePercent: 100,
                            displayedPolarization: 'HH',
                            quality: { qualified: true, confidence: 'high', warnings: [] },
                            overlayUrl: '/api/fields/plot-1/sar/overlay.png?sourceId=nisar-ssar-beta-gcov',
                        },
                    }));
                }
                if (path.startsWith('/api/seasons')) return Promise.resolve(jsonResponse([]));
                if (path === '/api/fields/plot-1/indices/statistics') {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'pipeline',
                        scope: 'field',
                        sourceId: 'sentinel-2-l2a',
                        acquisitionDate: '2026-01-02',
                        indexType: 'NDVI',
                        cloudMask,
                        statistics: null,
                        pixelCounts: {
                            totalPixels: 0,
                            nodataPixels: 0,
                            coveragePixels: 0,
                            maskedPixels: 0,
                            validPixels: 0,
                        },
                        metadata: { bands: [], warnings: [] },
                    }));
                }
                if (path.startsWith('/api/fields/plot-1/analytics/trend')) {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'pipeline',
                        scope: 'pipeline',
                        sourceId: 'sentinel-2-l2a',
                        indexType: 'NDVI',
                        startDate: '2025-07-06',
                        endDate: '2026-01-02',
                        points: [],
                        metadata: { bands: [] },
                    }));
                }
                return Promise.resolve(jsonResponse({}));
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-01-02"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
                onRadarEvidenceVisibleChange={ vi.fn() }
            />,
        );

        expect(await screen.findByText('Radar field evidence')).toBeTruthy();
        expect(screen.getByText(/NISAR S-band radar evidence.*using HH/i)).toBeTruthy();
    });

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

    it('renders three tabs with Crop info active by default', () => {
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

        // All three Crop info cards are present on the default tab.
        expect(screen.getByTestId('crop-info-card-crop-rotation')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-growth-stages')).toBeTruthy();
        expect(screen.getByTestId('crop-info-card-current-risks')).toBeTruthy();
    });

    it('opens the EOS-style growth stages editor for the selected crop cycle', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path.startsWith('/api/seasons')) return Promise.resolve(jsonResponse([]));
                if (path.includes('/indices/statistics')) {
                    return Promise.resolve(jsonResponse({
                        statistics: {
                            min: 0.1,
                            max: 0.8,
                            mean: 0.5,
                            stddev: 0.1,
                            validPixelPercent: 90,
                            cloudMaskedPercent: 5,
                            coveragePercent: 95,
                        },
                        pixelCounts: { maskedPixels: 0 },
                        metadata: { warnings: [] },
                    }));
                }
                if (path.includes('/analytics/trend')) {
                    return Promise.resolve(jsonResponse({ points: [], metadata: { bands: [] } }));
                }
                return Promise.resolve(jsonResponse({}));
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-07-18"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
                vegetationData={ [{
                    id: 'cycle-1',
                    fieldId: 'field-1',
                    seasonId: 'season-1',
                    year: 2026,
                    cropType: 14,
                    cropName: 'Rice',
                    growthStages: [{
                        id: null,
                        cropId: 14,
                        seq: 1,
                        name: 'Germination',
                        duration: '0-21',
                        startDate: null,
                        saved: false,
                    }],
                }] }
            />,
        );

        const card = await screen.findByTestId('crop-info-card-growth-stages');
        fireEvent.click(within(card).getByRole('button', { name: /No start date for the growth stage/ }));
        expect(await screen.findByRole('dialog', { name: 'Edit growth stages' })).toBeTruthy();
        const closeButtons = screen.getAllByRole('button', { name: 'Close' });
        fireEvent.click(closeButtons[closeButtons.length - 1]);

        const germinationDot = within(card).getByRole('button', { name: 'Select Germination' }).querySelector('span');
        expect(germinationDot).toBeTruthy();
        fireEvent.click(germinationDot as HTMLElement);
        expect(screen.getByTestId('growth-stage-selected-crop').textContent).toContain('Rice');
        expect(screen.getByTestId('growth-stage-selected-info').textContent).toContain('Germination');
        fireEvent.click(within(card).getByRole('button', { name: 'Edit' }));

        expect(await screen.findByRole('dialog', { name: 'Edit growth stages' })).toBeTruthy();
        expect(screen.getByRole('button', { name: 'Select start date' })).toBeTruthy();
    });

    it('shows the stage active today when the cycle has saved start dates', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path.startsWith('/api/seasons')) return Promise.resolve(jsonResponse([]));
                if (path.includes('/indices/statistics')) {
                    return Promise.resolve(jsonResponse({
                        statistics: { min: 0, max: 1, mean: 0.5, stddev: 0.1, validPixelPercent: 100, cloudMaskedPercent: 0, coveragePercent: 100 },
                        pixelCounts: { maskedPixels: 0 },
                        metadata: { warnings: [] },
                    }));
                }
                if (path.includes('/analytics/trend')) return Promise.resolve(jsonResponse({ points: [], metadata: { bands: [] } }));
                return Promise.resolve(jsonResponse({}));
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-08-14"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
                vegetationData={ [{
                    id: 'cycle-1', fieldId: 'field-1', seasonId: 'season-1', year: 2026,
                    cropType: 14, cropName: 'Rice',
                    growthStages: [
                        { id: 'stage-1', cropId: 14, seq: 1, name: 'Germination', duration: '0-21', startDate: '2000-01-01', saved: true },
                        { id: null, cropId: 14, seq: 2, name: 'Tillering', duration: '21-45', startDate: null, saved: false },
                    ],
                }] }
            />,
        );

        const selectedInfo = await screen.findByTestId('growth-stage-selected-info');
        expect(selectedInfo.textContent).toContain('Tillering');
        expect(selectedInfo.textContent).not.toContain('Jan 1, 2000');
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

    it('renders the backend NDVI value split in Crop info only', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn((input: RequestInfo | URL) => {
                const path = String(input);
                if (path === '/api/fields/plot-1/indices/statistics') {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'native',
                        scope: 'field',
                        sourceId: 'sentinel-2-l2a',
                        acquisitionDate: '2026-04-27',
                        indexType: 'NDVI',
                        cloudMask,
                        statistics: {
                            min: 0.1,
                            max: 0.8,
                            mean: 0.5,
                            stddev: 0.1,
                            validPixelPercent: 90,
                            cloudMaskedPercent: 5,
                            coveragePercent: 95,
                        },
                        pixelCounts: {
                            totalPixels: 100,
                            nodataPixels: 5,
                            coveragePixels: 95,
                            maskedPixels: 5,
                            validPixels: 90,
                        },
                        valueSplit: {
                            indexType: 'NDVI',
                            profileId: 'ndvi-density-v1',
                            percentageBasis: 'classifiablePixels',
                            thresholds: [0.2, 0.4, 0.6],
                            totalPixels: 100,
                            classifiablePixels: 95,
                            noDataPixels: 5,
                            unclassifiedPixels: 0,
                            categories: [
                                { id: 'denseVegetation', label: 'Dense vegetation', minInclusive: 0.6, maxExclusive: null, pixelCount: 40, percentage: 40 },
                                { id: 'moderateVegetation', label: 'Moderate vegetation', minInclusive: 0.4, maxExclusive: 0.6, pixelCount: 30, percentage: 30 },
                                { id: 'sparseVegetation', label: 'Sparse vegetation', minInclusive: 0.2, maxExclusive: 0.4, pixelCount: 15, percentage: 15 },
                                { id: 'openSoil', label: 'Open soil', minInclusive: null, maxExclusive: 0.2, pixelCount: 5, percentage: 5 },
                                { id: 'cloudiness', label: 'Cloudiness', minInclusive: null, maxExclusive: null, pixelCount: 5, percentage: 10 },
                            ],
                        },
                        metadata: { bands: ['B8', 'B4'], warnings: [] },
                    }));
                }
                if (path.startsWith('/api/fields/plot-1/analytics/trend')) {
                    return Promise.resolve(jsonResponse({
                        plotId: 'plot-1',
                        provider: 'native',
                        scope: 'native_fallback',
                        sourceId: 'sentinel-2-l2a',
                        indexType: 'NDVI',
                        startDate: '2025-10-29',
                        endDate: '2026-04-27',
                        points: [],
                        metadata: { bands: ['B8', 'B4'] },
                    }));
                }
                if (path.startsWith('/api/seasons')) return Promise.resolve(jsonResponse([]));
                return Promise.resolve(jsonResponse({}));
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-04-27"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'MSAVI'] }
                cloudMask={ cloudMask }
            />,
        );
        const split = await screen.findByTestId('ndvi-value-split');
        expect(screen.getByTestId('index-panel-content-crop-info').contains(split)).toBe(true);
        expect(screen.getByText('NDVI values split')).toBeTruthy();

        activateTab('index-panel-tab-chart');

        expect(screen.getByTestId('analytics-statistics-summary')).toBeTruthy();
        expect(screen.getByTestId('analytics-chart-section')).toBeTruthy();
        expect(screen.queryByTestId('ndvi-value-split')).toBeNull();
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

    it('renders optional Sentinel-2 pipeline provenance without exposing proxy URLs', async () => {
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
                            sourceId: 'sentinel-2-l2a',
                            acquisitionDate: '2026-01-15',
                            cloudMask,
                            statistics: {
                                min: 0.12,
                                max: 0.86,
                                mean: 0.54,
                                stddev: 0.08,
                                validPixelPercent: 92.5,
                                cloudMaskedPercent: 4.2,
                                coveragePercent: 100,
                            },
                            pixelCounts: {
                                totalPixels: 3736,
                                nodataPixels: 0,
                                coveragePixels: 3736,
                                maskedPixels: 280,
                                validPixels: 3456,
                            },
                            basisDate: '2026-01-13',
                            provenanceNote: 'Pipeline Sentinel-2 scene selected by quality_first.',
                            metadata: {
                                formula: '(NIR-RED)/(NIR+RED)',
                                bands: ['NIR', 'RED'],
                                warnings: [],
                                pipeline: {
                                    enabled: true,
                                    status: 'AVAILABLE',
                                    source: 'sentinel-2-l2a',
                                    providerRoute: 'earthsearch:sentinel-2-l2a',
                                    requestedDate: '2026-01-15',
                                    selectedSceneDate: '2026-01-13',
                                    tileUrl: '/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_1',
                                    statsUrl: '/api/pipeline/field-index/stats?proxyId=px_2',
                                    freshness: {
                                        status: 'FRESH',
                                        latestProcessedSceneDate: '2026-01-13',
                                        aoiId: 'bangalore_60km_geodesic_aoi',
                                    },
                                    quality: {
                                        status: 'GOOD',
                                        reason: 'Field cloud cover within threshold',
                                        warnings: ['Near-scene fallback used'],
                                    },
                                },
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
                            sourceId: 'sentinel-2-l2a',
                            indexType: 'NDVI',
                            startDate: '2025-07-19',
                            endDate: '2026-01-15',
                            points: [],
                            metadata: { formula: '(NIR-RED)/(NIR+RED)', bands: ['NIR', 'RED'] },
                        }),
                    );
                }
                throw new Error(`Unexpected request: ${path}`);
            }),
        );

        renderPanel(
            <IndexPanel
                selectedPlot={ plot }
                selectedDate="2026-01-15"
                sourceId="sentinel-2-l2a"
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        const provenance = await screen.findByTestId('analytics-pipeline-provenance');
        expect(provenance.textContent).toContain('earthsearch:sentinel-2-l2a');
        expect(provenance.textContent).toContain('2026-01-13');
        expect(screen.getByTestId('analytics-pipeline-freshness').textContent).toContain('FRESH');
        expect(screen.getByTestId('analytics-pipeline-quality').textContent).toContain(
            'Field cloud cover within threshold',
        );
        expect(screen.getByTestId('analytics-pipeline-warning').textContent).toContain(
            'Near-scene fallback used',
        );
        expect(screen.getByTestId('analytics-pipeline-status').textContent).toContain('GOOD');
        expect(provenance.textContent).not.toContain('/api/pipeline');
        expect(provenance.textContent).not.toContain('ingestion');
        expect(provenance.textContent).not.toContain('sig=');
    });

    it('keeps native provider compatibility and hides pipeline UI when metadata is absent', async () => {
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
                            metadata: { formula: '(BAND4 - BAND3) / (BAND4 + BAND3)', bands: ['BAND4', 'BAND3'] },
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
                displayMode="NDVI"
                supportedIndices={ ['NDVI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        expect(await screen.findByText('0.42')).toBeTruthy();
        expect(screen.queryByTestId('analytics-pipeline-provenance')).toBeNull();
    });

    it('surfaces EOS-04 SAR support as cloud-gap context only', async () => {
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
                                validPixelPercent: 55,
                                cloudMaskedPercent: 45,
                                coveragePercent: 97,
                            },
                            pixelCounts: {
                                totalPixels: 100,
                                nodataPixels: 3,
                                coveragePixels: 97,
                                maskedPixels: 42,
                                validPixels: 55,
                            },
                            sarSupport: {
                                available: true,
                                status: 'available',
                                sourceId: 'eos-04-sar-mrs-l2b',
                                acquisitionDate: '2026-03-20',
                                daysFromOpticalDate: 1,
                                windowDays: 7,
                                cloudGap: true,
                                opticalCloudMaskedPercent: 45,
                                opticalMaskedPixels: 42,
                                polarizations: ['HH', 'HV'],
                                coveragePercent: 88,
                                confidence: 'high',
                                reason: 'EOS-04 SAR support is available for cloudy/masked optical pixels.',
                                bands: [],
                                wetnessSignal: 'not_assessed',
                                changeSignal: 'not_assessed',
                            },
                            metadata: {
                                formula: '(NIR-RED)/(NIR+RED)',
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
                selectedDate="2026-03-19"
                sourceId="resourcesat-2a-liss3-boa"
                displayMode="NDVI"
                supportedIndices={ ['NDVI', 'NDMI'] }
                cloudMask={ cloudMask }
            />,
        );

        activateTab('index-panel-tab-chart');

        const note = await screen.findByTestId('analytics-sar-support');
        expect(note.textContent).toContain('EOS-04 SAR support available');
        expect(note.textContent).toContain('high confidence');
        expect(note.textContent).not.toContain('NDVI replacement');
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
