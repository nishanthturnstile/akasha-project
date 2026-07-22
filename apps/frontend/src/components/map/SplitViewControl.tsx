import { Columns2, Square } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SplitViewControlProps {
  available: boolean;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
}

/** Persistent on-map control for entering and leaving the two-up map view. */
export function SplitViewControl({
  available,
  enabled,
  onEnabledChange,
}: SplitViewControlProps) {
  if (!available && !enabled) return null;

  const label = enabled ? 'Single View' : 'Split View';

  return (
    <div
      className="glass overflow-hidden rounded-md p-0 shadow-e1"
      data-testid="split-view-control"
      role="group"
      aria-label="View layout"
    >
      <button
        type="button"
        aria-label={ label }
        aria-pressed={ enabled }
        title={ label }
        data-testid="split-view-toggle"
        onClick={ () => onEnabledChange(!enabled) }
        className={ cn(
          'flex size-9 items-center justify-center text-foreground/80 transition-colors duration-fast ease-standard',
          'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          enabled && 'bg-primary/15 text-primary',
        ) }
      >
        { enabled ? (
          <Square className="size-5" strokeWidth={ 1.75 } aria-hidden="true" />
        ) : (
          <Columns2 className="size-5" strokeWidth={ 1.75 } aria-hidden="true" />
        ) }
      </button>
    </div>
  );
}
