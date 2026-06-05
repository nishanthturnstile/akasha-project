import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { CalendarRangePicker } from '@/components/timeline/CalendarRangePicker';

function renderPicker(props: Partial<React.ComponentProps<typeof CalendarRangePicker>> = {}) {
    const onChange = vi.fn();
    const utils = render(
        <TooltipProvider>
            <CalendarRangePicker
                from={ props.from ?? null }
                to={ props.to ?? null }
                onChange={ props.onChange ?? onChange }
                disabled={ props.disabled }
            />
        </TooltipProvider>,
    );
    return { onChange, ...utils };
}

describe('CalendarRangePicker', () => {
    it('renders a calendar trigger with no label when range is empty', () => {
        renderPicker();
        const trigger = screen.getByTestId('timeline-period-trigger');
        expect(trigger.getAttribute('aria-expanded')).toBe('false');
        expect(trigger.getAttribute('data-active')).toBe('false');
        expect(screen.queryByTestId('timeline-period-popover')).toBeNull();
    });

    it('shows a short range label when bounds are set', () => {
        renderPicker({ from: '2026-03-05', to: '2026-06-04' });
        const trigger = screen.getByTestId('timeline-period-trigger');
        expect(trigger.getAttribute('data-active')).toBe('true');
        expect(trigger.textContent).toContain('Mar 5');
        expect(trigger.textContent).toContain('Jun 4');
    });

    it('opens the popover and applies a new range', () => {
        const { onChange } = renderPicker();
        fireEvent.click(screen.getByTestId('timeline-period-trigger'));
        const from = screen.getByTestId('timeline-period-from') as HTMLInputElement;
        const to = screen.getByTestId('timeline-period-to') as HTMLInputElement;
        fireEvent.change(from, { target: { value: '2026-03-05' } });
        fireEvent.change(to, { target: { value: '2026-06-04' } });
        fireEvent.click(screen.getByTestId('timeline-period-apply'));
        expect(onChange).toHaveBeenCalledWith('2026-03-05', '2026-06-04');
    });

    it('normalises inverted ranges before applying', () => {
        const { onChange } = renderPicker();
        fireEvent.click(screen.getByTestId('timeline-period-trigger'));
        const from = screen.getByTestId('timeline-period-from') as HTMLInputElement;
        const to = screen.getByTestId('timeline-period-to') as HTMLInputElement;
        // Bypass the input's own `max=draftTo` clamp by setting `to` first, then a later `from`.
        fireEvent.change(to, { target: { value: '2026-03-05' } });
        fireEvent.change(from, { target: { value: '2026-06-04' } });
        fireEvent.click(screen.getByTestId('timeline-period-apply'));
        expect(onChange).toHaveBeenCalledWith('2026-03-05', '2026-06-04');
    });

    it('clears the range and closes the popover', () => {
        const { onChange } = renderPicker({ from: '2026-03-05', to: '2026-06-04' });
        fireEvent.click(screen.getByTestId('timeline-period-trigger'));
        fireEvent.click(screen.getByTestId('timeline-period-clear'));
        expect(onChange).toHaveBeenCalledWith(null, null);
        expect(screen.queryByTestId('timeline-period-popover')).toBeNull();
    });

    it('is disabled when no dates are loaded', () => {
        renderPicker({ disabled: true });
        const trigger = screen.getByTestId('timeline-period-trigger') as HTMLButtonElement;
        expect(trigger.disabled).toBe(true);
    });
});
