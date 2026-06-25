import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MapControls } from '@/components/map/MapControls';

describe('MapControls', () => {
    it('renders zoom in and zoom out buttons', () => {
        const { getByTestId } = render(<MapControls map={ null } />);
        expect(getByTestId('zoom-in-btn')).toBeTruthy();
        expect(getByTestId('zoom-out-btn')).toBeTruthy();
    });
});
