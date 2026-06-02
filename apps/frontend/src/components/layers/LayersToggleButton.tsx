import { Layers } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LayersToggleButtonProps {
    open: boolean;
    onClick: () => void;
}

/** Collapsed entry point for the Layers surface (glass pill in the top bar). */
export function LayersToggleButton({ open, onClick }: LayersToggleButtonProps) {
    return (
        <button
            type="button"
            onClick={ onClick }
            aria-expanded={ open }
            aria-label={ open ? 'Hide layers' : 'Show layers' }
            data-testid="layers-toggle"
            className={ cn(
                'glass flex h-10 items-center gap-2 rounded-pill px-3.5 text-[13px] font-medium text-foreground',
                'transition-transform duration-fast ease-standard hover:scale-[1.02]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                open && 'ring-2 ring-primary/40',
            ) }
        >
            <Layers className="size-4 text-primary" strokeWidth={ 1.75 } />
            Layers
        </button>
    );
}
