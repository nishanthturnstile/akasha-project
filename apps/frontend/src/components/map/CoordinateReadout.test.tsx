import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import type maplibregl from 'maplibre-gl';
import { CoordinateReadout } from '@/components/map/CoordinateReadout';

type Handler = (event: maplibregl.MapMouseEvent) => void;

function createMockMap({
    renderedFeatures = 1,
    canvasWidth = 800,
}: {
    renderedFeatures?: number;
    canvasWidth?: number;
} = {}) {
    const handlers: Record<string, Handler[]> = {};
    const map = {
        on: (type: string, handler: Handler) => {
            (handlers[type] ??= []).push(handler);
        },
        off: (type: string, handler: Handler) => {
            handlers[type] = (handlers[type] ?? []).filter((h) => h !== handler);
        },
        getCanvas: () => ({ clientWidth: canvasWidth }),
        getLayer: () => ({}),
        queryRenderedFeatures: () => Array.from({ length: renderedFeatures }, () => ({})),
    } as unknown as maplibregl.Map;
    const emit = (type: string, event: Partial<maplibregl.MapMouseEvent>) => {
        const mapEvent = { point: { x: 400, y: 300 }, ...event } as maplibregl.MapMouseEvent;
        (handlers[type] ?? []).forEach((h) => h(mapEvent));
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

    it('shows a precise index value and agronomic class in a cursor popup', async () => {
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
            await Promise.resolve();
        });

        const readout = getByTestId('coordinate-readout');
        const tooltip = getByTestId('index-hover-tooltip');
        expect(lookup).toHaveBeenCalledWith({ lng: 77.5946, lat: 12.9716 });
        expect(readout.textContent).not.toContain('NDVI');
        expect(tooltip.textContent).toContain('NDVI: 0.45');
        expect(tooltip.textContent).toContain('Moderate vegetation');
        expect(tooltip.getAttribute('style')).toContain('left: 400px');
    });

    it('uses the EOS-style sparse vegetation interpretation at NDVI 0.40', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const lookup = vi.fn().mockResolvedValue({
            indexType: 'NDVI',
            value: 0.4,
            masked: false,
        });
        const { getByTestId } = render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', {
                lngLat: { lng: 77.5946, lat: 12.9716 } as maplibregl.LngLat,
                point: { x: 420, y: 300 } as maplibregl.Point,
            });
        });
        await act(async () => {
            await Promise.resolve();
        });

        expect(getByTestId('index-hover-tooltip').textContent).toContain('Sparse vegetation');
    });

    it('reports a known ResourceSat cloud-shadow mask class', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        const lookup = vi.fn().mockResolvedValue({
            indexType: 'NDVI',
            value: null,
            masked: true,
            maskClass: 3,
            sourceId: 'resourcesat-2a-liss3-boa',
        });
        const { getByTestId } = render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', {
                lngLat: { lng: 77.5946, lat: 12.9716 } as maplibregl.LngLat,
                point: { x: 420, y: 300 } as maplibregl.Point,
            });
        });
        await act(async () => {
            await Promise.resolve();
        });

        const tooltip = getByTestId('index-hover-tooltip');
        expect(tooltip.textContent).toContain('NDVI: Masked');
        expect(tooltip.textContent).toContain('Cloud shadow');
    });

    it('does not sample when the pointer is outside the rendered field', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap({ renderedFeatures: 0 });
        const lookup = vi.fn();
        const { queryByTestId } = render(
            <CoordinateReadout
                map={ map }
                interactiveLayerId="selected-field-fill"
                indexLookup={ lookup }
            />,
        );

        act(() => {
            emit('mousemove', {
                lngLat: { lng: 77.5946, lat: 12.9716 } as maplibregl.LngLat,
                point: { x: 420, y: 300 } as maplibregl.Point,
            });
        });

        expect(lookup).not.toHaveBeenCalled();
        expect(queryByTestId('index-hover-tooltip')).toBeNull();
    });

    it('samples the latest animation-frame coordinate immediately', async () => {
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
            await vi.advanceTimersByTimeAsync(0);
            await Promise.resolve();
        });
        expect(lookup).toHaveBeenCalledTimes(1);
        expect(lookup).toHaveBeenCalledWith({ lng: 77.3, lat: 12.3 });
    });

    it('allows one lookup in flight and then samples only the latest queued point', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
            cb(0);
            return 1;
        });
        const { map, emit } = createMockMap();
        let resolveFirst: ((value: { indexType: string; value: number; masked: boolean }) => void) | null = null;
        const lookup = vi.fn()
            .mockImplementationOnce(() => new Promise((resolve) => {
                resolveFirst = resolve;
            }))
            .mockResolvedValue({ indexType: 'NDVI', value: 0.75, masked: false });
        render(<CoordinateReadout map={ map } indexLookup={ lookup } />);

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 13.1 } as maplibregl.LngLat });
            emit('mousemove', { lngLat: { lng: 77.2, lat: 13.2 } as maplibregl.LngLat });
            emit('mousemove', { lngLat: { lng: 77.3, lat: 13.3 } as maplibregl.LngLat });
        });
        expect(lookup).toHaveBeenCalledTimes(1);
        expect(lookup).toHaveBeenLastCalledWith({ lng: 77.1, lat: 13.1 });

        await act(async () => {
            resolveFirst?.({ indexType: 'NDVI', value: 0.45, masked: false });
            await Promise.resolve();
            await vi.advanceTimersByTimeAsync(120);
        });

        expect(lookup).toHaveBeenCalledTimes(2);
        expect(lookup).toHaveBeenLastCalledWith({ lng: 77.3, lat: 13.3 });
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
        const { getByTestId, queryByTestId, rerender } = render(
            <CoordinateReadout map={ map } indexLookup={ lookup } />,
        );

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 13.1 } as maplibregl.LngLat });
        });
        rerender(<CoordinateReadout map={ map } />);
        await act(async () => {
            resolveLookup?.({ indexType: 'NDVI', value: 0.75, masked: false });
            await Promise.resolve();
        });

        expect(getByTestId('coordinate-readout').textContent).not.toContain('NDVI');
        expect(queryByTestId('index-hover-tooltip')).toBeNull();
    });

    it('keeps the popup visible at the moving cursor until the latest value resolves', async () => {
        vi.useFakeTimers();
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => (
            window.setTimeout(() => cb(0), 0) as unknown as number
        ));
        vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id: number) => {
            window.clearTimeout(id);
        });
        const { map, emit } = createMockMap();
        let resolveSecond: ((value: { indexType: string; value: number; masked: boolean }) => void) | null = null;
        const lookup = vi.fn()
            .mockResolvedValueOnce({ indexType: 'NDVI', value: 0.45, masked: false })
            .mockImplementationOnce(() => new Promise((resolve) => {
                resolveSecond = resolve;
            }));
        const { getByTestId } = render(
            <CoordinateReadout map={ map } indexLookup={ lookup } />,
        );

        act(() => {
            emit('mousemove', { lngLat: { lng: 77.1, lat: 13.1 } as maplibregl.LngLat });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(0);
            await Promise.resolve();
        });
        expect(getByTestId('index-hover-tooltip').textContent).toContain('NDVI: 0.45');

        act(() => {
            emit('mousemove', {
                lngLat: { lng: 77.2, lat: 13.2 } as maplibregl.LngLat,
                point: { x: 460, y: 320 } as maplibregl.Point,
            });
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(0);
        });

        const readout = getByTestId('coordinate-readout');
        const tooltip = getByTestId('index-hover-tooltip');
        expect(readout.textContent).toContain('13.2000° N');
        expect(tooltip.textContent).toContain('NDVI: 0.45');
        expect(tooltip.getAttribute('style')).toContain('left: 460px');

        await act(async () => {
            await vi.advanceTimersByTimeAsync(120);
        });
        expect(lookup).toHaveBeenCalledTimes(2);
        expect(getByTestId('index-hover-tooltip').textContent).toContain('NDVI: 0.45');

        await act(async () => {
            resolveSecond?.({ indexType: 'NDVI', value: 0.75, masked: false });
            await Promise.resolve();
        });
        expect(getByTestId('index-hover-tooltip').textContent).toContain('NDVI: 0.75');
        expect(getByTestId('index-hover-tooltip').textContent).toContain('Very dense vegetation');
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
