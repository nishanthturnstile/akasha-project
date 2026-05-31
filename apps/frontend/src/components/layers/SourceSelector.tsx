import type { Source } from '@/types/api';
import { cn } from '@/lib/utils';

interface SourceSelectorProps {
  sources: Source[];
  value: string | undefined;
  onChange: (sourceId: string) => void;
}

/** Segmented control of imagery sources. Active = saffron underline (not a fill). */
export function SourceSelector({ sources, value, onChange }: SourceSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Imagery source"
      className="flex items-center gap-1"
      data-testid="source-selector"
    >
      {sources.map((s) => {
        const active = s.id === value;
        return (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`source-tab-${s.id}`}
            onClick={() => onChange(s.id)}
            className={cn(
              'relative rounded-md px-2.5 py-1.5 text-[13px] font-medium leading-none transition-colors duration-fast ease-standard',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {s.label}
            {active && (
              <span className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-pill bg-primary" />
            )}
          </button>
        );
      })}
    </div>
  );
}
