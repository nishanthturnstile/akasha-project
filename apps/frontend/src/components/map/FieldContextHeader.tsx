import { Map as MapIcon, Pencil, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ThemeToggle';
import type { Plot } from '@/types/api';

interface FieldContextHeaderProps {
    /** Server-resolved plot, or `null` when no field is selected. */
    selectedPlot: Plot | null;
    /** Clear the active selection — equivalent to "back to all fields". */
    onBack: () => void;
    /** Enter geometry edit mode on the currently selected plot. */
    onEditGeometry: () => void;
    /** Open the command palette. */
    onOpenCommand: () => void;
}

function formatAreaHa(value: number | null | undefined): string {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return `${value.toFixed(1)} ha`;
}

/**
 * Top-of-canvas field chrome: back, field identity, validated area, edit,
 * add-field dropdown, and search trigger. Area is read from `plot.areaHa`
 * (server), never recomputed from polygon coordinates client-side (REQ-008).
 */

export function FieldContextHeader({
    selectedPlot,
    onBack,
    onEditGeometry,
    onOpenCommand,
}: FieldContextHeaderProps) {
    const hasSelection = Boolean(selectedPlot);
    const name = selectedPlot?.name ?? 'No field selected';
    const cropLine = [selectedPlot?.cropType, selectedPlot?.variety, selectedPlot?.seasonLabel]
        .filter(Boolean)
        .join(' · ');

    return (
        <div
            className="pointer-events-none absolute inset-x-0 top-4 z-toolbar flex items-center justify-between gap-3 px-4"
            data-testid="field-context-header"
        >
            <div className="pointer-events-auto glass flex h-12 max-w-160 items-center gap-2 rounded-md px-2 pr-3 shadow-e2">
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={ onBack }
                    disabled={ !hasSelection }
                    aria-label="Back to all fields"
                    data-testid="field-header-back"
                    className="size-9 rounded-md text-foreground/80 hover:bg-accent/60"
                >
                    <span aria-hidden="true" className="text-base leading-none">←</span>
                </Button>

                <div className="w-px self-stretch bg-border/60" />

                <div
                    className="flex size-9 shrink-0 items-center justify-center rounded-md border border-primary/40 bg-primary/10 text-primary"
                    aria-hidden="true"
                >
                    <MapIcon className="size-4" strokeWidth={ 1.75 } />
                </div>

                <div className="w-px self-stretch bg-border/60" />

                <div className="flex min-w-0 flex-col">
                    <div className="flex items-center gap-2 truncate font-display text-sm font-semibold tracking-tight text-foreground">
                        <span className="truncate" data-testid="field-header-name">{ name }</span>
                    </div>
                    { cropLine && (
                        <p className="truncate text-[11px] uppercase tracking-wide text-muted-foreground">
                            { cropLine }
                        </p>
                    ) }
                </div>

                <div className="w-px self-stretch bg-border/60" />

                <span
                    className="rounded border border-border/60 px-1.5 py-0.5 font-mono text-[11px] font-medium text-foreground/80"
                    data-testid="field-header-area"
                    title="Validated polygon area from BFF"
                >
                    { formatAreaHa(selectedPlot?.areaHa) }
                </span>

                <div className="w-px self-stretch bg-border/60" />

                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={ onEditGeometry }
                    disabled={ !hasSelection }
                    aria-label="Edit field geometry"
                    title="Edit boundary"
                    data-testid="field-header-edit"
                    className="size-9 rounded-md text-foreground/80 hover:bg-accent/60"
                >
                    <Pencil className="size-4" strokeWidth={ 1.75 } />
                </Button>

            </div>

            <div className="pointer-events-auto flex items-center gap-2">
                <button
                    type="button"
                    onClick={ onOpenCommand }
                    data-testid="command-trigger"
                    aria-label="Open command palette"
                    title="Search (Ctrl/⌘ K)"
                    className="glass flex h-10 items-center gap-2 rounded-md px-3 text-foreground/80 transition-colors duration-fast ease-standard hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                    <Search className="size-4" strokeWidth={ 1.75 } />
                    <kbd className="hidden font-mono text-[11px] text-muted-foreground sm:inline">⌘K</kbd>
                </button>
                <ThemeToggle />
            </div>
        </div>
    );
}
