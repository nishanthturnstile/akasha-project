import { cn } from '@/lib/utils';

interface DisplayModeToggleProps {
    modes: string[];
    value: string;
    onChange: (mode: string) => void;
}

/** Human label for an internal display-mode token (e.g. `VV_GRAYSCALE` → `VV`). */
function modeLabel(mode: string): string {
    switch (mode) {
        case 'RGB':
            return 'True colour';
        case 'NDVI':
            return 'NDVI';
        case 'NDRE':
            return 'NDRE';
        case 'NDMI':
            return 'NDMI';
        case 'MSAVI':
            return 'MSAVI';
        case 'RECI':
            return 'RECI';
        case 'FALSE_COLOR_URBAN':
            return 'False colour';
        case 'FALSE_COLOR':
            return 'False colour';
        case 'VV_GRAYSCALE':
            return 'VV';
        case 'VH_GRAYSCALE':
            return 'VH';
        default:
            return mode.replace(/_/g, ' ');
    }
}

/**
 * Segmented control for a source's render modes. Only meaningful when a source
 * exposes more than one mode; the active source's default mode stays selected
 * so true-colour remains the cold-start layer (CLAUDE.md guardrail).
 */
export function DisplayModeToggle({ modes, value, onChange }: DisplayModeToggleProps) {
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
