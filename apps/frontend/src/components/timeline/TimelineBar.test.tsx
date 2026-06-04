import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { TimelineBar } from '@/components/timeline/TimelineBar';
import type { SceneDate } from '@/types/api';

function makeDate(acquisitionDate: string, overrides: Partial<SceneDate> = {}): SceneDate {
    return {
        acquisitionDate,
        datetime: `${acquisitionDate}T05:20:00Z`,
        usablePixelPercent: 90,
        cloudMaskedPercent: 10,
        coveragePercent: 100,
        isLatestUsable: false,
        metricsProvisional: false,
        tileAvailable: true,
        ...overrides,
    };
}

const dates: SceneDate[] = [
    makeDate('2026-03-01'),
    makeDate('2026-04-10'),
    makeDate('2026-05-11', { isLatestUsable: true }),
];

function renderBar(props: Partial<React.ComponentProps<typeof TimelineBar>> = {}) {
    return render(
        <TooltipProvider>
            <TimelineBar
                dates={ props.dates ?? dates }
                selectedDate={ 'selectedDate' in props ? (props.selectedDate as string | null) : '2026-05-11' }
                onSelect={ props.onSelect ?? vi.fn() }
                sourceKind={ props.sourceKind ?? 'optical' }
                sensorBadge={ props.sensorBadge ?? null }
                loading={ props.loading ?? false }
                error={ props.error ?? null }
                onRetry={ props.onRetry ?? vi.fn() }
                periodFrom={ props.periodFrom ?? null }
                periodTo={ props.periodTo ?? null }
                onPeriodChange={ props.onPeriodChange }
            />
        </TooltipProvider>,
    );
}

describe('TimelineBar — Phase E parity', () => {
    it('renders the calendar trigger only when onPeriodChange is provided', () => {
        renderBar({ onPeriodChange: vi.fn() });
        expect(screen.getByTestId('timeline-period-trigger')).toBeTruthy();
    });

    it('hides the calendar trigger when no period handler is wired', () => {
        renderBar();
        expect(screen.queryByTestId('timeline-period-trigger')).toBeNull();
    });

    it('filters chips outside the period but always keeps the selected chip', () => {
        renderBar({
            onPeriodChange: vi.fn(),
            periodFrom: '2026-04-01',
            periodTo: '2026-04-30',
            selectedDate: '2026-05-11',
        });
        // March chip is filtered out, but May chip is kept because it is selected.
        expect(screen.queryByTestId('date-chip-2026-03-01')).toBeNull();
        expect(screen.getByTestId('date-chip-2026-04-10')).toBeTruthy();
        expect(screen.getByTestId('date-chip-2026-05-11')).toBeTruthy();
    });

    it('shows the empty-period notice when no dates match the filter and nothing is selected', () => {
        renderBar({
            onPeriodChange: vi.fn(),
            periodFrom: '2027-01-01',
            periodTo: '2027-02-01',
            selectedDate: null,
        });
        expect(screen.getByTestId('timeline-empty-period')).toBeTruthy();
    });

    it('projects the next image using a 5-day cadence for optical sources', () => {
        renderBar();
        const next = screen.getByTestId('timeline-next-image');
        // Latest is 2026-05-11 → +5d → May 16, 2026.
        expect(next.textContent).toContain('May 16, 2026');
    });

    it('projects the next image using a 6-day cadence for SAR sources', () => {
        renderBar({ sourceKind: 'sar' });
        const next = screen.getByTestId('timeline-next-image');
        // 2026-05-11 → +6d → May 17, 2026.
        expect(next.textContent).toContain('May 17, 2026');
    });

    it('opens the calendar popover and emits the chosen range', () => {
        const onPeriodChange = vi.fn();
        renderBar({ onPeriodChange });
        fireEvent.click(screen.getByTestId('timeline-period-trigger'));
        fireEvent.change(screen.getByTestId('timeline-period-from'), {
            target: { value: '2026-04-01' },
        });
        fireEvent.change(screen.getByTestId('timeline-period-to'), {
            target: { value: '2026-04-30' },
        });
        fireEvent.click(screen.getByTestId('timeline-period-apply'));
        expect(onPeriodChange).toHaveBeenCalledWith('2026-04-01', '2026-04-30');
    });
});
