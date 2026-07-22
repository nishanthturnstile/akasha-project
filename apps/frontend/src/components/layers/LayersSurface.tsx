import { useEffect, useRef, type ReactNode } from 'react';
import { Layers, X } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { useIsDesktop } from '@/hooks/useMediaQuery';
import { cn } from '@/lib/utils';

interface LayersSurfaceProps {
    open: boolean;
    onClose: () => void;
    children: ReactNode;
}

/**
 * Responsive shell for the layer manager: a left drawer on desktop (non-modal,
 * map stays interactive) and a bottom sheet on mobile (modal with a dismiss
 * scrim). One component tree, two presentations — driven by `useIsDesktop`.
 */
export function LayersSurface({ open, onClose, children }: LayersSurfaceProps) {
    const isDesktop = useIsDesktop();
    const panelRef = useRef<HTMLDivElement | null>(null);

    // Escape closes from anywhere while open.
    useEffect(() => {
        if (!open) return;
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    // Move focus into the panel when it opens on mobile (modal behaviour).
    useEffect(() => {
        if (open && !isDesktop) panelRef.current?.focus();
    }, [open, isDesktop]);

    if (!open) return null;

    const header = (
        <div className="hero-pattern flex items-center justify-between gap-2 px-4 py-3">
            <div className="flex items-center gap-2">
                <Layers className="size-4 text-primary" strokeWidth={ 1.75 } />
                <h2 className="font-display text-base font-semibold tracking-[-0.01em]">Layers</h2>
            </div>
            <button
                type="button"
                aria-label="Close layers"
                data-testid="layers-close"
                onClick={ onClose }
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
                <X className="size-4" strokeWidth={ 1.75 } />
            </button>
        </div>
    );

    if (isDesktop) {
        return (
            <section
                ref={ panelRef }
                data-testid="layers-surface"
                data-variant="drawer"
                aria-label="Layer controls"
                className="glass pointer-events-auto z-panel w-rail max-w-[88vw] animate-drawer-in overflow-hidden"
            >
                { header }
                <Separator />
                <div className="max-h-[calc(100vh-13rem)] overflow-y-auto p-4">{ children }</div>
            </section>
        );
    }

    return (
        <div className="fixed inset-0 z-panel" data-testid="layers-surface-mobile">
            <button
                type="button"
                aria-label="Close layers"
                onClick={ onClose }
                className="absolute inset-0 z-overlay bg-[hsl(var(--scrim-to))] animate-fade-in"
                data-testid="layers-backdrop"
            />
            <section
                ref={ panelRef }
                tabIndex={ -1 }
                role="dialog"
                aria-modal="true"
                aria-label="Layer controls"
                data-testid="layers-surface"
                data-variant="sheet"
                className={ cn(
                    'glass absolute inset-x-0 bottom-0 z-panel max-h-[82vh] overflow-hidden rounded-b-none',
                    'animate-sheet-up pb-[env(safe-area-inset-bottom)]',
                ) }
            >
                <div className="flex justify-center pt-2">
                    <span className="h-1 w-10 rounded-pill bg-muted-foreground/40" aria-hidden="true" />
                </div>
                { header }
                <Separator />
                <div className="max-h-[62vh] overflow-y-auto p-4">{ children }</div>
            </section>
        </div>
    );
}
