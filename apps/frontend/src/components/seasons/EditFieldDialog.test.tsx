import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';
import type { ResolvedBasemapConfig } from '@/map/basemap';
import type { Field } from '@/types/api';

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

vi.mock('@/components/fields/FieldBoundaryLayer', () => ({
    FieldBoundaryLayer: () => null,
}));

vi.mock('@/hooks/useVegetationCycles', () => ({
    useVegetationCycles: () => ({
        cycles: {},
        setFieldCycles: vi.fn(),
        addCycle: vi.fn(),
        removeCycle: vi.fn(),
        updateCycle: vi.fn(),
        clearSeasonCycles: vi.fn(),
    }),
}));

vi.mock('@/lib/queries', () => ({
    queryKeys: { varieties: (cropId: number) => ['varieties', cropId] },
    useConfig: () => ({ data: state.config }),
    useCrops: () => ({ data: [] }),
    useFieldGroups: () => ({ data: [] }),
    useFields: () => ({ data: [FIELD] }),
    useIrrigationTypes: () => ({ data: [] }),
    useSeasons: () => ({ data: [] }),
    useTillageTypes: () => ({ data: [] }),
    useVarieties: () => ({ data: { items: [] } }),
}));

const FIELD: Field = {
    id: 'field-1',
    userId: 'user-1',
    name: 'North field',
    areaHa: 4.2,
    geometry: {
        type: 'Polygon',
        coordinates: [[[77.59, 12.97], [77.6, 12.97], [77.6, 12.98], [77.59, 12.97]]],
    },
    groupId: null,
    seasonIds: [],
    vegetationData: [],
    createdAt: null,
    updatedAt: null,
};

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

function renderDialog() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return render(
        <MemoryRouter>
            <QueryClientProvider client={ queryClient }>
                <EditFieldDialog
                    field={ FIELD }
                    open
                    onOpenChange={ vi.fn() }
                    onSave={ vi.fn() }
                    onDelete={ vi.fn() }
                />
            </QueryClientProvider>
        </MemoryRouter>,
    );
}

afterEach(() => {
    state.basemaps.length = 0;
    vi.unstubAllEnvs();
});

describe('EditFieldDialog basemap behavior', () => {
    it.each(['session', 'tile'] as const)('forwards the %s usage model', (usageModel) => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config(usageModel);

        renderDialog();

        expect(state.basemaps[state.basemaps.length - 1]).toMatchObject({
            provider: 'esri',
            usageModel,
        });
    });

    it('shows runtime errors while keeping editable field state mounted', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('tile');
        renderDialog();

        fireEvent.change(screen.getByDisplayValue('North field'), {
            target: { value: 'Preserved edited field' },
        });
        fireEvent.click(screen.getByTestId('map-layer-manager'));

        expect(screen.getByTestId('basemap-runtime-error').textContent).toContain(
            'Unable to load Esri basemap: ArcGIS referrer rejected',
        );
        expect(screen.getByDisplayValue('Preserved edited field')).toBeTruthy();
        expect(screen.getByTestId('map-layer-manager')).toBeTruthy();
    });

    it('shows unsupported usage models instead of an indefinite loading state', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('per-request');

        renderDialog();

        expect(screen.getByTestId('basemap-configuration-error').textContent).toContain(
            'Unsupported Esri basemap usage model "per-request"',
        );
        expect(screen.getByDisplayValue('North field')).toBeTruthy();
        expect(screen.queryByTestId('map-layer-manager')).toBeNull();
    });
});
