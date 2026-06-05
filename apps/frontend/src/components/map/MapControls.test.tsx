import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { MapControls } from '@/components/map/MapControls';

describe('MapControls fullscreen', () => {
    const originalRequest = document.documentElement.requestFullscreen;

    beforeEach(() => {
        document.documentElement.requestFullscreen = vi.fn().mockResolvedValue(undefined);
    });

    afterEach(() => {
        document.documentElement.requestFullscreen = originalRequest;
        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: null,
        });
        vi.restoreAllMocks();
    });

    it('renders a fullscreen button when the API is supported', () => {
        const { getByTestId } = render(<MapControls map={ null } />);
        const btn = getByTestId('fullscreen-btn');
        expect(btn.getAttribute('aria-label')).toBe('Enter full screen');
    });

    it('requests fullscreen on click', () => {
        const { getByTestId } = render(<MapControls map={ null } />);
        fireEvent.click(getByTestId('fullscreen-btn'));
        expect(document.documentElement.requestFullscreen).toHaveBeenCalledTimes(1);
    });

    it('exits fullscreen when already fullscreen', () => {
        const exit = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: document.documentElement,
        });
        document.exitFullscreen = exit;

        const { getByTestId } = render(<MapControls map={ null } />);
        // Reflect the fullscreen state to the button label via the change event.
        fireEvent(document, new Event('fullscreenchange'));

        const btn = getByTestId('fullscreen-btn');
        expect(btn.getAttribute('aria-label')).toBe('Exit full screen');

        fireEvent.click(btn);
        expect(exit).toHaveBeenCalledTimes(1);
    });
});
