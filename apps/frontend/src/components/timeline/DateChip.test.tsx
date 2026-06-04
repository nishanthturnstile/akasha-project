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
                onSelect={ props.onSelect ?? vi.fn() }
            />
        </TooltipProvider>,
    );
    return { date, ...utils };
}

describe('DateChip — Phase E parity', () => {
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
});
