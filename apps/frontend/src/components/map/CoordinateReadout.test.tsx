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
        vi.useRealTimers();
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

    it('shows a precise index value when a hover lookup is provided', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const lookup = vi.fn().mockResolvedValue({ indexType: 'NDVI', value: 0.45, masked: false });
        const { getByTestId } = render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.5946, lat: 12.9716 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(180);
            await Promise.resolve();
        });

        const readout = getByTestId('coordinate-readout');
        expect(lookup).toHaveBeenCalledWith({ lng: 77.5946, lat: 12.9716 });
        expect(readout.textContent).toContain('NDVI 0.45');
    });

    it('debounces rapid hover lookups and samples the latest coordinate', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => (
            window.setTimeout(() => cb(0), 0) as unknown as number
        ));
        vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id: number) => {
            window.clearTimeout(id);
        });
        const { map, emit } = createMockMap();
        const lookup = vi.fn().mockResolvedValue({ indexType: 'NDVI', value: 0.45, masked: false });
        render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 12.1 } as maplibregl.LngLat });
            emit('mousemove', { lngLat: { lng: 77.2, lat: 12.2 } as maplibregl.LngLat });
            emit('mousemove', { lngLat: { lng: 77.3, lat: 12.3 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(179);
        });
        expect(lookup).not.toHaveBeenCalled();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(1);
        });
        expect(lookup).toHaveBeenCalledTimes(1);
        expect(lookup).toHaveBeenCalledWith({ lng: 77.3, lat: 12.3 });
    });

    it('discards a late lookup result when the lookup source changes', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        let resolveLookup: ((value: { indexType: string; value: number; masked: boolean }) => void) | null = null;
        const lookup = vi.fn().mockImplementation(() => new Promise((resolve) => {
            resolveLookup = resolve;
        }));
        const { getByTestId, rerender } = render(
            <CoordinateReadout map={ map } indexLookup={ lookup } />,
        );

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 13.1 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(180);
        });
        rerender(<CoordinateReadout map={ map } />);
        await act(async () => {
            resolveLookup?.({ indexType: 'NDVI', value: 0.75, masked: false });
            await Promise.resolve();
        });

        expect(getByTestId('coordinate-readout').textContent).not.toContain('NDVI 0.75');
    });

    it('does not show the previous point value beside new cursor coordinates', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => (
            window.setTimeout(() => cb(0), 0) as unknown as number
        ));
        vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id: number) => {
            window.clearTimeout(id);
        });
        const { map, emit } = createMockMap();
        const lookup = vi.fn().mockResolvedValue({ indexType: 'NDVI', value: 0.45, masked: false });
        const { getByTestId } = render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 13.1 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(0);
            await vi.advanceTimersByTimeAsync(180);
            await Promise.resolve();
        });
        expect(getByTestId('coordinate-readout').textContent).toContain('NDVI 0.45');

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.2, lat: 13.2 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(0);
        });

        const readout = getByTestId('coordinate-readout');
        expect(readout.textContent).toContain('13.2000° N');
        expect(readout.textContent).not.toContain('NDVI 0.45');
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
