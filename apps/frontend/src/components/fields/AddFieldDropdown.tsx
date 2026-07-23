import { useEffect, useMemo, useRef, useState } from 'react';
import { Triangle, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Field } from '@/types/api';
import { FieldCreateOptionsDialog } from '@/components/fields/FieldCreateOptionsDialog';
import { FieldThumbnail } from '@/components/fields/GlobalViewPanel';

interface AddFieldDropdownProps {
  fields: Field[];
  onNavigate: (path: string) => void;
  /** When set, clicking a field calls this instead of navigating. */
  onSelectField?: (fieldId: string) => void;
  /** Pre‑selected season id to skip the season radio on the create page. */
  defaultSeasonId?: string | null;
  /** Field currently selected on the map — gets highlighted. */
  selectedFieldId?: string | null;
  /** Optional class for the trigger button. */
  triggerClassName?: string;
  /** Optional data-testid prefix. */
  testId?: string;
}

function latestCropName(field: Field, seasonId?: string | null): string | null {
  if (!field.vegetationData || field.vegetationData.length === 0) return null;
  const cycles = seasonId
    ? field.vegetationData.filter((v) => v.seasonId === seasonId)
    : field.vegetationData;
  if (cycles.length === 0) return null;
  const sorted = [...cycles].sort((a, b) => {
    const yearA = a.year ?? 0;
    const yearB = b.year ?? 0;
    if (yearB !== yearA) return yearB - yearA;
    const dateA = a.sowingDate ? new Date(a.sowingDate).getTime() : 0;
    const dateB = b.sowingDate ? new Date(b.sowingDate).getTime() : 0;
    return dateB - dateA;
  });
  return sorted[0].cropName ?? null;
}

export function AddFieldDropdown({
  fields,
  onNavigate,
  onSelectField,
  defaultSeasonId,
  selectedFieldId,
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
          'flex h-8 items-center gap-1.5 rounded-md bg-muted/30 px-2 text-[13px] font-medium text-foreground/80 transition-colors duration-fast',
          'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
           open && 'bg-primary/10 text-foreground',
          triggerClassName,
        )}
      >
        Add fields
        <Triangle className={cn('size-3 transition-transform duration-fast text-muted-foreground/70 rotate-180', open && 'rotate-0')} fill="currentColor" />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full z-popover mt-1 w-80 rounded-md border border-border bg-popover shadow-e2 flex flex-col max-h-[calc(100vh-12rem)]"
          data-testid={`${testId}-panel`}
        >
          <div className="p-2 shrink-0">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields..."
              className="h-8 w-full rounded-md border border-input bg-background/55 pl-2 pr-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex-1 overflow-y-auto scroll-visible border-t border-border/60">
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
                  className={cn(
                    'grid w-full cursor-pointer grid-cols-[48px_1fr] gap-x-5 px-5 py-5 text-left text-foreground transition-colors duration-fast',
                    f.id === selectedFieldId
                      ? 'border-l-[3px] border-l-primary bg-primary/5'
                      : 'bg-card/35 hover:bg-accent/10',
                  )}
                >
                  <div className="row-span-2 self-center">
                    <FieldThumbnail geometry={f.geometry} size={48} />
                  </div>
                  <span className="min-w-0 self-center truncate text-base font-semibold">{f.name}</span>
                  <div className="flex flex-col self-center text-sm text-muted-foreground tnum">
                    <span>{f.areaHa != null ? `${f.areaHa.toFixed(1)} ha` : '—'}</span>
                    {(() => {
                      const crop = latestCropName(f, defaultSeasonId);
                      return crop ? <span className="text-xs text-muted-foreground/60">{crop}</span> : null;
                    })()}
                  </div>
                </button>
              ))
            )}
          </div>
          <div className="shrink-0 border-t border-border/60 p-2">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setDialogOpen(true);
              }}
              className="flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm hover:bg-primary/90 transition-colors duration-fast"
            >
              <Plus className="size-4" strokeWidth={2} />
              Add field
            </button>
          </div>
        </div>
      )}
      <FieldCreateOptionsDialog open={dialogOpen} onOpenChange={setDialogOpen} defaultSeasonId={defaultSeasonId} />
    </div>
  );
}
