import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Legend } from '@/components/map/Legend';

describe('Legend', () => {
    it('renders nothing for true-colour (RGB)', () => {
        const { queryByTestId } = render(<Legend displayMode="RGB" sourceKind="optical" />);
        expect(queryByTestId('map-legend')).toBeNull();
    });

    it('renders the NDVI vegetation ramp', () => {
        const { getByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        const legend = getByTestId('map-legend');
        expect(legend.getAttribute('data-display-mode')).toBe('NDVI');
        expect(legend.textContent).toContain('NDVI');
        expect(legend.getAttribute('aria-label')).toContain('NDVI');
    });

    it('renders the SAR backscatter ramp for VV grayscale', () => {
        const { getByTestId } = render(<Legend displayMode="VV_GRAYSCALE" sourceKind="sar" />);
        const legend = getByTestId('map-legend');
        expect(legend.textContent).toContain('Backscatter (dB)');
    });

    it('falls back to an index ramp for unknown non-RGB optical modes', () => {
        const { getByTestId } = render(<Legend displayMode="SOMETHING_ELSE" sourceKind="optical" />);
        expect(getByTestId('map-legend').textContent).toContain('Index');
        expect(getByTestId('map-legend').textContent).not.toContain('NDVI');
    });

    it('shows a false-colour key for FALSE_COLOR modes', () => {
        const { getByTestId } = render(
            <Legend displayMode="FALSE_COLOR_URBAN" sourceKind="optical" />,
        );
        expect(getByTestId('map-legend').textContent).toContain('False colour');
    });
});
