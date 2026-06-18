import type { SourceKind } from '@/types/api';
import { cn } from '@/lib/utils';

interface LegendProps {
    /** Active render mode (e.g. `RGB`, `NDVI`, `VV_GRAYSCALE`). */
    displayMode: string;
    sourceKind?: SourceKind;
    /** Resolved resolution from overlay provenance (e.g. 5.8 for LISS-4). */
    resolvedResolutionMeters?: number | null;
    className?: string;
}

interface RampSpec {
    title: string;
    /** CSS gradient applied left→right across the bar. */
    gradient: string;
    /** Tick labels under the bar, left→right. */
    ticks: string[];
    /** Optional one-line caption beneath the ramp. */
    caption?: string;
    maskedLabel?: string;
}

// Normalized-difference vegetation/water/moisture indices share a diverging
// ramp (low → high). NDVI uses the conventional brown→yellow→green; NDWI flips
// the meaning toward water so it reads blue at the high end. Ranges match the
// canonical (a-b)/(a+b) domain of [-1, 1].
const NDVI_RAMP: RampSpec = {
    title: 'NDVI heatmap',
    gradient:
        'linear-gradient(90deg,#d73027 0%,#fdae61 28%,#fee08b 52%,#a6d96a 76%,#1a9850 100%)',
    ticks: ['Low', 'Mid', 'High'],
    caption: 'Stress ▸ healthy canopy',
    maskedLabel: 'Cloud / no data',
};

const NDRE_RAMP: RampSpec = {
    title: 'NDRE · chlorophyll',
    gradient:
        'linear-gradient(90deg,#7a4b12 0%,#c79a3a 30%,#e8dd77 55%,#6fb04a 80%,#175e2b 100%)',
    ticks: ['-1', '0', '+1'],
    caption: 'Low ▸ high red-edge vigour',
};

const MSAVI_RAMP: RampSpec = {
    title: 'MSAVI · vegetation',
    gradient:
        'linear-gradient(90deg,#8a5a22 0%,#c79a3a 30%,#e8dd77 55%,#7cbb50 80%,#1f6b3a 100%)',
    ticks: ['0', '0.5', '1'],
    caption: 'Soil-adjusted canopy cover',
};

const NDMI_RAMP: RampSpec = {
    title: 'NDMI · moisture',
    gradient:
        'linear-gradient(90deg,#8a5a22 0%,#d8c98a 35%,#8fd3c4 70%,#1f6f8b 100%)',
    ticks: ['-1', '0', '+1'],
    caption: 'Dry ▸ moist vegetation',
};

const NDWI_RAMP: RampSpec = {
    title: 'NDWI · water',
    gradient:
        'linear-gradient(90deg,#caa86a 0%,#e8e0b0 30%,#7fc2dd 65%,#1660a8 100%)',
    ticks: ['-1', '0', '+1'],
    caption: 'Land ▸ open water',
};

const SAR_RAMP: RampSpec = {
    title: 'Backscatter (dB)',
    gradient: 'linear-gradient(90deg,#0a0a0a 0%,#6b6b6b 50%,#f5f5f5 100%)',
    ticks: ['Low', 'High'],
    caption: 'Smooth / water ▸ rough / urban',
};

const FALSE_COLOR_RAMP: RampSpec = {
    title: 'False colour',
    gradient: 'linear-gradient(90deg,#b22222 0%,#1f7a34 50%,#1660a8 100%)',
    ticks: ['NIR', 'Veg', 'Built'],
    caption: 'Band-substituted composite',
};

const GENERIC_INDEX_RAMP: RampSpec = {
    title: 'Index',
    gradient:
        'linear-gradient(90deg,#7b4b25 0%,#c7943e 30%,#e7dc79 55%,#6ead59 78%,#1f6b3a 100%)',
    ticks: ['Low', 'Mid', 'High'],
    caption: 'Low ▸ high index value',
};

/**
 * Resolve the legend ramp for a render mode. True-colour (`RGB`) has no legend
 * (natural imagery needs none); unknown optical index modes use a generic ramp
 * so the UI does not imply an NDVI formula for arbitrary labels.
 */
function rampFor(displayMode: string, sourceKind?: SourceKind): RampSpec | null {
    const mode = displayMode.toUpperCase();
    if (mode === 'RGB') return null;

    switch (mode) {
        case 'NDVI':
        case 'NDVI_CONTEXT':
            return NDVI_RAMP;
        case 'NDRE':
            return NDRE_RAMP;
        case 'MSAVI':
            return MSAVI_RAMP;
        case 'NDMI':
            return NDMI_RAMP;
        case 'NDWI':
        case 'NDWI_GREEN_NIR':
            return NDWI_RAMP;
        case 'VV_GRAYSCALE':
        case 'VH_GRAYSCALE':
            return SAR_RAMP;
        case 'FCC':
        case 'FALSE_COLOR':
        case 'FALSE_COLOUR':
            return FALSE_COLOR_RAMP;
        default:
            break;
    }
    if (mode.startsWith('FALSE_COLOR')) return FALSE_COLOR_RAMP;
    if (sourceKind === 'sar') return SAR_RAMP;
    return GENERIC_INDEX_RAMP;
}

/**
 * Colour key for the active display mode. Renders nothing for true-colour so the
 * map stays clean by default (CLAUDE.md: RGB is the cold default). For index and
 * SAR modes it shows a labelled ramp matching the tile render's colormap.
 */
export function Legend({ displayMode, sourceKind, resolvedResolutionMeters, className }: LegendProps) {
    const ramp = rampFor(displayMode, sourceKind);
    if (!ramp) return null;

    return (
        <div
            data-testid="map-legend"
            data-display-mode={ displayMode }
            role="img"
            aria-label={ `${ramp.title} legend${ramp.caption ? ` — ${ramp.caption}` : ''}` }
            className={ cn(
                'glass pointer-events-auto w-[176px] rounded-lg px-3 py-2.5',
                className,
            ) }
        >
            <div className="mb-1.5 flex items-center justify-between gap-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-foreground/80 on-map-text">
                    { ramp.title }
                </p>
                { resolvedResolutionMeters != null && Number.isFinite(resolvedResolutionMeters) && (
                    <span
                        className="text-[10px] font-medium text-primary/80 on-map-text"
                        data-testid="legend-resolved-resolution"
                    >
                        { resolvedResolutionMeters } m
                    </span>
                ) }
            </div>
            <div
                aria-hidden="true"
                className="h-2.5 w-full rounded-pill ring-1 ring-inset ring-border/60"
                style={ { background: ramp.gradient } }
            />
            <div className="mt-1 flex items-center justify-between text-[10px] font-medium tabular-nums text-foreground/70 on-map-text">
                { ramp.ticks.map((tick, i) => (
                    <span
                        key={ `${tick}-${i}` }
                        className={ cn(
                            ramp.ticks.length > 2 && i === 1 && 'flex-1 text-center',
                            i === ramp.ticks.length - 1 && 'text-right',
                        ) }
                    >
                        { tick }
                    </span>
                )) }
            </div>
            { ramp.caption && (
                <p className="mt-1 text-[10px] leading-3 text-muted-foreground">{ ramp.caption }</p>
            ) }
            { ramp.maskedLabel && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span
                        aria-hidden="true"
                        className="size-2.5 rounded-sm ring-1 ring-inset ring-border/60"
                        style={ { backgroundColor: '#d0d5dd' } }
                    />
                    <span>{ ramp.maskedLabel }</span>
                </div>
            ) }
        </div>
    );
}
