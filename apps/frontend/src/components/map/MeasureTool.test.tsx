import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { MeasureTool } from '@/components/map/MeasureTool';

// With map=null the tool never instantiates Terra Draw, so these tests exercise
// the toggle/disclosure UI without touching the (browser-only) draw engine.
describe('MeasureTool', () => {
    it('renders a collapsed toggle by default', () => {
        const { getByTestId, queryByTestId } = render(<MeasureTool map={ null } />);
        const toggle = getByTestId('measure-toggle');
        expect(toggle.getAttribute('aria-expanded')).toBe('false');
        expect(queryByTestId('measure-panel')).toBeNull();
    });

    it('expands to reveal distance and area modes', () => {
        const { getByTestId } = render(<MeasureTool map={ null } />);
        fireEvent.click(getByTestId('measure-toggle'));
        expect(getByTestId('measure-panel')).toBeTruthy();
        expect(getByTestId('measure-distance-btn')).toBeTruthy();
        expect(getByTestId('measure-area-btn')).toBeTruthy();
    });

    it('collapses again when toggled off', () => {
        const { getByTestId, queryByTestId } = render(<MeasureTool map={ null } />);
        const toggle = getByTestId('measure-toggle');
        fireEvent.click(toggle);
        fireEvent.click(toggle);
        expect(queryByTestId('measure-panel')).toBeNull();
    });
});
