import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EditFieldDialog, { sortVegetationCyclesForDisplay } from '@/components/seasons/EditFieldDialog';
import type { ResolvedBasemapConfig } from '@/map/basemap';
import type { Field } from '@/types/api';

const state = vi.hoisted(() => ({
    config: null as unknown as Record<string, unknown>,
    basemaps: [] as ResolvedBasemapConfig[],
    seasons: [] as Array<{ id: string; name: string; startDate?: string | null; endDate?: string | null; createdAt?: string | null }>,
    vegetationCycles: {} as Record<string, Array<Record<string, unknown>>>,
    addCycle: vi.fn(),
    clearSeasonCycles: vi.fn(),
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
        cycles: state.vegetationCycles,
        setFieldCycles: vi.fn(),
        addCycle: state.addCycle,
        removeCycle: vi.fn(),
        updateCycle: vi.fn(),
        clearSeasonCycles: state.clearSeasonCycles,
    }),
}));

vi.mock('@/lib/queries', () => ({
    queryKeys: { varieties: (cropId: number) => ['varieties', cropId] },
    useConfig: () => ({ data: state.config }),
    useCrops: () => ({ data: [] }),
    useFieldGroups: () => ({ data: [] }),
    useFields: () => ({ data: [FIELD] }),
    useIrrigationTypes: () => ({ data: [] }),
    useSeasons: () => ({ data: state.seasons }),
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

function renderDialog(field: Field = FIELD) {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return render(
        <MemoryRouter>
            <QueryClientProvider client={ queryClient }>
                <EditFieldDialog
                    field={ field }
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
    state.seasons = [];
    state.vegetationCycles = {};
    state.addCycle.mockReset();
    state.clearSeasonCycles.mockReset();
    vi.unstubAllEnvs();
});

describe('sortVegetationCyclesForDisplay', () => {
    it('keeps a newly added draft cycle at the top of the list', () => {
        const cycles = [
            {
                id: 'existing',
                cropName: 'Wheat',
                variety: '',
                maturity: '',
                year: 2024,
                plantingDate: '2024-01-10',
                irrigationType: '',
                targetYield: null,
                harvestingDate: '2024-05-15',
                tillageType: '',
                actualYield: null,
                isCutOff: false,
                notes: '',
            },
            {
                id: 'draft',
                cropName: '',
                variety: '',
                maturity: '',
                year: 2025,
                plantingDate: '',
                irrigationType: '',
                targetYield: null,
                harvestingDate: '',
                tillageType: '',
                actualYield: null,
                isCutOff: false,
                notes: '',
            },
        ];

        expect(sortVegetationCyclesForDisplay(cycles).map((cycle) => cycle.id)).toEqual(['draft', 'existing']);
    });
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

describe('EditFieldDialog single-crop-per-season validation', () => {
    const season = { id: 'season-1', name: 'Kharif 2025', startDate: null, endDate: null, createdAt: null };
    const cropCycle = {
        id: 'cycle-1',
        cropName: 'Wheat',
        variety: '',
        maturity: '',
        year: 2025,
        plantingDate: '',
        irrigationType: '',
        targetYield: null,
        harvestingDate: '',
        tillageType: '',
        actualYield: null,
        isCutOff: false,
        notes: '',
    };

    function stubEnv() {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('tile');
    }

    it('blocks adding a cycle when the season already has a crop', () => {
        stubEnv();
        state.seasons = [season];
        state.vegetationCycles = { 'season-1': [cropCycle] };

        renderDialog({ ...FIELD, seasonIds: ['season-1'] });
        fireEvent.click(screen.getByRole('button', { name: /add vegetation cycle/i }));

        expect(screen.getByText(/Wheat is already added for this season/i)).toBeTruthy();
        expect(state.addCycle).not.toHaveBeenCalled();
    });

    it('adds a cycle when the season has no crop', () => {
        stubEnv();
        state.seasons = [season];
        state.vegetationCycles = {};

        renderDialog({ ...FIELD, seasonIds: ['season-1'] });
        fireEvent.click(screen.getByRole('button', { name: /add vegetation cycle/i }));

        expect(state.addCycle).toHaveBeenCalledWith('season-1', undefined);
    });

    it('keeps the current crop and adds a new cycle after confirming the replacement', () => {
        stubEnv();
        state.seasons = [season];
        state.vegetationCycles = { 'season-1': [cropCycle] };

        renderDialog({ ...FIELD, seasonIds: ['season-1'] });
        fireEvent.click(screen.getByRole('button', { name: /add vegetation cycle/i }));
        fireEvent.click(screen.getByRole('button', { name: /replace crop/i }));

        expect(state.clearSeasonCycles).not.toHaveBeenCalled();
        expect(state.addCycle).toHaveBeenCalledWith('season-1', undefined);
    });
});
