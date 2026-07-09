import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Field } from '@/types/api';
import { FieldCreateOptionsDialog } from '@/components/fields/FieldCreateOptionsDialog';

interface AddFieldDropdownProps {
  fields: Field[];
  onNavigate: (path: string) => void;
  /** When set, clicking a field calls this instead of navigating. */
  onSelectField?: (fieldId: string) => void;
  /** Pre‑selected season id to skip the season radio on the create page. */
  defaultSeasonId?: string | null;
  /** Optional class for the trigger button. */
  triggerClassName?: string;
  /** Optional data-testid prefix. */
  testId?: string;
}

export function AddFieldDropdown({
  fields,
  onNavigate,
  onSelectField,
  defaultSeasonId,
  triggerClassName = '',
  testId = 'add-field',
}: AddFieldDropdownProps) {
  const [open, setOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointer = (e: PointerEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('pointerdown', handlePointer);
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('pointerdown', handlePointer);
      window.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const normalizedQuery = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!normalizedQuery) return fields;
    return fields.filter((f) => f.name.toLowerCase().includes(normalizedQuery));
  }, [fields, normalizedQuery]);

  return (
    <div ref={ref} className="relative" data-testid={`${testId}-dropdown`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid={`${testId}-trigger`}
        className={cn(
          'glass flex h-9 items-center gap-1.5 rounded-md border px-2 text-[12px] font-medium text-foreground/80 transition-colors duration-fast',
          'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          open && 'border-primary/50 bg-primary/10 text-foreground',
          triggerClassName,
        )}
      >
        Add Field
        <ChevronDown className={cn('size-3.5 transition-transform duration-fast', open && 'rotate-180')} strokeWidth={1.75} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-1 w-72 rounded-md border border-border bg-popover shadow-e2"
          data-testid={`${testId}-panel`}
        >
          <div className="p-2">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields..."
              className="h-8 w-full rounded-md border border-input bg-background/55 pl-2 pr-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="max-h-60 overflow-y-auto border-t border-border/60">
            {filtered.length === 0 ? (
              <p className="px-3 py-4 text-center text-[12px] text-muted-foreground">
                {normalizedQuery ? 'No fields match your search.' : 'No fields yet.'}
              </p>
            ) : (
              filtered.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    if (onSelectField) {
                      onSelectField(f.id);
                    } else {
                      onNavigate(`/monitoring/field-analytics/field/${f.id}`);
                    }
                  }}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] text-foreground hover:bg-accent/40 transition-colors duration-fast"
                >
                  <span className="min-w-0 truncate">{f.name}</span>
                  <span className="shrink-0 text-[11px] text-muted-foreground tnum">
                    {f.areaHa != null ? `${f.areaHa.toFixed(1)} ha` : '—'}
                  </span>
                </button>
              ))
            )}
          </div>
          <div className="border-t border-border/60 p-2">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setDialogOpen(true);
              }}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-[12px] font-medium text-primary-foreground shadow-sm hover:bg-primary/90 transition-colors duration-fast"
            >
              <Plus className="size-3.5" strokeWidth={1.75} />
              Add field
            </button>
          </div>
        </div>
      )}
      <FieldCreateOptionsDialog open={dialogOpen} onOpenChange={setDialogOpen} defaultSeasonId={defaultSeasonId} />
    </div>
  );
}
