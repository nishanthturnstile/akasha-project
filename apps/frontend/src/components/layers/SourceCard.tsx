import { CalendarDays, Info, Lock } from 'lucide-react';
import type { Source } from '@/types/api';
import { cn } from '@/lib/utils';
import { OpacitySlider } from './OpacitySlider';
import { VisibilityToggle } from './VisibilityToggle';
import { SourceMetadata } from './SourceMetadata';
import { DisplayModeToggle } from './DisplayModeToggle';

interface SourceCardProps {
    source: Source;
    active: boolean;
    selectedDate: string | null;
    displayMode: string;
    visible: boolean;
    opacity: number;
    onSelect: () => void;
    onDisplayModeChange: (mode: string) => void;
    onVisibleChange: (visible: boolean) => void;
    onOpacityChange: (opacity: number) => void;
    /** Prefetch this source's dates on hover/focus (instant switch). */
    onPrefetch?: () => void;
}

/**
 * One imagery source. Inactive cards are a compact, clickable summary; the active
 * card expands to expose date echo, render mode, opacity and visibility — the layer
 * controls that used to live in the old single-panel `LayerPanel`.
 */
export function SourceCard({
    source,
    active,
    selectedDate,
    displayMode,
    visible,
    opacity,
    onSelect,
    onDisplayModeChange,
    onVisibleChange,
    onOpacityChange,
    onPrefetch,
}: SourceCardProps) {
    const isSar = source.kind === 'sar';
    const isGated = source.availabilityStatus === 'gated';
    const modes = source.mapDisplayModes ?? source.displayModes ?? [];
    const limitations = source.limitations ?? [];
    const showModeToggle = active && modes.length > 1;

    return (
        <div
            data-testid={ `source-card-${source.id}` }
            data-active={ active }
            className={ cn(
                'rounded-lg border transition-colors duration-fast ease-standard',
                active
                    ? 'border-primary/50 bg-primary/[0.06] shadow-e1'
                    : 'border-border/70 bg-card/40 hover:border-border hover:bg-accent/40',
            ) }
        >
            <button
                type="button"
                role="radio"
                aria-checked={ active }
                data-testid={ `source-tab-${source.id}` }
                onClick={ onSelect }
                onMouseEnter={ onPrefetch }
                onFocus={ onPrefetch }
                className="flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
                <span
                    aria-hidden="true"
                    className={ cn(
                        'mt-1 flex size-3.5 shrink-0 items-center justify-center rounded-pill border',
                        active ? 'border-primary' : 'border-muted-foreground/50',
                    ) }
                >
                    { active && <span className="size-1.5 rounded-pill bg-primary" /> }
                </span>
                <span className="min-w-0 flex-1">
                    <span className="block truncate font-display text-[14px] font-semibold tracking-[-0.01em] text-foreground">
                        { source.label }
                    </span>
                    <SourceMetadata source={ source } />
                </span>
            </button>

            { active && (
                <div className="flex flex-col gap-3 border-t border-border/60 px-3 py-3">
                    { source.description && (
                        <p className="text-[12px] leading-4 text-muted-foreground" data-testid="source-note">
                            { source.description }
                        </p>
                    ) }

                    { isSar && (
                        <div
                            className="flex items-start gap-2 rounded-md border border-info/30 bg-info/10 px-2.5 py-2 text-[12px] text-info"
                            data-testid="sar-source-note"
                        >
                            <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={ 1.75 } />
                            <span>Radar layer · cloud-penetrating · not true colour</span>
                        </div>
                    ) }

                    { isGated && (
                        <div
                            className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-2 text-[12px] text-warning"
                            data-testid="source-gated-note"
                        >
                            <Lock className="mt-0.5 size-3.5 shrink-0" strokeWidth={ 1.75 } />
                            <span>{ source.gatedReason ?? 'This source is gated pending validation.' }</span>
                        </div>
                    ) }

                    { limitations.length > 0 && (
                        <div
                            className="flex flex-col gap-1.5 rounded-md border border-border/60 bg-card/35 px-2.5 py-2"
                            data-testid="source-limitations"
                        >
                            <div className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                                <Info className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
                                Limitations
                            </div>
                            <ul className="flex list-disc flex-col gap-1 pl-4 text-[12px] leading-4 text-muted-foreground">
                                { limitations.map((limitation) => (
                                    <li key={ limitation }>{ limitation }</li>
                                )) }
                            </ul>
                        </div>
                    ) }

                    { selectedDate && (
                        <p
                            className="flex items-center gap-1.5 text-[12px] text-muted-foreground"
                            data-testid="source-selected-date"
                        >
                            <CalendarDays className="size-3.5" strokeWidth={ 1.75 } />
                            <span className="font-mono tnum text-foreground">{ selectedDate }</span>
                        </p>
                    ) }

                    { showModeToggle && (
                        <div className="flex flex-col gap-1.5">
                            <span className="text-[12px] font-medium text-muted-foreground">Display mode</span>
                            <DisplayModeToggle
                                modes={ modes }
                                value={ displayMode }
                                onChange={ onDisplayModeChange }
                            />
                        </div>
                    ) }

                    <VisibilityToggle checked={ visible } onCheckedChange={ onVisibleChange } />
                    <OpacitySlider value={ opacity } onChange={ onOpacityChange } disabled={ !visible } />
                </div>
            ) }
        </div>
    );
}
