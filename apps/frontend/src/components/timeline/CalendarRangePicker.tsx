import { useEffect, useId, useRef, useState } from 'react';
import { CalendarRange, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface CalendarRangePickerProps {
    /** Inclusive lower bound (YYYY-MM-DD) or null. */
    from: string | null;
    /** Inclusive upper bound (YYYY-MM-DD) or null. */
    to: string | null;
    onChange: (from: string | null, to: string | null) => void;
    /** Disabled when no timeline dates are loaded. */
    disabled?: boolean;
}

/** Pretty short label for the trigger (e.g. `Mar 5 – Jun 4`). */
function shortRange(from: string | null, to: string | null): string | null {
    if (!from && !to) return null;
    const fmt = (iso: string) => {
        const [y, m, d] = iso.split('-');
        const months = [
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        ];
        return `${months[Number(m) - 1] ?? m} ${Number(d)}${y ? `, ${y.slice(2)}` : ''}`;
    };
    if (from && to) return `${fmt(from)} → ${fmt(to)}`;
    if (from) return `≥ ${fmt(from)}`;
    return `≤ ${fmt(to as string)}`;
}

/**
 * Hand-rolled date-range popover that drives the timeline `period_from` / `period_to`
 * window (URL-bridged via `useMapUrlState`). EOS surfaces this as a calendar control
 * to the left of the filmstrip; we mirror placement + behaviour with native inputs.
 */
export function CalendarRangePicker({ from, to, onChange, disabled }: CalendarRangePickerProps) {
    const [open, setOpen] = useState(false);
    const [draftFrom, setDraftFrom] = useState<string>(from ?? '');
    const [draftTo, setDraftTo] = useState<string>(to ?? '');
    const wrapperRef = useRef<HTMLDivElement | null>(null);
    const fromInputId = useId();
    const toInputId = useId();

    // Re-sync draft to props whenever the popover opens so stale edits don't bleed.
    useEffect(() => {
        if (open) {
            setDraftFrom(from ?? '');
            setDraftTo(to ?? '');
        }
    }, [open, from, to]);

    // Outside-click + Escape close (matches LayerControlBar popover pattern).
    useEffect(() => {
        if (!open) return undefined;
        const onPointer = (event: PointerEvent) => {
            const node = wrapperRef.current;
            if (node && event.target instanceof Node && !node.contains(event.target)) {
                setOpen(false);
            }
        };
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false);
        };
        window.addEventListener('pointerdown', onPointer);
        window.addEventListener('keydown', onKey);
        return () => {
            window.removeEventListener('pointerdown', onPointer);
            window.removeEventListener('keydown', onKey);
        };
    }, [open]);

    const triggerLabel = shortRange(from, to);
    const hasRange = Boolean(from || to);

    const apply = () => {
        const nextFrom = draftFrom || null;
        const nextTo = draftTo || null;
        // Normalise inverted bounds so the timeline filter never receives `from > to`.
        if (nextFrom && nextTo && nextFrom > nextTo) {
            onChange(nextTo, nextFrom);
        } else {
            onChange(nextFrom, nextTo);
        }
        setOpen(false);
    };

    const clear = () => {
        setDraftFrom('');
        setDraftTo('');
        onChange(null, null);
        setOpen(false);
    };

    return (
        <div ref={ wrapperRef } className="relative shrink-0">
            <Tooltip>
                <TooltipTrigger asChild>
                    <button
                        type="button"
                        aria-haspopup="dialog"
                        aria-expanded={ open }
                        aria-label={ triggerLabel ? `Period ${triggerLabel}` : 'Set period' }
                        data-testid="timeline-period-trigger"
                        data-active={ hasRange }
                        disabled={ disabled }
                        onClick={ () => setOpen((prev) => !prev) }
                        className={ cn(
                            'glass inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-[12px] font-medium transition-colors duration-fast ease-standard',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            hasRange
                                ? 'border-primary/50 bg-primary/10 text-foreground'
                                : 'border-border/60 text-foreground hover:bg-accent/40',
                            disabled && 'cursor-not-allowed opacity-50',
                        ) }
                    >
                        <CalendarRange className="size-4" strokeWidth={ 1.75 } />
                        { triggerLabel && (
                            <span className="font-mono tnum text-[11px]">{ triggerLabel }</span>
                        ) }
                    </button>
                </TooltipTrigger>
                <TooltipContent>{ triggerLabel ? `Period ${triggerLabel}` : 'Set period (from/to)' }</TooltipContent>
            </Tooltip>

            { open && (
                <div
                    role="dialog"
                    aria-label="Pick a date range"
                    data-testid="timeline-period-popover"
                    className="glass absolute bottom-full left-0 z-popover mb-2 w-64 rounded-md p-3 shadow-e2"
                >
                    <div className="mb-2 flex items-center justify-between">
                        <span className="text-[12px] font-medium text-foreground">Filter by period</span>
                        { hasRange && (
                            <button
                                type="button"
                                onClick={ clear }
                                data-testid="timeline-period-clear"
                                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                            >
                                <X className="size-3" strokeWidth={ 1.75 } /> Clear
                            </button>
                        ) }
                    </div>
                    <div className="flex flex-col gap-2">
                        <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                            <span>From</span>
                            <input
                                id={ fromInputId }
                                type="date"
                                value={ draftFrom }
                                max={ draftTo || undefined }
                                onChange={ (event) => setDraftFrom(event.target.value) }
                                data-testid="timeline-period-from"
                                className="h-8 rounded-md border border-border/60 bg-card/40 px-2 text-[12px] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </label>
                        <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                            <span>To</span>
                            <input
                                id={ toInputId }
                                type="date"
                                value={ draftTo }
                                min={ draftFrom || undefined }
                                onChange={ (event) => setDraftTo(event.target.value) }
                                data-testid="timeline-period-to"
                                className="h-8 rounded-md border border-border/60 bg-card/40 px-2 text-[12px] text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </label>
                    </div>
                    <div className="mt-3 flex justify-end gap-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={ () => setOpen(false) }
                            className="h-7 px-2 text-[12px]"
                        >
                            Cancel
                        </Button>
                        <Button
                            size="sm"
                            onClick={ apply }
                            data-testid="timeline-period-apply"
                            className="h-7 px-2 text-[12px]"
                        >
                            Apply
                        </Button>
                    </div>
                </div>
            ) }
        </div>
    );
}
