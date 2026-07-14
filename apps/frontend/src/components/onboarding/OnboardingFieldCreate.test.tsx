import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OnboardingFieldCreate from '@/components/onboarding/OnboardingFieldCreate';
import type { ResolvedBasemapConfig } from '@/map/basemap';

const state = vi.hoisted(() => ({
    config: null as unknown as Record<string, unknown>,
    basemaps: [] as ResolvedBasemapConfig[],
}));

vi.mock('@/components/map/MapLayerManager', () => ({
    MapLayerManager: ({
        basemap,
        onBasemapError,
    }: {
        basemap: ResolvedBasemapConfig;
        onBasemapError?: (error: Error) => void;
    }) => {
        state.basemaps.push(basemap);
        return (
            <button
                type="button"
                data-testid="map-layer-manager"
                onClick={ () => onBasemapError?.(new Error('ArcGIS referrer rejected')) }
            >
                Map
            </button>
        );
    },
}));

vi.mock('@/components/fields/FieldDrawController', () => ({
    FieldDrawController: ({
        onPolygonComplete,
    }: {
        onPolygonComplete?: (geometry: {
            type: 'Polygon';
            coordinates: number[][][];
        }) => void;
    }) => (
        <button
            type="button"
            data-testid="complete-field-draw"
            onClick={ () => onPolygonComplete?.({
                type: 'Polygon',
                coordinates: [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12]]],
            }) }
        >
            Complete field
        </button>
    ),
}));

vi.mock('@/components/fields/FieldBoundaryLayer', () => ({
    FieldBoundaryLayer: () => null,
}));

vi.mock('@/components/map/MapControls', () => ({
    MapControls: () => null,
}));

vi.mock('@/components/scaffold/PlotToolbar', () => ({
    PlotToolbar: () => null,
}));

vi.mock('@/lib/api', () => ({
    getField: vi.fn(),
}));

vi.mock('@/lib/queries', () => ({
    useConfig: () => ({ data: state.config, isLoading: false, isError: false }),
    useCreateField: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useUpdateField: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

function config(usageModel: string) {
    return {
        appName: 'Akasha',
        aoi: {
            id: 'bangalore',
            name: 'Bangalore',
            center: [77.59, 12.97],
            zoom: 11,
            bounds: [77, 12, 78, 13],
        },
        basemapStyleUrl: '',
        basemap: {
            provider: 'esri',
            style: 'arcgis/imagery',
            styleFamily: 'arcgis',
            usageModel,
            places: 'none',
            sessionDurationSeconds: 43_200,
        },
        maxPolygonAreaHa: 50,
        maxPolygonVertices: 5000,
        usablePixelThresholdPercent: 70,
        supportedIndices: ['NDVI'],
        defaultIndex: 'NDVI',
        adminIngestionLiveTriggerEnabled: false,
    };
}

function renderPage() {
    return render(
        <MemoryRouter>
            <OnboardingFieldCreate />
        </MemoryRouter>,
    );
}

afterEach(() => {
    state.basemaps.length = 0;
    window.sessionStorage.clear();
    vi.unstubAllEnvs();
});

describe('OnboardingFieldCreate basemap behavior', () => {
    it.each(['session', 'tile'] as const)('forwards the %s usage model', (usageModel) => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config(usageModel);

        renderPage();

        expect(state.basemaps[state.basemaps.length - 1]).toMatchObject({
            provider: 'esri',
            usageModel,
        });
    });

    it('shows runtime errors while keeping the onboarding workflow mounted', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('tile');
        renderPage();

        fireEvent.click(screen.getByTestId('complete-field-draw'));
        fireEvent.change(screen.getByPlaceholderText('Field name'), {
            target: { value: 'Preserved onboarding draft' },
        });
        fireEvent.click(screen.getByTestId('map-layer-manager'));

        expect(screen.getByTestId('basemap-runtime-error').textContent).toContain(
            'Unable to load Esri basemap: ArcGIS referrer rejected',
        );
        expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy();
        expect(screen.getByTestId('map-layer-manager')).toBeTruthy();
        expect(screen.getByDisplayValue('Preserved onboarding draft')).toBeTruthy();
    });

    it('shows unsupported usage models as configuration errors', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('per-request');

        renderPage();

        expect(screen.getByText(/Unsupported Esri basemap usage model "per-request"/)).toBeTruthy();
        expect(screen.queryByTestId('map-layer-manager')).toBeNull();
    });
});
