import { act, render, screen } from '@testing-library/react';
import type maplibregl from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';
import { FieldOverlayLoadingIndicator } from '@/components/map/FieldOverlayLoadingIndicator';
import type { Plot } from '@/types/api';

type Handler = () => void;

function createMockMap(project = vi.fn(() => ({ x: 120, y: 80 }))) {
    const handlers: Record<string, Handler[]> = {};
    const map = {
        on: (type: string, handler: Handler) => {
            (handlers[type] ??= []).push(handler);
        },
        off: (type: string, handler: Handler) => {
            handlers[type] = (handlers[type] ?? []).filter((h) => h !== handler);
        },
        project,
    } as unknown as maplibregl.Map;
    const emit = (type: string) => {
        (handlers[type] ?? []).forEach((handler) => handler());
    };
    return { emit, map, project };
}

const plot: Pick<Plot, 'geometry'> = {
    geometry: {
        type: 'Polygon',
        coordinates: [[
            [77, 12],
            [78, 12],
            [78, 13],
            [77, 13],
            [77, 12],
        ]],
    },
};

describe('FieldOverlayLoadingIndicator', () => {
    it('renders a non-blocking calculating chip centered on the field bbox', () => {
        const { map, project } = createMockMap();

        render(<FieldOverlayLoadingIndicator loading map={ map } plot={ plot } />);

        const indicator = screen.getByTestId('field-overlay-loading-indicator');
        expect(indicator.textContent).toContain('Calculating index…');
        expect(indicator.className).toContain('pointer-events-none');
        expect(indicator.style.left).toBe('120px');
        expect(indicator.style.top).toBe('80px');
        expect(project).toHaveBeenCalledWith([77.5, 12.5]);
    });

    it('reprojects the chip when the map moves', () => {
        const project = vi
            .fn()
            .mockReturnValueOnce({ x: 120, y: 80 })
            .mockReturnValueOnce({ x: 140, y: 92 });
        const { emit, map } = createMockMap(project);

        render(<FieldOverlayLoadingIndicator loading map={ map } plot={ plot } />);
        expect(screen.getByTestId('field-overlay-loading-indicator').style.left).toBe('120px');
        expect(screen.getByTestId('field-overlay-loading-indicator').style.top).toBe('80px');

        act(() => {
            emit('move');
        });

        expect(screen.getByTestId('field-overlay-loading-indicator').style.left).toBe('140px');
        expect(screen.getByTestId('field-overlay-loading-indicator').style.top).toBe('92px');
    });

    it('renders nothing until an overlay recalculation is active', () => {
        const { map } = createMockMap();

        const { rerender } = render(<FieldOverlayLoadingIndicator loading={ false } map={ map } plot={ plot } />);
        expect(screen.queryByTestId('field-overlay-loading-indicator')).toBeNull();

        rerender(<FieldOverlayLoadingIndicator loading map={ null } plot={ plot } />);
        expect(screen.queryByTestId('field-overlay-loading-indicator')).toBeNull();

        rerender(<FieldOverlayLoadingIndicator loading map={ map } plot={ null } />);
        expect(screen.queryByTestId('field-overlay-loading-indicator')).toBeNull();
    });
});