import { forwardRef } from 'react';
import { CircleSlash, Cloud } from 'lucide-react';
import type { SceneDate, SourceKind } from '@/types/api';
import { CloudUsabilityChip } from '@/components/layers/CloudUsabilityChip';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** Above this share of cloud-masked pixels we draw a Cloud overlay icon. */
const CLOUDY_THRESHOLD_PERCENT = 30;

interface DateChipProps {
    date: SceneDate;
    selected: boolean;
    sourceKind?: SourceKind;
    /** Short sensor badge (e.g. `S2`, `S1`). Falls back to `date.sensor`. */
    sensorBadge?: string | null;
    /** Per-chip provenance label for best-available mode (e.g. `LISS-4 · 5.8 m`). */
    provenanceLabel?: string | null;
    /**
     * Compact single-row chip: shorter height and no secondary badge line. The
     * best-available provenance label is still shown (it carries cross-source info);
     * the sensor badge and usability chip are dropped to reclaim vertical space.
     */
    compact?: boolean;
    onSelect: () => void;
    onPrefetch?: () => void;
}

/** Compact MM-DD label for a filmstrip chip (e.g. `2026-04-27` → `Apr 27`). */
function shortLabel(acquisitionDate: string): { month: string; day: string } {
    const [, mm, dd] = acquisitionDate.split('-');
    const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    const monthIdx = Number(mm) - 1;
    return {
        month: months[monthIdx] ?? mm,
        day: dd ?? '',
    };
}

/** A single date in the bottom filmstrip: label + usability badge, button semantics. */
export const DateChip = forwardRef<HTMLButtonElement, DateChipProps>(function DateChip(
    { date, selected, sourceKind, sensorBadge, provenanceLabel, compact = false, onSelect, onPrefetch },
    ref,
) {
    const disabled = date.selectable === false || date.tileAvailable === false;
    const unavailableReason = disabled
        ? date.unavailableReason ?? 'This acquisition is not available for selection.'
        : null;
    const { month, day } = shortLabel(date.acquisitionDate);
    const latestLabel =
        sourceKind === 'sar'
            ? 'Latest radar pass'
            : sourceKind === 'context'
                ? 'Latest context layer'
                : sourceKind === 'archive'
                    ? 'Latest archive scene'
                    : 'Latest usable scene';
    const badge = (sensorBadge ?? date.sensor ?? '').trim() || null;
    const effectiveProvenanceLabel = provenanceLabel ?? date.provenanceLabel ?? null;
    const status = (date.availabilityStatus ?? '').toLowerCase();
    const cloudRejected = disabled && (
        /cloud|shadow|obscur/.test(status) ||
        /(cloud|shadow|obscur).*(threshold|limit|cover|exceed|reject)|(threshold|limit).*(cloud|shadow|obscur)/i.test(unavailableReason ?? '') ||
        (date.appliedCloudThresholdPercent != null && date.cloudMaskedPercent != null && date.cloudMaskedPercent > date.appliedCloudThresholdPercent)
    );
    const showCloudIcon =
        sourceKind !== 'sar' &&
        sourceKind !== 'context' &&
        sourceKind !== 'archive' &&
        (cloudRejected || (
            date.cloudMaskedPercent != null &&
            !Number.isNaN(date.cloudMaskedPercent) &&
            date.cloudMaskedPercent > CLOUDY_THRESHOLD_PERCENT &&
            !unavailableReason
        ));
    const ariaParts = [date.acquisitionDate];
    if (effectiveProvenanceLabel) ariaParts.push(effectiveProvenanceLabel);
    else if (badge) ariaParts.push(badge);
    if (date.isLatestUsable) ariaParts.push(latestLabel);
    if (showCloudIcon) ariaParts.push('cloudy');
    if (unavailableReason) ariaParts.push(unavailableReason);

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <button
                    ref={ ref }
                    type="button"
                    role="option"
                    aria-selected={ selected }
                    aria-current={ selected }
                    aria-disabled={ disabled || undefined }
                    aria-label={ ariaParts.join(' · ') }
                    title={ unavailableReason ?? undefined }
                    data-testid={ `date-chip-${date.acquisitionDate}` }
                    data-selected={ selected }
                    onClick={ (event) => {
                        if (disabled) {
                            event.preventDefault();
                            return;
                        }
                        onSelect();
                    } }
                    onMouseEnter={ onPrefetch }
                    onFocus={ onPrefetch }
                    className={ cn(
                        'group relative flex shrink-0 snap-start flex-col items-center justify-center gap-0 rounded-md border px-1 py-0.5 text-center transition-colors duration-fast ease-standard',
                        compact ? 'min-h-9 w-[54px]' : 'h-11 w-[64px]',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        selected
                            ? 'border-primary/60 bg-primary/10 shadow-e1'
                            : 'border-border/60 bg-card/30 hover:border-border hover:bg-accent/50',
                        disabled && 'cursor-not-allowed opacity-60 hover:border-border/60 hover:bg-card/30',
                    ) }
                >
            { date.isLatestUsable && (
                <span
                    className="absolute right-1 top-1 size-1.5 rounded-pill bg-primary"
                    aria-hidden="true"
                    data-testid={
                        sourceKind === 'sar'
                            ? `latest-date-dot-${date.acquisitionDate}`
                            : `latest-usable-dot-${date.acquisitionDate}`
                    }
                />
            ) }
            { showCloudIcon && (
                <Cloud
                    className="absolute left-1 top-1 size-2.5 text-muted-foreground"
                    strokeWidth={ 1.75 }
                    aria-hidden="true"
                    data-testid={ `date-chip-cloud-${date.acquisitionDate}` }
                />
            ) }
            { unavailableReason && !cloudRejected && (
                <CircleSlash
                    className="absolute left-1 top-1 size-2.5 text-warning"
                    strokeWidth={ 1.75 }
                    aria-hidden="true"
                    data-testid={ `date-chip-unavailable-${date.acquisitionDate}` }
                />
            ) }
            <span className="leading-tight">
                <span className="block text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                    { month }
                </span>
                <span className="block font-display text-[14px] font-semibold leading-none tracking-[-0.02em] text-foreground">
                    { day }
                </span>
            </span>
            { compact ? (
                effectiveProvenanceLabel ? (
                    <span
                        className="font-mono tnum mt-0.5 inline-flex h-3 max-w-full items-center truncate rounded-pill border border-border/60 bg-card/40 px-1 text-[9px] leading-none tracking-[0.04em] text-muted-foreground"
                        data-testid={ `date-chip-provenance-${date.acquisitionDate}` }
                        title={ effectiveProvenanceLabel }
                    >
                        { effectiveProvenanceLabel }
                    </span>
                ) : badge && sourceKind !== 'context' && sourceKind !== 'archive' ? (
                    <span
                        className="font-mono tnum mt-0.5 inline-flex h-3 items-center rounded-pill border border-border/60 bg-card/40 px-1 text-[9px] leading-none tracking-[0.04em] text-muted-foreground"
                        data-testid={ `date-chip-sensor-${date.acquisitionDate}` }
                    >
                        { badge }
                    </span>
                ) : null
            ) : effectiveProvenanceLabel ? (
                <span
                    className="font-mono tnum mt-0.5 inline-flex h-3 max-w-full items-center truncate rounded-pill border border-border/60 bg-card/40 px-1 text-[9px] leading-none tracking-[0.04em] text-muted-foreground"
                    data-testid={ `date-chip-provenance-${date.acquisitionDate}` }
                    title={ effectiveProvenanceLabel }
                >
                    { effectiveProvenanceLabel }
                </span>
            ) : badge && sourceKind !== 'context' && sourceKind !== 'archive' ? (
                <span
                    className="font-mono tnum mt-0.5 inline-flex h-3 items-center rounded-pill border border-border/60 bg-card/40 px-1 text-[9px] leading-none tracking-[0.04em] text-muted-foreground"
                    data-testid={ `date-chip-sensor-${date.acquisitionDate}` }
                >
                    { badge }
                </span>
            ) : (
                <CloudUsabilityChip
                    percent={ date.usablePixelPercent }
                    coveragePercent={ date.coveragePercent }
                    sourceKind={ sourceKind }
                    className="max-w-full gap-1 overflow-hidden px-1 py-0 text-[10px] leading-3 [&>span:first-child]:size-1"
                />
            ) }
                </button>
            </TooltipTrigger>
            <TooltipContent data-testid={ `date-chip-tooltip-${date.acquisitionDate}` }>
                <div className="space-y-0.5">
                    <p className="font-medium">{ date.acquisitionDate }{ badge ? ` · ${badge}` : '' }</p>
                    <p>Cloud: { date.cloudMaskedPercent != null ? `${Math.round(date.cloudMaskedPercent)}%` : '—' }</p>
                    <p>Shadow: { date.shadowPercent != null ? `${Math.round(date.shadowPercent)}%` : '—' }</p>
                    <p>Combined: {
                        (date.combinedCloudShadowPercent ?? date.obscuredPercent) != null
                            ? `${Math.round(date.combinedCloudShadowPercent ?? date.obscuredPercent!)}%`
                            : '—'
                    }</p>
                    { date.appliedCloudThresholdPercent != null && <p>Limit: { Math.round(date.appliedCloudThresholdPercent) }%</p> }
                    { unavailableReason && <p>Reason: { unavailableReason }</p> }
                </div>
            </TooltipContent>
        </Tooltip>
    );
});
