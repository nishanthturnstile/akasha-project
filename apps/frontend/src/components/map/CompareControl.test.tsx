import { beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { CompareControl } from '@/components/map/CompareControl';
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

beforeAll(() => {
    // Radix Slider relies on ResizeObserver, absent in jsdom.
    globalThis.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
});

function setup(overrides: Partial<React.ComponentProps<typeof CompareControl>> = {}) {
    const onEnabledChange = vi.fn();
    const onCompareDateChange = vi.fn();
    const onBlendChange = vi.fn();
    const utils = render(
        <CompareControl
            enabled={ false }
            onEnabledChange={ onEnabledChange }
            dates={ dates }
            activeDate="2026-05-21"
            compareDate={ null }
            onCompareDateChange={ onCompareDateChange }
            blend={ 60 }
            onBlendChange={ onBlendChange }
            { ...overrides }
        />,
    );
    return { ...utils, onEnabledChange, onCompareDateChange, onBlendChange };
}

describe('CompareControl', () => {
    it('is collapsed by default', () => {
        const { getByTestId, queryByTestId } = setup();
        expect(getByTestId('compare-toggle').getAttribute('aria-expanded')).toBe('false');
        expect(queryByTestId('compare-panel')).toBeNull();
    });

    it('expands to show the enable switch', () => {
        const { getByTestId } = setup();
        fireEvent.click(getByTestId('compare-toggle'));
        expect(getByTestId('compare-panel')).toBeTruthy();
        expect(getByTestId('compare-switch')).toBeTruthy();
    });

    it('lists B dates excluding the active date when enabled', () => {
        const { getByTestId, queryByTestId } = setup({ enabled: true });
        fireEvent.click(getByTestId('compare-toggle'));
        expect(getByTestId('compare-date-2026-05-01')).toBeTruthy();
        expect(getByTestId('compare-date-2026-05-11')).toBeTruthy();
        // The active ("A") date is not offered as B.
        expect(queryByTestId('compare-date-2026-05-21')).toBeNull();
    });

    it('selecting a B date notifies the parent', () => {
        const { getByTestId, onCompareDateChange } = setup({ enabled: true });
        fireEvent.click(getByTestId('compare-toggle'));
        fireEvent.click(getByTestId('compare-date-2026-05-11'));
        expect(onCompareDateChange).toHaveBeenCalledWith('2026-05-11');
    });
});
