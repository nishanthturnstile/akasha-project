import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { MeasureTool } from '@/components/map/MeasureTool';

// With map=null the tool never instantiates Terra Draw, so these tests exercise
// the toggle/disclosure UI without touching the (browser-only) draw engine.
describe('MeasureTool', () => {
    it('renders a collapsed toggle by default', () => {
        const { getByTestId } = render(<MeasureTool map={ null } />);
        const toggle = getByTestId('measure-toggle');
        expect(toggle.getAttribute('aria-expanded')).toBe('false');
    });

    it('expands to start measurement mode', () => {
        const { getByTestId } = render(<MeasureTool map={ null } />);
        const toggle = getByTestId('measure-toggle');
        fireEvent.click(toggle);
        expect(toggle.getAttribute('aria-expanded')).toBe('true');
        expect(getByTestId('measure-mode-picker')).toBeTruthy();
        expect(getByTestId('measure-distance-mode').getAttribute('aria-pressed')).toBe('true');
    });

    it('lets the user choose area instead of tracing an open distance path', () => {
        const { getByTestId } = render(<MeasureTool map={ null } />);
        fireEvent.click(getByTestId('measure-toggle'));
        fireEvent.click(getByTestId('measure-area-mode'));
        expect(getByTestId('measure-area-mode').getAttribute('aria-pressed')).toBe('true');
        expect(getByTestId('measure-distance-mode').getAttribute('aria-pressed')).toBe('false');
    });

    it('collapses again when toggled off', () => {
        const { getByTestId } = render(<MeasureTool map={ null } />);
        const toggle = getByTestId('measure-toggle');
        fireEvent.click(toggle);
        fireEvent.click(toggle);
        expect(toggle.getAttribute('aria-expanded')).toBe('false');
    });
});
