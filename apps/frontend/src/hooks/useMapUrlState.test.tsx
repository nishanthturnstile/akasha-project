import { act, fireEvent, render, screen } from '@testing-library/react';
import {
    MemoryRouter,
    Route,
    Routes,
    useLocation,
} from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { useMapUrlState } from '@/hooks/useMapUrlState';
import { MapViewProvider } from '@/state/mapViewContext';
import { useMapView } from '@/state/useMapView';

function LocationProbe() {
    const location = useLocation();
    return (
        <div
            data-testid="location-probe"
            data-pathname={ location.pathname }
            data-search={ location.search }
        />
    );
}

function StateProbe() {
    const view = useMapView();
    return (
        <div data-testid="state-probe">
            <span data-testid="state-plot">{ view.selectedPlotId ?? '' }</span>
            <span data-testid="state-scene">{ view.selectedDate ?? '' }</span>
            <span data-testid="state-from">{ view.periodFrom ?? '' }</span>
            <span data-testid="state-to">{ view.periodTo ?? '' }</span>
            <span data-testid="state-source">{ view.activeSourceId ?? '' }</span>
            <span data-testid="state-layer">{ view.displayMode ?? '' }</span>
            <button
                type="button"
                data-testid="set-scene"
                onClick={ () => view.setDate('2026-05-12') }
            >
                set-scene
            </button>
            <button
                type="button"
                data-testid="set-period"
                onClick={ () => view.setPeriod('2026-03-05', '2026-06-04') }
            >
                set-period
            </button>
            <button
                type="button"
                data-testid="clear-plot"
                onClick={ () => view.setSelectedPlotId(null) }
            >
                clear-plot
            </button>
        </div>
    );
}

function MapHarness() {
    useMapUrlState();
    return (
        <>
            <StateProbe />
            <LocationProbe />
        </>
    );
}

function renderHarness(initialEntry: string) {
    return render(
        <MapViewProvider>
            <MemoryRouter initialEntries={ [initialEntry] }>
                <Routes>
                    <Route path="/monitoring/field-analytics" element={ <MapHarness /> } />
                    <Route
                        path="/monitoring/field-analytics/field/:plotId"
                        element={ <MapHarness /> }
                    />
                </Routes>
            </MemoryRouter>
        </MapViewProvider>,
    );
}

afterEach(() => {
    window.localStorage.clear();
});

describe('useMapUrlState', () => {
    it('hydrates reducer state from the route param + query string on mount', () => {
        renderHarness(
            '/monitoring/field-analytics/field/field-42?scene=2026-04-27&from=2026-03-05&to=2026-04-27&source=resourcesat-2a-liss3-boa&layer=NDVI',
        );

        expect(screen.getByTestId('state-plot').textContent).toBe('field-42');
        expect(screen.getByTestId('state-scene').textContent).toBe('2026-04-27');
        expect(screen.getByTestId('state-from').textContent).toBe('2026-03-05');
        expect(screen.getByTestId('state-to').textContent).toBe('2026-04-27');
        expect(screen.getByTestId('state-source').textContent).toBe('resourcesat-2a-liss3-boa');
        expect(screen.getByTestId('state-layer').textContent).toBe('NDVI');
    });

    it('ignores malformed ISO dates in query params', () => {
        renderHarness(
            '/monitoring/field-analytics/field/field-42?scene=not-a-date&from=bad&to=2026-04-27',
        );

        expect(screen.getByTestId('state-scene').textContent).toBe('');
        expect(screen.getByTestId('state-from').textContent).toBe('');
        expect(screen.getByTestId('state-to').textContent).toBe('2026-04-27');
    });

    it('serializes reducer mutations back into the URL with replace history', () => {
        renderHarness('/monitoring/field-analytics/field/field-42?scene=2026-04-27&layer=NDVI');

        act(() => {
            fireEvent.click(screen.getByTestId('set-scene'));
        });
        act(() => {
            fireEvent.click(screen.getByTestId('set-period'));
        });

        const probe = screen.getByTestId('location-probe');
        expect(probe.getAttribute('data-pathname')).toBe(
            '/monitoring/field-analytics/field/field-42',
        );
        const search = probe.getAttribute('data-search') ?? '';
        expect(search).toContain('scene=2026-05-12');
        expect(search).toContain('from=2026-03-05');
        expect(search).toContain('to=2026-06-04');
        expect(search).toContain('layer=NDVI');
    });

    it('drops the field segment from the URL when the selection is cleared', () => {
        renderHarness('/monitoring/field-analytics/field/field-42?scene=2026-04-27');

        act(() => {
            fireEvent.click(screen.getByTestId('clear-plot'));
        });

        const probe = screen.getByTestId('location-probe');
        expect(probe.getAttribute('data-pathname')).toBe('/monitoring/field-analytics');
        expect(probe.getAttribute('data-search')).toContain('scene=2026-04-27');
    });
});
