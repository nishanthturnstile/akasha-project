import type { SourceKind } from '@/types/api';
import { cn } from '@/lib/utils';
import { NDVI_INDEX_RAMP, type IndexRampConfig } from '@/lib/indexRamp';

interface LegendProps {
    /** Active render mode (e.g. `RGB`, `NDVI`, `VV_GRAYSCALE`). */
    displayMode: string;
    sourceKind?: SourceKind;
    /** Resolved resolution from overlay provenance (e.g. 5.8 for LISS-4). */
    resolvedResolutionMeters?: number | null;
    /** Resolved STAC source ID from overlay provenance (e.g. `resourcesat-2a-liss4-mx70-l2`). */
    resolvedSourceId?: string | null;
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

// Normalized-difference moisture/water indices share a diverging ramp (low →
// high). Ranges match the canonical (a-b)/(a+b) domain of [-1, 1]. NDVI uses
// the discrete ramp from NDVI_INDEX_RAMP (see indexRamp.ts) so the frontend
// legend matches backend _NDVI_REFERENCE_CLASSES exactly.

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

/** Map of known STAC source IDs to human-readable short names. */
const SOURCE_DISPLAY_NAMES: Record<string, string> = {
    'resourcesat-2a-liss4-mx70-l2': 'LISS-4',
    'resourcesat-2a-liss3-boa': 'LISS-3',
};

/**
 * Returns the human-readable source label for a STAC source ID, or `null` for
 * unknown IDs so callers can decide whether to omit the name portion.
 */
function formatSourceName(sourceId: string | null | undefined): string | null {
    if (!sourceId) return null;
    return SOURCE_DISPLAY_NAMES[sourceId] ?? null;
}

/**
 * Builds the provenance chip text from resolved source + resolution.
 * Examples: `LISS-4 · 5.8 m`, `LISS-3 · 24 m`, `5.8 m` (source unknown).
 * Returns `null` when neither piece of information is available.
 */
function provenanceChip(
    resolvedSourceId: string | null | undefined,
    resolvedResolutionMeters: number | null | undefined,
): string | null {
    const sourceName = formatSourceName(resolvedSourceId);
    const hasResolution =
        resolvedResolutionMeters != null && Number.isFinite(resolvedResolutionMeters);

    if (sourceName && hasResolution) return `${sourceName} · ${resolvedResolutionMeters} m`;
    if (sourceName) return sourceName;
    if (hasResolution) return `${resolvedResolutionMeters} m`;
    return null;
}

/**
 * Resolve the legend ramp for a render mode. Returns `null` for true-colour
 * (`RGB`) — natural imagery needs no legend. NDVI/NDVI_CONTEXT also return
 * `null` here because they use the discrete `NdviDiscreteLegend` path.
 * Unknown optical index modes use a generic ramp.
 */
function rampFor(displayMode: string, sourceKind?: SourceKind): RampSpec | null {
    const mode = displayMode.toUpperCase();
    if (mode === 'RGB') return null;

    switch (mode) {
        case 'NDVI':
        case 'NDVI_CONTEXT':
            return null; // handled by NdviDiscreteLegend
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
        case 'BACKSCATTER':
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
 * Discrete legend for NDVI and NDVI_CONTEXT.
 *
 * Renders 8 segmented colour swatches matching backend _NDVI_REFERENCE_CLASSES,
 * numeric boundary ticks, per-class agricultural labels, and a cloud/masked
 * indicator swatch.
 */
function NdviDiscreteLegend({
    config,
    displayMode,
    resolvedSourceId,
    resolvedResolutionMeters,
    className,
}: {
    config: IndexRampConfig;
    displayMode: string;
    resolvedSourceId?: string | null;
    resolvedResolutionMeters?: number | null;
    className?: string;
}) {
    const chip = provenanceChip(resolvedSourceId, resolvedResolutionMeters);
    return (
        <div
            data-testid="map-legend"
            data-display-mode={ displayMode }
            role="img"
            aria-label={ `${config.title} legend${config.caption ? ` — ${config.caption}` : ''}` }
            className={ cn(
                'glass pointer-events-auto w-[176px] rounded-lg px-3 py-2.5',
                className,
            ) }
        >
            <div className="mb-1.5 flex items-center justify-between gap-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-foreground/80 on-map-text">
                    { config.title }
                </p>
                { chip != null && (
                    <span
                        className="text-[10px] font-medium text-primary/80 on-map-text"
                        data-testid="legend-resolved-resolution"
                    >
                        { chip }
                    </span>
                ) }
            </div>

            {/* 8-segment colour bar — each segment mirrors one backend NDVI class */}
            <div
                aria-hidden="true"
                className="flex h-2.5 w-full overflow-hidden rounded-pill ring-1 ring-inset ring-border/60"
            >
                { config.classes.map((cls) => (
                    <div
                        key={ cls.label }
                        data-testid="ndvi-segment"
                        data-color={ cls.color }
                        className="flex-1"
                        style={ { backgroundColor: cls.color } }
                    />
                )) }
            </div>

            {/* Numeric boundary ticks — 9 ticks for 8 segments */}
            <div className="mt-1 flex items-center justify-between overflow-hidden text-[9px] font-medium tabular-nums text-foreground/70 on-map-text">
                { config.ticks.map((tick, i) => (
                    <span key={ `${tick}-${i}` } data-testid="ndvi-tick">
                        { tick }
                    </span>
                )) }
            </div>

            {/* Per-class agricultural labels */}
            <div className="mt-2 space-y-0.5">
                { config.classes.map((cls) => (
                    <div
                        key={ cls.label }
                        className="flex items-center gap-1.5 text-[10px] text-foreground/80 on-map-text"
                    >
                        <span
                            aria-hidden="true"
                            className="size-2 shrink-0 rounded-sm"
                            style={ { backgroundColor: cls.color } }
                        />
                        <span>{ cls.label }</span>
                    </div>
                )) }
            </div>

            {/* Cloud / masked indicator */}
            <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <span
                    aria-hidden="true"
                    className="size-2 shrink-0 rounded-sm ring-1 ring-inset ring-border/60"
                    style={ { backgroundColor: config.maskedColor } }
                />
                <span>{ config.maskedLabel }</span>
            </div>
        </div>
    );
}

/**
 * Colour key for the active display mode. Renders nothing for true-colour so the
 * map stays clean by default (CLAUDE.md: RGB is the cold default). For index and
 * SAR modes it shows a labelled ramp matching the tile render's colormap.
 */
export function Legend({ displayMode, sourceKind, resolvedResolutionMeters, resolvedSourceId, className }: LegendProps) {
    const mode = displayMode.toUpperCase();

    // NDVI and NDVI_CONTEXT use a discrete 8-class legend matching backend _NDVI_REFERENCE_CLASSES.
    if (mode === 'NDVI' || mode === 'NDVI_CONTEXT') {
        return (
            <NdviDiscreteLegend
                config={ NDVI_INDEX_RAMP }
                displayMode={ displayMode }
                resolvedSourceId={ resolvedSourceId }
                resolvedResolutionMeters={ resolvedResolutionMeters }
                className={ className }
            />
        );
    }

    const ramp = rampFor(displayMode, sourceKind);
    if (!ramp) return null;

    const chip = provenanceChip(resolvedSourceId, resolvedResolutionMeters);

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
                { chip != null && (
                    <span
                        className="text-[10px] font-medium text-primary/80 on-map-text"
                        data-testid="legend-resolved-resolution"
                    >
                        { chip }
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
