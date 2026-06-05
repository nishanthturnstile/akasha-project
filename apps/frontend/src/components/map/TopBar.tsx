import { Search } from 'lucide-react';
import { ThemeToggle } from '@/components/ThemeToggle';
import { LayersToggleButton } from '@/components/layers/LayersToggleButton';

interface TopBarProps {
    layersOpen: boolean;
    onToggleLayers: () => void;
    onOpenCommand: () => void;
}

/**
 * Floating top chrome: Layers entry (left), search + theme (right). Anchored
 * over the map; the center stays clear for the canvas.
 */
export function TopBar({ layersOpen, onToggleLayers, onOpenCommand }: TopBarProps) {
    return (
        <div className="pointer-events-none absolute inset-x-0 top-4 z-toolbar flex items-center justify-between px-4">
            <div className="pointer-events-auto">
                <LayersToggleButton open={ layersOpen } onClick={ onToggleLayers } />
            </div>

            <div className="pointer-events-auto flex items-center gap-2">
                <button
                    type="button"
                    onClick={ onOpenCommand }
                    data-testid="command-trigger"
                    aria-label="Open command palette"
                    title="Search (Ctrl/⌘ K)"
                    className="glass flex h-9 items-center gap-2 rounded-pill px-3 text-foreground/80 transition-colors duration-fast ease-standard hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                    <Search className="size-4" strokeWidth={ 1.75 } />
                    <kbd className="hidden font-mono text-[11px] text-muted-foreground sm:inline">⌘K</kbd>
                </button>
                <ThemeToggle />
            </div>
        </div>
    );
}
