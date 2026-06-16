import { beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CommandPalette } from '@/components/map/CommandPalette';
import type { SceneDate, Source } from '@/types/api';

const sources: Source[] = [
    {
        id: 'resourcesat-2a-liss3-boa',
        label: 'ResourceSat-2A LISS-3 BOA',
        provider: 'ISRO/NRSC Bhoonidhi',
        kind: 'optical',
    },
    {
        id: 'eos-04-sar-mrs-l2b',
        label: 'EOS-04 SAR MRS L2B',
        provider: 'ISRO/NRSC Bhoonidhi',
        kind: 'sar',
    },
];

const dates: SceneDate[] = [
    {
        acquisitionDate: '2026-05-31',
        datetime: '2026-05-31T05:20:00Z',
        usablePixelPercent: 92,
        cloudMaskedPercent: 8,
        coveragePercent: 100,
        isLatestUsable: true,
        metricsProvisional: false,
        tileAvailable: true,
    },
    {
        acquisitionDate: '2026-05-21',
        datetime: '2026-05-21T05:20:00Z',
        usablePixelPercent: 40,
        cloudMaskedPercent: 60,
        coveragePercent: 100,
        isLatestUsable: false,
        metricsProvisional: false,
        tileAvailable: false, // not selectable
    },
];

beforeAll(() => {
    // cmdk/Radix rely on ResizeObserver, which jsdom doesn't provide.
    globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
});

function renderPalette(overrides: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
    const onSelectSource = vi.fn();
    const onSelectDate = vi.fn();
    const onOpenChange = vi.fn();
    const onToggleLayers = vi.fn();
    render(
        <CommandPalette
            open
            onOpenChange={ onOpenChange }
            sources={ sources }
            activeSourceId="resourcesat-2a-liss3-boa"
            dates={ dates }
            onSelectSource={ onSelectSource }
            onSelectDate={ onSelectDate }
            onToggleLayers={ onToggleLayers }
            { ...overrides }
        />,
    );
    return { onSelectSource, onSelectDate, onOpenChange, onToggleLayers };
}

describe('CommandPalette', () => {
    it('lists sources and only tile-available dates when open', () => {
        renderPalette();
        expect(screen.getByTestId('command-palette')).toBeTruthy();
        expect(screen.getByTestId('command-source-resourcesat-2a-liss3-boa')).toBeTruthy();
        expect(screen.getByTestId('command-source-eos-04-sar-mrs-l2b')).toBeTruthy();
        expect(screen.getByTestId('command-date-2026-05-31')).toBeTruthy();
        expect(screen.queryByTestId('command-date-2026-05-21')).toBeNull();
    });

    it('selecting a source notifies and closes', () => {
        const { onSelectSource, onOpenChange } = renderPalette();
        fireEvent.click(screen.getByTestId('command-source-eos-04-sar-mrs-l2b'));
        expect(onSelectSource).toHaveBeenCalledWith('eos-04-sar-mrs-l2b');
        expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it('selecting a date notifies and closes', () => {
        const { onSelectDate, onOpenChange } = renderPalette();
        fireEvent.click(screen.getByTestId('command-date-2026-05-31'));
        expect(onSelectDate).toHaveBeenCalledWith('2026-05-31');
        expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it('toggle-layers action fires the callback', () => {
        const { onToggleLayers } = renderPalette();
        fireEvent.click(screen.getByTestId('command-toggle-layers'));
        expect(onToggleLayers).toHaveBeenCalledTimes(1);
    });

    it('renders nothing while closed', () => {
        renderPalette({ open: false });
        expect(screen.queryByTestId('command-palette')).toBeNull();
    });
});
