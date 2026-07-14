/**
 * Index ramp configuration for legend rendering.
 *
 * The NDVI discrete ramp colors mirror the backend _NDVI_REFERENCE_CLASSES
 * defined in apps/api/app/raster/tiles.py. Keep them in sync when backend
 * palette changes.
 */

export interface IndexRampClass {
    /** Lower bound of this class. Use -Infinity for the open-ended "< 0" class. */
    low: number;
    /** Upper bound of this class (exclusive, except the last). */
    high: number;
    /** Human-readable agricultural label. */
    label: string;
    /** Concise cursor-tooltip interpretation, when it differs from the legend label. */
    hoverLabel?: string;
    /** CSS hex color exactly matching backend _NDVI_REFERENCE_CLASSES. */
    color: string;
}

/** `discrete` — render as segmented swatches; `continuous` — render as a smooth gradient. */
export type IndexRampKind = 'discrete' | 'continuous';

export interface IndexRampConfig {
    kind: IndexRampKind;
    title: string;
    /** Ordered class definitions (required for discrete ramps). */
    classes: IndexRampClass[];
    /** Numeric boundary tick labels rendered below the bar, left to right. */
    ticks: string[];
    /** Optional one-line caption beneath the ramp. */
    caption?: string;
    /** Background color for the cloud/masked indicator swatch. */
    maskedColor: string;
    /** Label for the cloud/masked indicator swatch. */
    maskedLabel: string;
}

/**
 * NDVI discrete ramp — 8 agriculture-oriented classes.
 *
 * Colors mirror backend _NDVI_REFERENCE_CLASSES in apps/api/app/raster/tiles.py:
 *   (-1.0, 0.0,  (19, 24, 125))  → #13187d
 *   (0.0,  0.15, (128, 70, 26))  → #80461a
 *   (0.15, 0.30, (213, 0,  35))  → #d50023
 *   (0.30, 0.45, (255, 83, 13))  → #ff530d
 *   (0.45, 0.60, (250, 201, 9))  → #fac909
 *   (0.60, 0.75, (111, 202, 7))  → #6fca07
 *   (0.75, 0.90, (22,  153, 43)) → #16992b
 *   (0.90, 1.0,  (0,   88, 37))  → #005825
 */
export const NDVI_INDEX_RAMP: IndexRampConfig = {
    kind: 'discrete',
    title: 'NDVI heatmap',
    classes: [
        {
            low: -Infinity,
            high: 0,
            label: 'Water / non-veg',
            hoverLabel: 'Water / non-vegetation',
            color: '#13187d',
        },
        { low: 0, high: 0.15, label: 'Bare soil', color: '#80461a' },
        {
            low: 0.15,
            high: 0.30,
            label: 'Stressed',
            hoverLabel: 'Stressed vegetation',
            color: '#d50023',
        },
        {
            low: 0.30,
            high: 0.45,
            label: 'Sparse crop',
            hoverLabel: 'Sparse vegetation',
            color: '#ff530d',
        },
        {
            low: 0.45,
            high: 0.60,
            label: 'Sub-canopy',
            hoverLabel: 'Moderate vegetation',
            color: '#fac909',
        },
        {
            low: 0.60,
            high: 0.75,
            label: 'Moderate',
            hoverLabel: 'Dense vegetation',
            color: '#6fca07',
        },
        {
            low: 0.75,
            high: 0.90,
            label: 'Healthy',
            hoverLabel: 'Very dense vegetation',
            color: '#16992b',
        },
        {
            low: 0.90,
            high: 1.0,
            label: 'Peak vigour',
            hoverLabel: 'Peak vegetation',
            color: '#005825',
        },
    ],
    ticks: ['<0', '0', '.15', '.30', '.45', '.60', '.75', '.90', '1.0'],
    caption: 'Stress ▸ healthy canopy',
    maskedColor: '#d0d5dd',
    maskedLabel: 'Cloud / masked',
};

/** Resolve a numeric value against a discrete ramp's [low, high) intervals. */
export function indexRampClassForValue(
    config: IndexRampConfig,
    value: number,
): IndexRampClass | null {
    if (!Number.isFinite(value)) return null;
    const lastIndex = config.classes.length - 1;
    return config.classes.find((item, index) => (
        value >= item.low && (value < item.high || (index === lastIndex && value === item.high))
    )) ?? null;
}

/** Agronomic interpretation shown by the field-map NDVI cursor inspector. */
export function ndviInterpretation(value: number): string | null {
    const item = indexRampClassForValue(NDVI_INDEX_RAMP, value);
    return item?.hoverLabel ?? item?.label ?? null;
}
