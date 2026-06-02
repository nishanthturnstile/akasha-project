import { forwardRef } from 'react';
import type { SceneDate, SourceKind } from '@/types/api';
import { CloudUsabilityChip } from '@/components/layers/CloudUsabilityChip';
import { cn } from '@/lib/utils';

interface DateChipProps {
    date: SceneDate;
    selected: boolean;
    sourceKind?: SourceKind;
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
    { date, selected, sourceKind, onSelect, onPrefetch },
    ref,
) {
    const disabled = !date.tileAvailable;
    const { month, day } = shortLabel(date.acquisitionDate);
    const latestLabel = sourceKind === 'sar' ? 'Latest radar pass' : 'Latest usable scene';

    return (
        <button
            ref={ ref }
            type="button"
            role="option"
            aria-selected={ selected }
            aria-current={ selected }
            aria-label={ `${date.acquisitionDate}${date.isLatestUsable ? ` · ${latestLabel}` : ''}` }
            disabled={ disabled }
            data-testid={ `date-chip-${date.acquisitionDate}` }
            data-selected={ selected }
            onClick={ onSelect }
            onMouseEnter={ onPrefetch }
            onFocus={ onPrefetch }
            className={ cn(
                'group relative flex h-11 w-[64px] shrink-0 snap-start flex-col items-center justify-center gap-0 rounded-md border px-1 py-0.5 text-center transition-colors duration-fast ease-standard',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selected
                    ? 'border-primary/60 bg-primary/10 shadow-e1'
                    : 'border-border/60 bg-card/30 hover:border-border hover:bg-accent/50',
                disabled && 'cursor-not-allowed opacity-40 hover:border-border/60 hover:bg-card/30',
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
            <span className="leading-tight">
                <span className="block text-[9px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
                    { month }
                </span>
                <span className="block font-display text-[13px] font-semibold leading-none tracking-[-0.02em] text-foreground">
                    { day }
                </span>
            </span>
            <CloudUsabilityChip
                percent={ date.usablePixelPercent }
                coveragePercent={ date.coveragePercent }
                sourceKind={ sourceKind }
                className="max-w-full gap-1 overflow-hidden px-1 py-0 text-[9px] leading-3 [&>span:first-child]:size-1"
            />
        </button>
    );
});
