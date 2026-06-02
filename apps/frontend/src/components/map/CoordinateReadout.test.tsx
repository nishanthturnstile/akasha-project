import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import type maplibregl from 'maplibre-gl';
import { CoordinateReadout } from '@/components/map/CoordinateReadout';

type Handler = (event: maplibregl.MapMouseEvent) => void;

function createMockMap() {
    const handlers: Record<string, Handler[]> = {};
    const map = {
        on: (type: string, handler: Handler) => {
            (handlers[type] ??= []).push(handler);
        },
        off: (type: string, handler: Handler) => {
            handlers[type] = (handlers[type] ?? []).filter((h) => h !== handler);
        },
    } as unknown as maplibregl.Map;
    const emit = (type: string, event: Partial<maplibregl.MapMouseEvent>) => {
        (handlers[type] ?? []).forEach((h) => h(event as maplibregl.MapMouseEvent));
    };
    return { map, emit };
}

describe('CoordinateReadout', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('renders nothing before the pointer enters the map', () => {
        const { map } = createMockMap();
        const { queryByTestId } = render(<CoordinateReadout map={ map } />);
        expect(queryByTestId('coordinate-readout')).toBeNull();
    });

    it('shows formatted lng/lat with hemispheres on mousemove', () => {
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const { getByTestId } = render(<CoordinateReadout map={ map } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.5946, lat: 12.9716 } as maplibregl.LngLat });
        });

        const readout = getByTestId('coordinate-readout');
        expect(readout.textContent).toContain('12.9716° N');
        expect(readout.textContent).toContain('77.5946° E');
    });

    it('uses S/W hemispheres for negative coordinates', () => {
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const { getByTestId } = render(<CoordinateReadout map={ map } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: -43.1729, lat: -22.9068 } as maplibregl.LngLat });
        });

        const readout = getByTestId('coordinate-readout');
        expect(readout.textContent).toContain('22.9068° S');
        expect(readout.textContent).toContain('43.1729° W');
    });

    it('clears the readout when the pointer leaves the map', () => {
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const { queryByTestId } = render(<CoordinateReadout map={ map } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 10, lat: 20 } as maplibregl.LngLat });
        });
        expect(queryByTestId('coordinate-readout')).not.toBeNull();

        act(() => {
            emit('mouseout', {});
        });
        expect(queryByTestId('coordinate-readout')).toBeNull();
    });

    it('does not throw without a map', () => {
        expect(() => render(<CoordinateReadout map={ null } />)).not.toThrow();
    });
});
