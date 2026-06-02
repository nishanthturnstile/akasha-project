import { useCallback, useState } from 'react';
import { Columns2 } from 'lucide-react';
import type { SceneDate } from '@/types/api';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';

interface CompareControlProps {
    enabled: boolean;
    onEnabledChange: (enabled: boolean) => void;
    /** Chronological, tile-available dates available as the "B" scene. */
    dates: SceneDate[];
    /** The active ("A") acquisition date. */
    activeDate: string | null;
    compareDate: string | null;
    onCompareDateChange: (date: string) => void;
    /** A-over-B blend, 0..100 (reuses the overlay opacity). */
    blend: number;
    onBlendChange: (blend: number) => void;
}

/**
 * Opacity-blend compare ("A over B") — NASA Worldview's simplest compare mode.
 * The timeline drives the A date; this control enables compare, picks the B date,
 * and the blend slider fades A over B (B sits beneath at full opacity). Swipe mode
 * is a future spike (needs two synced map instances).
 */
export function CompareControl({
    enabled,
    onEnabledChange,
    dates,
    activeDate,
    compareDate,
    onCompareDateChange,
    blend,
    onBlendChange,
}: CompareControlProps) {
    const [open, setOpen] = useState(false);

    const toggleOpen = useCallback(() => setOpen((p) => !p), []);

    const selectableB = dates.filter((d) => d.acquisitionDate !== activeDate);

    return (
        <div className="flex flex-col items-end gap-2" data-testid="compare-control">
            { open && (
                <div className="glass flex w-64 flex-col gap-2.5 rounded-md p-3" data-testid="compare-panel">
                    <label className="flex items-center justify-between gap-2">
                        <span className="text-[13px] font-medium text-foreground">Compare A over B</span>
                        <Switch
                            checked={ enabled }
                            onCheckedChange={ onEnabledChange }
                            data-testid="compare-switch"
                            aria-label="Enable compare"
                        />
                    </label>

                    { enabled && (
                        <>
                            <div className="flex flex-col gap-1">
                                <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                                    B scene
                                </span>
                                <div className="flex max-h-32 flex-col gap-1 overflow-y-auto pr-0.5" role="listbox" aria-label="Compare date">
                                    { selectableB.length === 0 && (
                                        <span className="px-1 py-1 text-[12px] text-muted-foreground">
                                            No other dates to compare.
                                        </span>
                                    ) }
                                    { selectableB.map((d) => {
                                        const selected = d.acquisitionDate === compareDate;
                                        return (
                                            <button
                                                key={ d.acquisitionDate }
                                                type="button"
                                                role="option"
                                                aria-selected={ selected }
                                                data-testid={ `compare-date-${d.acquisitionDate}` }
                                                onClick={ () => onCompareDateChange(d.acquisitionDate) }
                                                className={ cn(
                                                    'rounded px-2 py-1 text-left font-mono text-[12px] tabular-nums transition-colors duration-fast ease-standard',
                                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                                                    selected
                                                        ? 'bg-primary/15 text-foreground'
                                                        : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                                                ) }
                                            >
                                                { d.acquisitionDate }
                                            </button>
                                        );
                                    }) }
                                </div>
                            </div>

                            <div className="flex flex-col gap-1.5">
                                <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                                    <span>B</span>
                                    <span className="font-mono tabular-nums text-foreground/80">{ blend }%</span>
                                    <span>A</span>
                                </div>
                                <Slider
                                    min={ 0 }
                                    max={ 100 }
                                    step={ 1 }
                                    value={ [blend] }
                                    onValueChange={ (v) => onBlendChange(v[0]) }
                                    data-testid="compare-blend"
                                    aria-label="A over B blend"
                                />
                            </div>

                            { compareDate && (
                                <p className="text-[11px] leading-4 text-muted-foreground" data-testid="compare-caption">
                                    <span className="font-mono text-foreground/80">{ activeDate ?? '—' }</span> over{ ' ' }
                                    <span className="font-mono text-foreground/80">{ compareDate }</span>
                                </p>
                            ) }
                        </>
                    ) }
                </div>
            ) }

            <button
                type="button"
                aria-label={ open ? 'Close compare' : 'Compare two dates' }
                aria-expanded={ open }
                title="Compare"
                data-testid="compare-toggle"
                onClick={ toggleOpen }
                className={ cn(
                    'glass flex size-9 items-center justify-center rounded-md text-foreground/80 transition-colors duration-fast ease-standard',
                    'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    (open || enabled) && 'bg-primary/15 text-foreground',
                ) }
            >
                <Columns2 className="size-5" strokeWidth={ 1.75 } />
            </button>
        </div>
    );
}
