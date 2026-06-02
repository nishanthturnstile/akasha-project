import { useCallback, useEffect, useMemo, useRef } from 'react';
import { AlertTriangle, ChevronsRight, Info, RefreshCw } from 'lucide-react';
import type { SceneDate, SourceKind } from '@/types/api';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { DateChip } from './DateChip';
import { PlaybackControls } from './PlaybackControls';

interface TimelineBarProps {
    dates: SceneDate[] | undefined;
    selectedDate: string | null;
    onSelect: (acquisitionDate: string) => void;
    sourceKind?: SourceKind;
    loading: boolean;
    error: string | null;
    onRetry: () => void;
    /** Surfaced when no date meets the usability threshold. */
    marginalNote?: string | null;
    /** Surfaced for the nearest radar pass (SAR sources). */
    nearestPassNote?: string | null;
    onPrefetchDate?: (acquisitionDate: string) => void;
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
                'flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px]',
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
    loading,
    error,
    onRetry,
    marginalNote,
    nearestPassNote,
    onPrefetchDate,
}: TimelineBarProps) {
    const trackRef = useRef<HTMLDivElement | null>(null);
    const selectedRef = useRef<HTMLButtonElement | null>(null);

    // Oldest → newest for left-to-right reading; only tile-available dates are selectable.
    const ordered = useMemo(() => {
        if (!dates) return [];
        return [...dates].sort((a, b) => a.acquisitionDate.localeCompare(b.acquisitionDate));
    }, [dates]);

    const selectable = useMemo(() => ordered.filter((d) => d.tileAvailable), [ordered]);

    const jumpTarget = useMemo(() => {
        if (selectable.length === 0) return null;
        const latestUsable = [...selectable].reverse().find((d) => d.isLatestUsable);
        return (latestUsable ?? selectable[selectable.length - 1]).acquisitionDate;
    }, [selectable]);

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
            <div className="flex gap-2" data-testid="timeline-loading">
                { [0, 1, 2, 3, 4, 5].map((i) => (
                    <Skeleton key={ i } className="h-[68px] w-[88px] shrink-0 rounded-lg" />
                )) }
            </div>
        );
    } else if (error) {
        content = (
            <div
                className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2"
                data-testid="timeline-error"
            >
                <span className="flex items-center gap-2 text-[13px] text-destructive">
                    <AlertTriangle className="size-4" strokeWidth={ 1.75 } /> { error }
                </span>
                <Button variant="outline" size="sm" onClick={ onRetry } data-testid="timeline-retry">
                    <RefreshCw className="size-4" strokeWidth={ 1.75 } /> Retry
                </Button>
            </div>
        );
    } else if (ordered.length === 0) {
        content = (
            <p className="py-4 text-[13px] text-muted-foreground" data-testid="timeline-empty">
                No acquisition dates available for this source.
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
                className="flex snap-x gap-2 overflow-x-auto pb-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
                { ordered.map((d) => {
                    const selected = d.acquisitionDate === selectedDate;
                    return (
                        <DateChip
                            key={ d.acquisitionDate }
                            ref={ selected ? selectedRef : undefined }
                            date={ d }
                            selected={ selected }
                            sourceKind={ sourceKind }
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
            className="glass pointer-events-auto z-panel animate-panel-in overflow-hidden px-3 pb-2 pt-2"
        >
            { (marginalNote || nearestPassNote) && (
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
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
            <div className="flex items-stretch gap-3">
                <div className="min-w-0 flex-1">{ content }</div>
                <div className="flex shrink-0 items-center gap-2">
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
                    >
                        <ChevronsRight className="size-4" strokeWidth={ 1.75 } />
                        <span className="hidden sm:inline">Latest</span>
                    </Button>
                </div>
            </div>
        </section>
    );
}
