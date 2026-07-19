import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { Legend } from '@/components/map/Legend';
import { NDVI_INDEX_RAMP } from '@/lib/indexRamp';

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
        expect(legend.textContent).toContain('Cloud / masked');
        expect(legend.getAttribute('aria-label')).toContain('NDVI');
    });

    it('renders the NDVI vegetation ramp for precomputed context NDVI', () => {
        const { getByTestId } = render(<Legend displayMode="NDVI_CONTEXT" sourceKind="context" />);
        const legend = getByTestId('map-legend');
        expect(legend.textContent).toContain('NDVI');
        expect(legend.getAttribute('aria-label')).toContain('NDVI');
    });

    // --- Discrete NDVI legend ---

    it('renders 8 discrete NDVI class segments', () => {
        const { getAllByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        const segments = getAllByTestId('ndvi-segment');
        expect(segments).toHaveLength(8);
    });

    it('NDVI segments carry exact hex colors matching backend _NDVI_REFERENCE_CLASSES', () => {
        const { getAllByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        const segments = getAllByTestId('ndvi-segment');
        const expectedColors = [
            '#13187d', // Water / non-veg  — RGB(19,  24,  125)
            '#80461a', // Bare soil        — RGB(128, 70,  26)
            '#d50023', // Stressed         — RGB(213, 0,   35)
            '#ff530d', // Sparse crop      — RGB(255, 83,  13)
            '#fac909', // Sub-canopy       — RGB(250, 201, 9)
            '#6fca07', // Moderate         — RGB(111, 202, 7)
            '#16992b', // Healthy          — RGB(22,  153, 43)
            '#005825', // Peak vigour      — RGB(0,   88,  37)
        ];
        segments.forEach((seg, i) => {
            expect(seg.getAttribute('data-color')).toBe(expectedColors[i]);
        });
    });

    it('renders all 9 NDVI numeric ticks', () => {
        const { getAllByTestId, getByTestId } = render(
            <Legend displayMode="NDVI" sourceKind="optical" />,
        );
        const ticks = getAllByTestId('ndvi-tick');
        expect(ticks).toHaveLength(9);
        const legend = getByTestId('map-legend');
        expect(legend.textContent).toContain('<0');
        expect(legend.textContent).toContain('.15');
        expect(legend.textContent).toContain('.30');
        expect(legend.textContent).toContain('.45');
        expect(legend.textContent).toContain('.60');
        expect(legend.textContent).toContain('.75');
        expect(legend.textContent).toContain('.90');
        expect(legend.textContent).toContain('1.0');
    });

    it('renders all 8 NDVI agricultural class labels', () => {
        const { getByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        const legend = getByTestId('map-legend');
        for (const label of [
            'Water / non-veg',
            'Bare soil',
            'Stressed',
            'Sparse crop',
            'Sub-canopy',
            'Moderate',
            'Healthy',
            'Peak vigour',
        ]) {
            expect(legend.textContent).toContain(label);
        }
    });

    it('renders Cloud / masked swatch label for NDVI', () => {
        const { getByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        expect(getByTestId('map-legend').textContent).toContain('Cloud / masked');
    });

    it('renders discrete NDVI legend for NDVI_CONTEXT mode too', () => {
        const { getAllByTestId, getByTestId } = render(
            <Legend displayMode="NDVI_CONTEXT" sourceKind="context" />,
        );
        expect(getAllByTestId('ndvi-segment')).toHaveLength(8);
        expect(getByTestId('map-legend').textContent).toContain('Water / non-veg');
        expect(getByTestId('map-legend').textContent).toContain('Cloud / masked');
    });

    // --- Non-NDVI modes use continuous gradient ---

    it('renders the SAR backscatter ramp for VV grayscale', () => {
        const { getByTestId } = render(<Legend displayMode="VV_GRAYSCALE" sourceKind="sar" />);
        const legend = getByTestId('map-legend');
        expect(legend.textContent).toContain('Backscatter (dB)');
    });

    it('renders the SAR backscatter ramp for the NISAR BACKSCATTER token', () => {
        const { getByTestId } = render(<Legend displayMode="BACKSCATTER" sourceKind="sar" />);
        expect(getByTestId('map-legend').textContent).toContain('Backscatter (dB)');
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

    it('shows a false-colour key for FCC', () => {
        const { getByTestId } = render(<Legend displayMode="FCC" sourceKind="optical" />);
        expect(getByTestId('map-legend').textContent).toContain('False colour');
    });

    it('shows the resolved resolution label when resolvedResolutionMeters is provided', () => {
        const { getByTestId } = render(
            <Legend displayMode="NDVI" sourceKind="optical" resolvedResolutionMeters={ 5.8 } />,
        );
        const resEl = getByTestId('legend-resolved-resolution');
        expect(resEl).toBeTruthy();
        expect(resEl.textContent).toContain('5.8');
        expect(resEl.textContent).toContain('m');
    });

    it('does not show the resolved resolution label when resolvedResolutionMeters is null', () => {
        const { queryByTestId } = render(
            <Legend displayMode="NDVI" sourceKind="optical" resolvedResolutionMeters={ null } />,
        );
        expect(queryByTestId('legend-resolved-resolution')).toBeNull();
    });

    it('does not show the resolved resolution label when resolvedResolutionMeters is absent', () => {
        const { queryByTestId } = render(<Legend displayMode="NDVI" sourceKind="optical" />);
        expect(queryByTestId('legend-resolved-resolution')).toBeNull();
    });

    // --- Source provenance chip ---

    it('shows LISS-4 chip with resolution for resourcesat-2a-liss4-mx70-l2', () => {
        const { getByTestId } = render(
            <Legend
                displayMode="NDVI"
                sourceKind="optical"
                resolvedSourceId="resourcesat-2a-liss4-mx70-l2"
                resolvedResolutionMeters={ 5.8 }
            />,
        );
        const chip = getByTestId('legend-resolved-resolution');
        expect(chip.textContent).toBe('LISS-4 · 5.8 m');
    });

    it('shows LISS-3 chip with resolution for resourcesat-2a-liss3-boa', () => {
        const { getByTestId } = render(
            <Legend
                displayMode="NDVI"
                sourceKind="optical"
                resolvedSourceId="resourcesat-2a-liss3-boa"
                resolvedResolutionMeters={ 24 }
            />,
        );
        const chip = getByTestId('legend-resolved-resolution');
        expect(chip.textContent).toBe('LISS-3 · 24 m');
    });

    it('shows only resolution when source ID is unknown', () => {
        const { getByTestId } = render(
            <Legend
                displayMode="NDVI"
                sourceKind="optical"
                resolvedSourceId="some-unknown-source"
                resolvedResolutionMeters={ 10 }
            />,
        );
        const chip = getByTestId('legend-resolved-resolution');
        expect(chip.textContent).toBe('10 m');
        expect(chip.textContent).not.toContain('LISS');
    });
});

// ---------------------------------------------------------------------------
// Cross-stack NDVI palette contract
// Canonical source: apps/api/app/raster/tiles.py  _NDVI_REFERENCE_CLASSES
// If you change colors here you MUST update the backend constant and vice-versa.
// ---------------------------------------------------------------------------
describe('NDVI_INDEX_RAMP color contract (cross-stack)', () => {
    /**
     * Canonical NDVI hex palette mirroring backend _NDVI_REFERENCE_CLASSES:
     *   (-1.0, 0.0,  (19,  24,  125)) → #13187d
     *   (0.0,  0.15, (128, 70,  26))  → #80461a
     *   (0.15, 0.30, (213, 0,   35))  → #d50023
     *   (0.30, 0.45, (255, 83,  13))  → #ff530d
     *   (0.45, 0.60, (250, 201, 9))   → #fac909
     *   (0.60, 0.75, (111, 202, 7))   → #6fca07
     *   (0.75, 0.90, (22,  153, 43))  → #16992b
     *   (0.90, 1.0,  (0,   88,  37))  → #005825
     */
    const CANONICAL_COLORS = [
        '#13187d', // (-1.0, 0.0)  Water / non-veg  — RGB(19, 24, 125)
        '#80461a', // (0.0,  0.15) Bare soil         — RGB(128, 70, 26)
        '#d50023', // (0.15, 0.30) Stressed          — RGB(213, 0, 35)
        '#ff530d', // (0.30, 0.45) Sparse crop       — RGB(255, 83, 13)
        '#fac909', // (0.45, 0.60) Sub-canopy        — RGB(250, 201, 9)
        '#6fca07', // (0.60, 0.75) Moderate          — RGB(111, 202, 7)
        '#16992b', // (0.75, 0.90) Healthy           — RGB(22, 153, 43)
        '#005825', // (0.90, 1.0)  Peak vigour       — RGB(0, 88, 37)
    ] as const;

    it('has exactly 8 classes', () => {
        expect(NDVI_INDEX_RAMP.classes).toHaveLength(8);
    });

    it('class colors match canonical backend _NDVI_REFERENCE_CLASSES hex values', () => {
        const actual = NDVI_INDEX_RAMP.classes.map((c) => c.color);
        expect(actual).toEqual([...CANONICAL_COLORS]);
    });

    it('first class color is #13187d (RGB 19,24,125) — water/non-veg sentinel', () => {
        expect(NDVI_INDEX_RAMP.classes[0].color).toBe('#13187d');
    });

    it('class boundaries match backend _NDVI_REFERENCE_CLASSES ranges', () => {
        const expectedBounds = [
            [-Infinity, 0],
            [0, 0.15],
            [0.15, 0.30],
            [0.30, 0.45],
            [0.45, 0.60],
            [0.60, 0.75],
            [0.75, 0.90],
            [0.90, 1.0],
        ] as const;
        NDVI_INDEX_RAMP.classes.forEach((cls, i) => {
            expect(cls.low).toBeCloseTo(expectedBounds[i][0] as number, 10);
            expect(cls.high).toBeCloseTo(expectedBounds[i][1], 10);
        });
    });
});
