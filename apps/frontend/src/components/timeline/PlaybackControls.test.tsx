import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render } from '@testing-library/react';
import { PlaybackControls } from '@/components/timeline/PlaybackControls';
import type { SceneDate } from '@/types/api';

function makeDate(acquisitionDate: string): SceneDate {
    return {
        acquisitionDate,
        datetime: `${acquisitionDate}T05:20:00Z`,
        usablePixelPercent: 90,
        cloudMaskedPercent: 10,
        coveragePercent: 100,
        isLatestUsable: false,
        metricsProvisional: false,
        tileAvailable: true,
    };
}

const dates = [makeDate('2026-05-01'), makeDate('2026-05-11'), makeDate('2026-05-21')];

describe('PlaybackControls', () => {
    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('disables play when fewer than two dates are selectable', () => {
        const { getByTestId } = render(
            <PlaybackControls dates={ [dates[0]] } selectedDate="2026-05-01" onSelect={ vi.fn() } />,
        );
        expect((getByTestId('playback-toggle') as HTMLButtonElement).disabled).toBe(true);
    });

    it('advances to the next date on each tick while playing', () => {
        vi.useFakeTimers();
        const onSelect = vi.fn();
        const { getByTestId } = render(
            <PlaybackControls dates={ dates } selectedDate="2026-05-01" onSelect={ onSelect } />,
        );
        fireEvent.click(getByTestId('playback-toggle'));
        act(() => {
            vi.advanceTimersByTime(1400);
        });
        expect(onSelect).toHaveBeenCalledWith('2026-05-11');
    });

    it('cycles speed labels', () => {
        const { getByTestId } = render(
            <PlaybackControls dates={ dates } selectedDate="2026-05-01" onSelect={ vi.fn() } />,
        );
        const speed = getByTestId('playback-speed');
        expect(speed.textContent).toContain('1×');
        fireEvent.click(speed);
        expect(speed.textContent).toContain('2×');
    });
});
