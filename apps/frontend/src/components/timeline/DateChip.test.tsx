import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { DateChip } from '@/components/timeline/DateChip';
import type { SceneDate } from '@/types/api';

function makeDate(overrides: Partial<SceneDate> = {}): SceneDate {
    return {
        acquisitionDate: '2026-05-11',
        datetime: '2026-05-11T05:20:00Z',
        usablePixelPercent: 92,
        cloudMaskedPercent: 8,
        coveragePercent: 100,
        isLatestUsable: false,
        metricsProvisional: false,
        tileAvailable: true,
        ...overrides,
    };
}

function renderChip(props: Partial<React.ComponentProps<typeof DateChip>> = {}) {
    const date = props.date ?? makeDate();
    const utils = render(
        <TooltipProvider>
            <DateChip
                date={ date }
                selected={ props.selected ?? false }
                sourceKind={ props.sourceKind ?? 'optical' }
                sensorBadge={ props.sensorBadge }
                provenanceLabel={ props.provenanceLabel }
                onSelect={ props.onSelect ?? vi.fn() }
            />
        </TooltipProvider>,
    );
    return { date, ...utils };
}

describe('DateChip — timeline chip behavior', () => {
    it('renders the sensor badge from the global override on optical chips', () => {
        const { getByTestId } = renderChip({ sensorBadge: 'S2' });
        const badge = getByTestId('date-chip-sensor-2026-05-11');
        expect(badge.textContent).toBe('S2');
    });

    it('prefers a per-date sensor when no override is provided', () => {
        const { getByTestId } = renderChip({ date: makeDate({ sensor: 'S2A' }) });
        expect(getByTestId('date-chip-sensor-2026-05-11').textContent).toBe('S2A');
    });

    it('shows a cloud icon when cloudMaskedPercent crosses the cloudy threshold', () => {
        const { getByTestId } = renderChip({ date: makeDate({ cloudMaskedPercent: 65 }) });
        expect(getByTestId('date-chip-cloud-2026-05-11')).toBeTruthy();
    });

    it('hides the cloud icon for clear optical scenes', () => {
        const { queryByTestId } = renderChip({ date: makeDate({ cloudMaskedPercent: 5 }) });
        expect(queryByTestId('date-chip-cloud-2026-05-11')).toBeNull();
    });

    it('never renders the cloud icon or sensor badge on SAR chips', () => {
        const { queryByTestId } = renderChip({
            sourceKind: 'sar',
            sensorBadge: 'S1',
            date: makeDate({ cloudMaskedPercent: 80 }),
        });
        expect(queryByTestId('date-chip-cloud-2026-05-11')).toBeNull();
        expect(queryByTestId('date-chip-sensor-2026-05-11')).toBeNull();
    });

    it('uses coverage semantics for context chips', () => {
        const { getByTestId, queryByTestId } = renderChip({
            sourceKind: 'context',
            sensorBadge: 'OCM',
            date: makeDate({ cloudMaskedPercent: 80, coveragePercent: 76 }),
        });
        expect(queryByTestId('date-chip-cloud-2026-05-11')).toBeNull();
        expect(queryByTestId('date-chip-sensor-2026-05-11')).toBeNull();
        expect(getByTestId('context-coverage-chip').textContent).toContain('76% coverage');
    });

    it('marks unavailable dates with the backend reason instead of the cloud glyph', () => {
        const { getByRole, getByTestId, queryByTestId } = renderChip({
            date: makeDate({
                tileAvailable: false,
                cloudMaskedPercent: 80,
                unavailableReason: 'Required raster assets are missing for this date: mask.',
            }),
        });
        const button = getByRole('option', {
            name: /Required raster assets are missing for this date: mask\./,
        });
        expect((button as HTMLButtonElement).disabled).toBe(true);
        expect(button.getAttribute('title')).toBe(
            'Required raster assets are missing for this date: mask.',
        );
        expect(getByTestId('date-chip-unavailable-2026-05-11')).toBeTruthy();
        expect(queryByTestId('date-chip-cloud-2026-05-11')).toBeNull();
    });

    // --- TASK-072: Provenance label rendering (outcome 6) ---

    it('renders a LISS-4 provenance label (LISS-4 · 5.8 m) from the provenanceLabel prop', () => {
        const { getByTestId, queryByTestId } = renderChip({ provenanceLabel: 'LISS-4 · 5.8 m' });
        expect(getByTestId('date-chip-provenance-2026-05-11').textContent).toBe('LISS-4 · 5.8 m');
        // Provenance preempts sensor badge.
        expect(queryByTestId('date-chip-sensor-2026-05-11')).toBeNull();
    });

    it('renders a LISS-3 provenance label (LISS-3 · 24 m)', () => {
        const { getByTestId } = renderChip({ provenanceLabel: 'LISS-3 · 24 m' });
        expect(getByTestId('date-chip-provenance-2026-05-11').textContent).toBe('LISS-3 · 24 m');
    });

    it('renders an AWiFS coarse provenance label (AWiFS · 56 m · coarse)', () => {
        const { getByTestId } = renderChip({ provenanceLabel: 'AWiFS · 56 m · coarse' });
        expect(getByTestId('date-chip-provenance-2026-05-11').textContent).toBe('AWiFS · 56 m · coarse');
    });

    it('shows provenance label instead of sensor badge when both are provided', () => {
        const { getByTestId, queryByTestId } = renderChip({
            provenanceLabel: 'LISS-4 · 5.8 m',
            sensorBadge: 'L4',
        });
        expect(getByTestId('date-chip-provenance-2026-05-11').textContent).toBe('LISS-4 · 5.8 m');
        expect(queryByTestId('date-chip-sensor-2026-05-11')).toBeNull();
    });
});
