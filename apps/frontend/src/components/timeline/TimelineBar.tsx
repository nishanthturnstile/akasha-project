import { useCallback, useEffect, useMemo, useRef } from 'react';
import { AlertTriangle, CalendarClock, ChevronsRight, Info, RefreshCw, Layers } from 'lucide-react';
import type { SceneDate, SourceKind } from '@/types/api';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { CalendarRangePicker } from './CalendarRangePicker';
import { DateChip } from './DateChip';
import { PlaybackControls } from './PlaybackControls';

interface TimelineBarProps {
    dates: SceneDate[] | undefined;
    selectedDate: string | null;
    onSelect: (acquisitionDate: string) => void;
    sourceKind?: SourceKind;
    /** Short sensor badge shown per chip when the underlying scene has no `sensor`. */
    sensorBadge?: string | null;
    /** BFF-projected, source-global acquisition date. Must be strictly future UTC. */
    nextExpectedAcquisitionDate?: string | null;
    loading: boolean;
    error: string | null;
    onRetry: () => void;
    /** Surfaced when no date meets the usability threshold. */
    marginalNote?: string | null;
    /** Surfaced for the nearest radar pass (SAR sources). */
    nearestPassNote?: string | null;
    onPrefetchDate?: (acquisitionDate: string) => void;
    /** Inclusive lower bound (YYYY-MM-DD) for the visible filmstrip. */
    periodFrom?: string | null;
    /** Inclusive upper bound (YYYY-MM-DD) for the visible filmstrip. */
    periodTo?: string | null;
    onPeriodChange?: (from: string | null, to: string | null) => void;
    /** When true, timeline is in best-available mode showing cross-source candidates. */
    bestMode?: boolean;
    /** When provided, renders a Best / Source toggle button. */
    onBestModeChange?: (on: boolean) => void;
    /** Compact single-row filmstrip: shorter chips with no per-chip badge line. */
    compact?: boolean;
}

function NoteRow({
    testId,
    tone,
    children,
}: {
    testId: string;
    tone: 'warning' | 'info';
    children: React.ReactNode;
}) {
    return (
        <div
            data-testid={ testId }
            className={ cn(
                'flex min-w-0 items-center gap-1.5 rounded-md border px-2 py-0.5 text-[13px]',
                tone === 'warning'
                    ? 'border-warning/30 bg-warning/10 text-warning'
                    : 'border-info/30 bg-info/10 text-info',
            ) }
        >
            <Info className="size-3.5 shrink-0" strokeWidth={ 1.75 } />
            <span className="truncate">{ children }</span>
        </div>
    );
}

/**
 * Map-first temporal navigator: a horizontal filmstrip of acquisition dates with a
 * jump-to-latest affordance. Replaces the old vertical `DateList`. Dates render
 * oldest → newest; ←/→ step between selectable chips, Home/End jump to ends.
 */
export function TimelineBar({
    dates,
    selectedDate,
    onSelect,
    sourceKind,
    sensorBadge,
    nextExpectedAcquisitionDate,
    loading,
    error,
    onRetry,
    marginalNote,
    nearestPassNote,
    onPrefetchDate,
    periodFrom,
    periodTo,
    onPeriodChange,
    bestMode = false,
    onBestModeChange,
    compact = false,
}: TimelineBarProps) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    const selectedRef = useRef<HTMLButtonElement | null>(null);

    // Oldest → newest for left-to-right reading; only tile-available dates are selectable.
    const ordered = useMemo(() => {
        if (!dates) return [];
        return [...dates].sort((a, b) => a.acquisitionDate.localeCompare(b.acquisitionDate));
    }, [dates]);

    // Apply the calendar range filter; always keep the active selection visible so the
    // selected chip never disappears mid-interaction.
    const visible = useMemo(() => {
        if (!periodFrom && !periodTo) return ordered;
        return ordered.filter((d) => {
            if (d.acquisitionDate === selectedDate) return true;
            if (periodFrom && d.acquisitionDate < periodFrom) return false;
            if (periodTo && d.acquisitionDate > periodTo) return false;
            return true;
        });
    }, [ordered, periodFrom, periodTo, selectedDate]);

    const selectable = useMemo(() => visible.filter((d) => d.tileAvailable), [visible]);

    const jumpTarget = useMemo(() => {
        if (selectable.length === 0) return null;
        const latestUsable = [...selectable].reverse().find((d) => d.isLatestUsable);
        return (latestUsable ?? selectable[selectable.length - 1]).acquisitionDate;
    }, [selectable]);

    /** Format the authoritative BFF projection and fail closed on stale values. */
    const nextImage = useMemo<{ iso: string; label: string } | null>(() => {
        if (bestMode || !nextExpectedAcquisitionDate || sourceKind === 'archive') return null;
        const todayIso = new Date().toISOString().slice(0, 10);
        if (nextExpectedAcquisitionDate <= todayIso) return null;
        const base = new Date(`${nextExpectedAcquisitionDate}T00:00:00Z`);
        if (Number.isNaN(base.getTime())) return null;
        const months = [
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        ];
        const label = `${months[base.getUTCMonth()]} ${base.getUTCDate()}, ${base.getUTCFullYear()}`;
        return { iso: nextExpectedAcquisitionDate, label };
    }, [bestMode, nextExpectedAcquisitionDate, sourceKind]);

    // Keep the active chip in view when selection changes (e.g. source switch / jump).
    useEffect(() => {
        selectedRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }, [selectedDate]);

    const handleKeyDown = useCallback(
        (event: React.KeyboardEvent<HTMLDivElement>) => {
            if (selectable.length === 0) return;
            const idx = selectable.findIndex((d) => d.acquisitionDate === selectedDate);
            let next = idx;
            switch (event.key) {
                case 'ArrowRight':
                    next = idx < 0 ? 0 : Math.min(idx + 1, selectable.length - 1);
                    break;
                case 'ArrowLeft':
                    next = idx < 0 ? selectable.length - 1 : Math.max(idx - 1, 0);
                    break;
                case 'Home':
                    next = 0;
                    break;
                case 'End':
                    next = selectable.length - 1;
                    break;
                default:
                    return;
            }
            event.preventDefault();
            const target = selectable[next];
            if (target && target.acquisitionDate !== selectedDate) onSelect(target.acquisitionDate);
        },
        [selectable, selectedDate, onSelect],
    );

    const atLatest = jumpTarget != null && jumpTarget === selectedDate;

    let content: React.ReactNode;
    if (loading) {
        content = (
            <div className="flex gap-1.5" data-testid="timeline-loading">
                { [0, 1, 2, 3, 4, 5].map((i) => (
                    <Skeleton
                        key={ i }
                        className={ cn('shrink-0 rounded-md', compact ? 'h-9 w-[54px]' : 'h-11 w-[62px]') }
                    />
                )) }
            </div>
        );
    } else if (error) {
        content = (
            <div
                className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2"
                data-testid="timeline-error"
            >
                <span className="flex items-center gap-2 text-[14px] text-destructive">
                    <AlertTriangle className="size-4" strokeWidth={ 1.75 } /> { error }
                </span>
                <Button variant="outline" size="sm" onClick={ onRetry } data-testid="timeline-retry">
                    <RefreshCw className="size-4" strokeWidth={ 1.75 } /> Retry
                </Button>
            </div>
        );
    } else if (ordered.length === 0) {
        content = (
            <p className="py-4 text-[14px] text-muted-foreground" data-testid="timeline-empty">
                No acquisition dates available for this source.
            </p>
        );
    } else if (visible.length === 0) {
        content = (
            <p className="py-4 text-[14px] text-muted-foreground" data-testid="timeline-empty-period">
                No acquisition dates in the selected period.
            </p>
        );
    } else {
        content = (
            <div
                ref={ trackRef }
                role="listbox"
                aria-label="Acquisition dates"
                aria-orientation="horizontal"
                tabIndex={ 0 }
                onKeyDown={ handleKeyDown }
                data-testid="timeline-track"
                className="flex snap-x gap-1.5 overflow-x-auto py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
                { visible.map((d) => {
                    const selected = d.acquisitionDate === selectedDate;
                    return (
                        <DateChip
                            key={ d.acquisitionDate }
                            ref={ selected ? selectedRef : undefined }
                            date={ d }
                            selected={ selected }
                            sourceKind={ sourceKind }
                            sensorBadge={ bestMode ? null : (sensorBadge ?? undefined) }
                            provenanceLabel={ bestMode ? (d.provenanceLabel ?? null) : null }
                            compact={ compact }
                            onSelect={ () => onSelect(d.acquisitionDate) }
                            onPrefetch={ onPrefetchDate ? () => onPrefetchDate(d.acquisitionDate) : undefined }
                        />
                    );
                }) }
            </div>
        );
    }

    return (
        <section
            aria-label="Timeline"
            data-testid="timeline-bar"
            className="glass pointer-events-auto z-panel min-h-[var(--timeline-height)] animate-panel-in overflow-hidden px-2 py-1"
        >
            <div className={ cn('flex items-center gap-2', compact ? 'min-h-9' : 'min-h-12') }>
                { onPeriodChange && (
                    <CalendarRangePicker
                        from={ periodFrom ?? null }
                        to={ periodTo ?? null }
                        onChange={ onPeriodChange }
                        disabled={ loading || ordered.length === 0 }
                    />
                ) }
                { (marginalNote || nearestPassNote) && (
                    <div className="hidden max-w-[28vw] shrink-0 flex-col gap-1 lg:flex">
                        { marginalNote && (
                            <NoteRow testId="marginal-note" tone="warning">
                                { marginalNote }
                            </NoteRow>
                        ) }
                        { nearestPassNote && (
                            <NoteRow testId="nearest-pass-note" tone="info">
                                { nearestPassNote }
                            </NoteRow>
                        ) }
                    </div>
                ) }
                <div className="min-w-0 flex-1">{ content }</div>
                <div className={ cn('flex shrink-0 items-center', compact ? 'gap-1' : 'gap-1.5') }>
                    { !compact && onBestModeChange && (
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant={ bestMode ? 'primary' : 'outline' }
                                    size="sm"
                                    onClick={ () => onBestModeChange(!bestMode) }
                                    data-testid="timeline-best-mode-toggle"
                                    className="h-8 gap-1 px-2"
                                    aria-pressed={ bestMode }
                                >
                                    <Layers className="size-3.5" strokeWidth={ 1.75 } />
                                    <span className="hidden sm:inline">{ bestMode ? 'Best' : 'Source' }</span>
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                { bestMode
                                    ? 'Best-available mode: showing best source per date. Click to switch to source-specific mode.'
                                    : 'Switch to best-available mode: auto-selects the best source per date.' }
                            </TooltipContent>
                        </Tooltip>
                    ) }
                    { nextImage && (
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <span
                                    role="status"
                                    data-testid="timeline-next-image"
                                    className={ cn(
                                        'hidden h-8 items-center gap-1 rounded-md border border-border/60 bg-card/40 text-muted-foreground md:inline-flex',
                                        compact ? 'px-1.5 text-[12px]' : 'px-2 text-[13px]',
                                    ) }
                                >
                                    <CalendarClock className="size-3.5" strokeWidth={ 1.75 } />
                                    <span>
                                        { !compact && <span className="hidden lg:inline">Next expected pass </span> }
                                        <span className="font-mono tnum">{ nextImage.label }</span>
                                    </span>
                                </span>
                            </TooltipTrigger>
                            <TooltipContent>
                                Expected source pass. Imagery appears only after provider publication,
                                ingestion, and cloud/field quality checks.
                            </TooltipContent>
                        </Tooltip>
                    ) }
                    { selectable.length >= 2 && (
                        <PlaybackControls
                            dates={ selectable }
                            selectedDate={ selectedDate }
                            onSelect={ onSelect }
                            onPrefetch={ onPrefetchDate }
                        />
                    ) }
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={ atLatest || jumpTarget == null }
                        onClick={ () => jumpTarget && onSelect(jumpTarget) }
                        data-testid="timeline-jump-latest"
                        title="Jump to latest"
                        className="h-8 px-2"
                    >
                        <ChevronsRight className="size-4" strokeWidth={ 1.75 } />
                        <span className={ cn(compact ? 'hidden' : 'hidden sm:inline') }>Latest</span>
                    </Button>
                </div>
            </div>
        </section>
    );
}
