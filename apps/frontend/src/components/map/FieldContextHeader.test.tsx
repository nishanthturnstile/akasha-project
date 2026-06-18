import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { describe, expect, it, vi } from 'vitest';

import { FieldContextHeader } from '@/components/map/FieldContextHeader';
import type { Plot } from '@/types/api';

const plot: Plot = {
    id: 'plot-1',
    name: 'North bay field',
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
    areaHa: 42.3,
    cropType: 'Maize',
    variety: 'Hybrid 7',
    seasonLabel: 'Season 2',
    createdAt: null,
    updatedAt: null,
};

function renderHeader(overrides: Partial<Parameters<typeof FieldContextHeader>[0]> = {}) {
    const props = {
        selectedPlot: plot,
        onBack: vi.fn(),
        onEditGeometry: vi.fn(),
        onOpenCommand: vi.fn(),
        onGetOverview: vi.fn(),
        ...overrides,
    };
    render(<FieldContextHeader { ...props } />);
    return props;
}

describe('FieldContextHeader', () => {
    it('renders selected field name, server area, and crop line', () => {
        renderHeader();

        expect(screen.getByTestId('field-header-name').textContent).toBe('North bay field');
        // Area is rendered from the server-validated `areaHa` only (REQ-008).
        expect(screen.getByTestId('field-header-area').textContent).toBe('42.3 ha');
        expect(screen.getByText('Maize · Hybrid 7 · Season 2')).toBeTruthy();
    });

    it('disables back/edit and shows an em-dash when no field is selected', () => {
        renderHeader({ selectedPlot: null });

        const back = screen.getByTestId('field-header-back') as HTMLButtonElement;
        const edit = screen.getByTestId('field-header-edit') as HTMLButtonElement;
        expect(back.disabled).toBe(true);
        expect(edit.disabled).toBe(true);
        expect(screen.getByTestId('field-header-area').textContent).toBe('—');
        expect(screen.getByTestId('field-header-name').textContent).toBe('No field selected');
    });

    it('wires the back / edit / command callbacks', () => {
        const props = renderHeader();

        fireEvent.click(screen.getByTestId('field-header-back'));
        fireEvent.click(screen.getByTestId('field-header-edit'));
        fireEvent.click(screen.getByTestId('command-trigger'));

        expect(props.onBack).toHaveBeenCalledTimes(1);
        expect(props.onEditGeometry).toHaveBeenCalledTimes(1);
        expect(props.onOpenCommand).toHaveBeenCalledTimes(1);
    });

    it('disables the Overview placeholder (plan-gated entry-point)', () => {
        renderHeader();
        const overview = screen.getByTestId('field-header-overview') as HTMLButtonElement;
        expect(overview.disabled).toBe(true);
    });
});
