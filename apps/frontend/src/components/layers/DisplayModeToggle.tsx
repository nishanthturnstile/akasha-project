import { Check } from 'lucide-react';
import type { LayerGroup } from '@/types/api';
import { modeLabel } from '@/lib/displayMode';
import { cn } from '@/lib/utils';

interface DisplayModeToggleProps {
    modes: string[];
    value: string;
    onChange: (mode: string) => void;
    /** EOS-style category grouping. When provided, renders a grouped vertical
     *  list (Natural Color / Vegetation Indices / Moisture Indices); otherwise a
     *  flat segmented control. */
    groups?: LayerGroup[] | null;
}

function ModeRow({
    mode,
    active,
    onSelect,
}: {
    mode: string;
    active: boolean;
    onSelect: () => void;
}) {
    return (
        <button
            type="button"
            role="radio"
            aria-checked={ active }
            data-testid={ `display-mode-${mode}` }
            onClick={ onSelect }
            className={ cn(
                'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-[12px] font-medium leading-none transition-colors duration-fast ease-standard',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                active
                    ? 'bg-primary/15 text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            ) }
        >
            <span>{ modeLabel(mode) }</span>
            { active && <Check className="size-3.5 text-primary" strokeWidth={ 2 } aria-hidden="true" /> }
        </button>
    );
}

/**
 * Render-mode picker for a source. When `groups` are supplied it renders an
 * EOS-style grouped vertical list (category headers + selectable rows); when not,
 * it falls back to the legacy segmented control. The active source's default mode
 * stays selected so true-colour remains the cold-start layer (CLAUDE.md guardrail).
 */
export function DisplayModeToggle({ modes, value, onChange, groups }: DisplayModeToggleProps) {
    // Only keep groups whose modes the source actually advertises, then drop empties.
    const resolvedGroups = (groups ?? [])
        .map((group) => ({
            label: group.label,
            modes: group.modes.filter((mode) => modes.includes(mode)),
        }))
        .filter((group) => group.modes.length > 0);

    if (resolvedGroups.length > 0) {
        return (
            <div
                role="radiogroup"
                aria-label="Display mode"
                data-testid="display-mode-toggle"
                className="flex flex-col gap-2.5"
            >
                { resolvedGroups.map((group) => (
                    <div key={ group.label } className="flex flex-col gap-0.5">
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                            { group.label }
                        </p>
                        { group.modes.map((mode) => (
                            <ModeRow
                                key={ mode }
                                mode={ mode }
                                active={ mode === value }
                                onSelect={ () => onChange(mode) }
                            />
                        )) }
                    </div>
                )) }
            </div>
        );
    }

    return (
        <div
            role="radiogroup"
            aria-label="Display mode"
            data-testid="display-mode-toggle"
            className="flex items-center gap-1 rounded-md bg-secondary/60 p-0.5"
        >
            { modes.map((mode) => {
                const active = mode === value;
                return (
                    <button
                        key={ mode }
                        type="button"
                        role="radio"
                        aria-checked={ active }
                        data-testid={ `display-mode-${mode}` }
                        onClick={ () => onChange(mode) }
                        className={ cn(
                            'flex-1 rounded-[5px] px-2 py-1 text-[12px] font-medium leading-none transition-colors duration-fast ease-standard',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            active
                                ? 'bg-primary/15 text-foreground shadow-e1'
                                : 'text-muted-foreground hover:text-foreground',
                        ) }
                    >
                        { modeLabel(mode) }
                    </button>
                );
            }) }
        </div>
    );
}