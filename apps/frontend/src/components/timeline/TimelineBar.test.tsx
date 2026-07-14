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
                nextExpectedAcquisitionDate={ props.nextExpectedAcquisitionDate ?? null }
                loading={ props.loading ?? false }
                error={ props.error ?? null }
                onRetry={ props.onRetry ?? vi.fn() }
                periodFrom={ props.periodFrom ?? null }
                periodTo={ props.periodTo ?? null }
                onPeriodChange={ props.onPeriodChange }
                bestMode={ props.bestMode ?? false }
                onBestModeChange={ props.onBestModeChange }
            />
        </TooltipProvider>,
    );
}

describe('TimelineBar — date navigation behavior', () => {
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

    it('renders the BFF-projected strictly future expected pass', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-07-14T12:00:00Z'));
        try {
            renderBar({ nextExpectedAcquisitionDate: '2026-07-18' });
            const next = screen.getByTestId('timeline-next-image');
            expect(next.textContent).toContain('Next expected pass');
            expect(next.textContent).toContain('Jul 18, 2026');
        } finally {
            vi.useRealTimers();
        }
    });

    it('does not infer a pass from historical field dates', () => {
        renderBar({ nextExpectedAcquisitionDate: null });
        expect(screen.queryByTestId('timeline-next-image')).toBeNull();
    });

    it('fails closed when the BFF projection is today or in the past', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-07-14T12:00:00Z'));
        try {
            const { rerender } = renderBar({ nextExpectedAcquisitionDate: '2026-05-17' });
            expect(screen.queryByTestId('timeline-next-image')).toBeNull();
            rerender(
                <TooltipProvider>
                    <TimelineBar
                        dates={ dates }
                        selectedDate="2026-05-11"
                        onSelect={ vi.fn() }
                        sourceKind="optical"
                        nextExpectedAcquisitionDate="2026-07-14"
                        loading={ false }
                        error={ null }
                        onRetry={ vi.fn() }
                    />
                </TooltipProvider>,
            );
            expect(screen.queryByTestId('timeline-next-image')).toBeNull();
        } finally {
            vi.useRealTimers();
        }
    });

    it('does not show an expected pass for archive or best-available mode', () => {
        const { rerender } = renderBar({
            sourceKind: 'archive',
            nextExpectedAcquisitionDate: '2099-07-18',
        });
        expect(screen.queryByTestId('timeline-next-image')).toBeNull();
        rerender(
            <TooltipProvider>
                <TimelineBar
                    dates={ dates }
                    selectedDate="2026-05-11"
                    onSelect={ vi.fn() }
                    sourceKind="optical"
                    nextExpectedAcquisitionDate="2099-07-18"
                    loading={ false }
                    error={ null }
                    onRetry={ vi.fn() }
                    bestMode
                />
            </TooltipProvider>,
        );
        expect(screen.queryByTestId('timeline-next-image')).toBeNull();
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

    // --- TASK-072: Best-mode and provenance label behavior (outcomes 4, 5, 6) ---

    it('renders the best mode toggle button when onBestModeChange is provided', () => {
        renderBar({ onBestModeChange: vi.fn() });
        expect(screen.getByTestId('timeline-best-mode-toggle')).toBeTruthy();
    });

    it('labels the best mode toggle with the current timeline mode', () => {
        const { rerender } = renderBar({ onBestModeChange: vi.fn(), bestMode: false });
        expect(screen.getByTestId('timeline-best-mode-toggle').textContent).toContain('Source');

        rerender(
            <TooltipProvider>
                <TimelineBar
                    dates={ dates }
                    selectedDate="2026-05-11"
                    onSelect={ vi.fn() }
                    sourceKind="optical"
                    sensorBadge={ null }
                    loading={ false }
                    error={ null }
                    onRetry={ vi.fn() }
                    bestMode
                    onBestModeChange={ vi.fn() }
                />
            </TooltipProvider>,
        );
        expect(screen.getByTestId('timeline-best-mode-toggle').textContent).toContain('Best');
    });

    it('does not render the best mode toggle when onBestModeChange is not provided', () => {
        renderBar();
        expect(screen.queryByTestId('timeline-best-mode-toggle')).toBeNull();
    });

    it('in best mode passes per-chip provenance labels from date.provenanceLabel and suppresses sensorBadge', () => {
        const datesWithProv: SceneDate[] = [
            makeDate('2026-05-11', { isLatestUsable: true, provenanceLabel: 'LISS-4 · 5.8 m' }),
        ];
        renderBar({
            dates: datesWithProv,
            bestMode: true,
            sensorBadge: 'L3',
            selectedDate: '2026-05-11',
        });
        // Provenance label must render.
        expect(screen.getByTestId('date-chip-provenance-2026-05-11').textContent).toBe('LISS-4 · 5.8 m');
        // Global sensorBadge must be suppressed in best mode.
        expect(screen.queryByTestId('date-chip-sensor-2026-05-11')).toBeNull();
    });

    it('in source-specific mode (default) shows the global sensorBadge and no provenance labels', () => {
        // Default: bestMode=false, no provenanceLabel on date objects.
        renderBar({ sensorBadge: 'L3', selectedDate: '2026-05-11' });
        expect(screen.getByTestId('date-chip-sensor-2026-05-11').textContent).toBe('L3');
        expect(screen.queryByTestId('date-chip-provenance-2026-05-11')).toBeNull();
    });
});
