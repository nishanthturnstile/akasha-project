import { MoreVertical, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScrollArea } from '@/components/ui/scroll-area';
import { GeometryPreview } from '@/lib/geometry-preview';
import { useDeleteField, useFields, useSeasons } from '@/lib/queries';
import { useMapView } from '@/state/useMapView';
import type { Field } from '@/types/api';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';

interface Props {
  onClose: () => void;
  seasonId: string | null;
}

function FieldMenu({
  field,
  onEdit,
  onDelete,
}: {
  field: Field;
  onEdit: (field: Field) => void;
  onDelete: (field: Field) => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-colors duration-fast"
        aria-label={`Field options for ${field.name}`}
      >
        <MoreVertical className="size-4" strokeWidth={1.75} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[140px] rounded-md border border-border bg-popover py-1 shadow-e2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onEdit(field); }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
          >
            <Pencil className="size-3.5" strokeWidth={1.75} />
            Edit
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onDelete(field); }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-destructive hover:bg-accent/40 transition-colors duration-fast"
          >
            <Trash2 className="size-3.5" strokeWidth={1.75} />
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function FieldCard({
  field,
  seasonNames,
  onEdit,
  onDelete,
  onSelect,
}: {
  field: Field;
  seasonNames: Record<string, string>;
  onEdit: (field: Field) => void;
  onDelete: (field: Field) => void;
  onSelect?: (field: Field) => void;
}) {
  const fieldSeasonNames = field.seasonIds
    ?.map((sid) => seasonNames[sid])
    .filter(Boolean) ?? [];

  return (
    <div
      className="flex cursor-pointer items-center gap-3 rounded-lg border border-border/70 bg-card/35 px-3 py-2.5 transition-colors duration-fast hover:bg-accent/10"
      onClick={ () => onSelect?.(field) }
      role="button"
      tabIndex={ 0 }
      onKeyDown={ (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(field); } } }
    >
      <GeometryPreview
        geometry={field.geometry}
        width={48}
        height={48}
        className="shrink-0 rounded-sm border border-border/40 bg-muted/30"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{field.name}</p>
        <p className="text-xs text-muted-foreground tnum">
          {field.areaHa != null ? `${field.areaHa.toFixed(2)} ha` : '—'}
        </p>
        {fieldSeasonNames.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {fieldSeasonNames.map((name) => (
              <span
                key={name}
                className="inline-block rounded-sm bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary/80"
              >
                {name}
              </span>
            ))}
          </div>
        )}
      </div>
      <FieldMenu field={field} onEdit={onEdit} onDelete={onDelete} />
    </div>
  );
}

const EMPTY_CTA_BUTTONS = [
  { label: 'Add Field', icon: Plus, action: 'add-field' as const },
  { label: 'Browse Map', icon: Search, action: 'browse-map' as const },
];

export default function GlobalViewPanel({ onClose, seasonId }: Props) {
  const fieldsQ = useFields();
  const seasonsQ = useSeasons();
  const deleteField = useDeleteField();
  const view = useMapView();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [editingField, setEditingField] = useState<Field | null>(null);

  const allFields = useMemo(() => fieldsQ.data ?? [], [fieldsQ.data]);
  const allSeasons = useMemo(() => seasonsQ.data ?? [], [seasonsQ.data]);

  const currentSeason = useMemo(() => {
    if (!seasonId) return null;
    return allSeasons.find((s) => s.id === seasonId) ?? null;
  }, [allSeasons, seasonId]);

  const seasonFields = useMemo(() => {
    if (!seasonId) return allFields;
    return allFields.filter((f) => f.seasonIds?.includes(seasonId));
  }, [allFields, seasonId]);

  const seasonNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const s of allSeasons) {
      map[s.id] = s.name;
    }
    return map;
  }, [allSeasons]);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredFields = useMemo(() => {
    if (!normalizedQuery) return seasonFields;
    return seasonFields.filter((f) => {
      const searchable = [
        f.name,
        f.areaHa?.toString(),
        ...(f.seasonIds?.map((sid) => seasonNames[sid]).filter(Boolean) ?? []),
      ].filter(Boolean).join(' ').toLocaleLowerCase();
      return searchable.includes(normalizedQuery);
    });
  }, [seasonFields, normalizedQuery, seasonNames]);

  const handleDelete = async (field: Field) => {
    if (!window.confirm(`Delete field "${field.name}"? This action cannot be undone.`)) return;
    try {
      await deleteField.mutateAsync(field.id);
    } catch {
      // error handled by query state
    }
  };

  return (
    <>
      <div className="flex h-full w-80 flex-col border-l border-border bg-background/96">
        <header className="flex items-center justify-between border-b border-border/60 px-4 py-4">
          <div>
            <h2 className="font-display text-base font-semibold text-foreground">Global View</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {currentSeason
                ? `${currentSeason.name} (${seasonFields.length} field${seasonFields.length !== 1 ? 's' : ''})`
                : `${seasonFields.length} field${seasonFields.length !== 1 ? 's' : ''}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close global view"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent/40"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="flex flex-col gap-3 px-4 py-3">
          <label className="relative block">
            <span className="sr-only">Search fields</span>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              strokeWidth={1.75}
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields, seasons…"
              className="h-9 w-full rounded-md border border-input bg-background/55 pl-9 pr-3 text-[13px] text-foreground shadow-e1 transition-colors duration-fast placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>

        <ScrollArea className="flex-1 px-4 pb-4">
          {fieldsQ.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-border/70 bg-card/35 px-3 py-2.5">
                  <div className="size-12 shrink-0 rounded-sm bg-muted/50 animate-pulse" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3.5 w-28 rounded bg-muted/50 animate-pulse" />
                    <div className="h-3 w-16 rounded bg-muted/50 animate-pulse" />
                  </div>
                </div>
              ))}
            </div>
          ) : fieldsQ.error ? (
            <p className="text-sm text-destructive">Failed to load fields.</p>
          ) : filteredFields.length === 0 ? (
            normalizedQuery ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border/80 bg-card/35 px-4 py-8 text-center">
                <p className="text-sm font-medium text-foreground">No fields match your search</p>
                <p className="text-xs text-muted-foreground">Try a different search term.</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border/80 bg-card/35 px-4 py-8 text-center">
                <p className="text-sm font-medium text-foreground">
                  {currentSeason ? `"${currentSeason.name}" has no fields yet` : 'No fields yet'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {currentSeason ? 'Add a field to this season to get started.' : 'Add a field to get started.'}
                </p>
                <div className="flex flex-wrap justify-center gap-2 pt-1">
                  {EMPTY_CTA_BUTTONS.map((btn) => (
                    <button
                      key={btn.action}
                      type="button"
                      onClick={() => {
                        if (btn.action === 'add-field') {
                          onClose();
                          navigate('/monitoring/field-create');
                        }
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors duration-fast"
                    >
                      <btn.icon className="size-3.5" strokeWidth={1.75} />
                      {btn.label}
                    </button>
                  ))}
                </div>
              </div>
            )
          ) : (
            <div className="space-y-2">
              {filteredFields.map((field) => (
                <FieldCard
                  key={field.id}
                  field={field}
                  seasonNames={seasonNames}
                  onEdit={setEditingField}
                  onDelete={handleDelete}
                  onSelect={ (f) => {
                    view.setSelectedPlotId(f.id);
                    view.setFocusNonce(Date.now());
                  } }
                />
              ))}
            </div>
          )}
        </ScrollArea>

        <div className="shrink-0 border-t border-border/60 px-4 py-3">
          <button
            type="button"
            onClick={ () => {
              onClose();
              navigate('/monitoring/field-create');
            } }
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 active:bg-primary/80 transition-colors duration-fast"
          >
            <Plus className="size-4" strokeWidth={1.75} />
            Add field
          </button>
        </div>
      </div>

      {editingField && (
        <EditFieldDialog
          field={editingField}
          open={!!editingField}
          onOpenChange={(open) => { if (!open) setEditingField(null); }}
        />
      )}
    </>
  );
}
