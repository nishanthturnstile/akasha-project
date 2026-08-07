import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FieldCreatePage from '@/pages/monitoring/FieldCreatePage';
import { MapViewProvider } from '@/state/mapViewContext';
import { useMapView } from '@/state/useMapView';
import type { ResolvedBasemapConfig } from '@/map/basemap';

const state = vi.hoisted(() => ({
    config: null as unknown as Record<string, unknown>,
    basemaps: [] as ResolvedBasemapConfig[],
    createField: vi.fn(),
    setLastField: vi.fn(),
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
        onPolygonComplete?: (
            geometry: { type: 'Polygon'; coordinates: number[][][] },
            featureId?: string,
        ) => void;
    }) => (
        <button
            type="button"
            data-testid="complete-field-draw"
            onClick={ () => onPolygonComplete?.(
                {
                    type: 'Polygon',
                    coordinates: [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12]]],
                },
                'feature-1',
            ) }
        >
            Complete field
        </button>
    ),
}));

vi.mock('@/components/fields/FieldBoundaryLayer', () => ({
    FieldBoundaryLayer: () => null,
}));

vi.mock('@/components/fields/GlobalViewPanel', () => ({
    FieldThumbnail: () => null,
    setLastFieldForSeason: state.setLastField,
}));

vi.mock('@/components/map/MapControls', () => ({
    MapControls: () => null,
}));

vi.mock('@/components/seasons/CreateSeasonDialog', () => ({ default: () => null }));
vi.mock('@/components/seasons/EditFieldDialog', () => ({ default: () => null }));

vi.mock('@/components/ui/tooltip', () => ({
    Tooltip: ({ children }: { children: React.ReactNode }) => <>{ children }</>,
    TooltipContent: ({ children }: { children: React.ReactNode }) => <>{ children }</>,
    TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{ children }</>,
}));

vi.mock('@/lib/queries', () => ({
    queryKeys: { fields: ['fields'] },
    useConfig: () => ({ data: state.config, isLoading: false, isError: false }),
    useCreateField: () => ({ isPending: false, mutateAsync: state.createField }),
    useFields: () => ({ data: [] }),
    useSeasons: () => ({ data: [] }),
    useNextFieldName: () => ({ data: { name: 'Field 1' } }),
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
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    return render(
        <MemoryRouter>
            <QueryClientProvider client={ queryClient }>
                <MapViewProvider>
                    <FieldCreatePage />
                </MapViewProvider>
            </QueryClientProvider>
        </MemoryRouter>,
    );
}

afterEach(() => {
    state.basemaps.length = 0;
    vi.unstubAllEnvs();
});

describe('FieldCreatePage basemap behavior', () => {
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

    it('shows runtime errors while keeping field creation controls mounted', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('tile');
        renderPage();

        fireEvent.click(screen.getByTestId('complete-field-draw'));
        fireEvent.click(screen.getByTestId('map-layer-manager'));

        expect(screen.getByTestId('basemap-runtime-error').textContent).toContain(
            'Unable to load Esri basemap: ArcGIS referrer rejected',
        );
        expect(screen.getByRole('heading', { name: 'Add field' })).toBeTruthy();
        expect(screen.getByTestId('map-layer-manager')).toBeTruthy();
        expect(screen.getByRole('button', { name: 'Save 1 field' })).toBeTruthy();
    });

    it('shows unsupported usage models as configuration errors', () => {
        vi.stubEnv('VITE_BASEMAP_PROVIDER', 'esri');
        vi.stubEnv('VITE_ESRI_API_KEY', 'AAPK_TEST_BASEMAP_KEY');
        state.config = config('per-request');

        renderPage();

        expect(screen.getByText(/Unsupported Esri basemap usage model "per-request"/)).toBeTruthy();
        expect(screen.queryByTestId('map-layer-manager')).toBeNull();
    });

    it('lands in Global View after saving a drawn field', async () => {
        state.config = config('session');
        state.createField.mockResolvedValue({
            id: 'field-new-1',
            userId: 'user-1',
            name: 'Field 1',
            areaHa: 1.1,
            geometry: {
                type: 'Polygon',
                coordinates: [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12]]],
            },
            groupId: null,
            seasonIds: ['season-1'],
            vegetationData: [],
            createdAt: null,
            updatedAt: null,
        });

        function LocationProbe() {
            const location = useLocation();
            return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>;
        }

        function SelectionProbe() {
            const view = useMapView();
            return <div data-testid="selection-probe">{view.selectedPlotId ?? ''}</div>;
        }

        const queryClient = new QueryClient({
            defaultOptions: { queries: { retry: false, gcTime: 0 } },
        });
        render(
            <MemoryRouter initialEntries={ ['/monitoring/field-create?mode=draw&seasonId=season-1'] }>
                <QueryClientProvider client={ queryClient }>
                    <MapViewProvider>
                        <LocationProbe />
                        <SelectionProbe />
                        <FieldCreatePage />
                    </MapViewProvider>
                </QueryClientProvider>
            </MemoryRouter>,
        );

        fireEvent.click(screen.getByTestId('complete-field-draw'));
        fireEvent.click(screen.getByRole('button', { name: 'Save 1 field' }));

        await waitFor(() => {
            expect(screen.getByTestId('location-probe').textContent).toBe(
                '/monitoring/field-analytics?seasonId=season-1',
            );
        });
        expect(window.sessionStorage.getItem('akasha.seasonId')).toBe('season-1');
        expect(state.setLastField).toHaveBeenCalledWith('season-1', 'field-new-1');
        expect(screen.getByTestId('selection-probe').textContent).toBe('field-new-1');
    });
});
