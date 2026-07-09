import { MapPin, MoreVertical, Plus, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useDeleteField, useFields, useSeasons, useUpdateField } from '@/lib/queries';
import { useMapView } from '@/state/useMapView';
import type { Field, GeoJsonPosition, PlotGeometry } from '@/types/api';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';

interface Props {
  onClose: () => void;
  seasonId: string | null;
}

function FieldMenu({
  field,
  onEdit,
  onDelete,
  isPinned,
  onPin,
  onUnpin,
}: {
  field: Field;
  onEdit: (field: Field) => void;
  onDelete: (field: Field) => void;
  isPinned: boolean;
  onPin: (field: Field) => void;
  onUnpin: (field: Field) => void;
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
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[130px] whitespace-nowrap rounded-md border border-border bg-popover py-1 shadow-e2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onEdit(field); }}
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
          >
            Edit
          </button>
          {isPinned ? (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setOpen(false); onUnpin(field); }}
              className="flex w-full items-center px-3 py-1.5 text-left text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
            >
              Unpin
            </button>
          ) : (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setOpen(false); onPin(field); }}
              className="flex w-full items-center px-3 py-1.5 text-left text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
            >
              Pin Field
            </button>
          )}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); }}
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
          >
            Export Contours
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); onDelete(field); }}
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-destructive hover:bg-accent/40 transition-colors duration-fast"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function extractRings(geometry: PlotGeometry): GeoJsonPosition[][] {
  if (geometry.type === 'Polygon') return [geometry.coordinates[0] ?? []];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map((poly) => poly[0] ?? []);
  return [];
}

export function FieldThumbnail({ geometry, size = 48 }: { geometry: PlotGeometry; size?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !geometry) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rings = extractRings(geometry);
    if (rings.length === 0) return;

    const lngs = rings.flat().map((p) => p[0]);
    const lats = rings.flat().map((p) => p[1]);
    const minLng = Math.min(...lngs);
    const maxLng = Math.max(...lngs);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);

    const pad = 4;
    const drawSize = size - pad * 2;
    const geoW = maxLng - minLng || 1;
    const geoH = maxLat - minLat || 1;
    const scale = Math.min(drawSize / geoW, drawSize / geoH);
    const cx = (maxLng + minLng) / 2;
    const cy = (maxLat + minLat) / 2;

    ctx.clearRect(0, 0, size, size);

    for (const ring of rings) {
      ctx.beginPath();
      for (let i = 0; i < ring.length; i++) {
        const x = pad + (ring[i][0] - cx) * scale + drawSize / 2;
        const y = pad + (cy - ring[i][1]) * scale + drawSize / 2;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.1)';
      ctx.fill();
    }
  }, [geometry, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="size-12 shrink-0 rounded-md border border-border/60 bg-card"
      aria-hidden="true"
    />
  );
}

function FieldCard({
  field,
  onEdit,
  onDelete,
  onSelect,
  selected,
  isPinned,
  onPin,
  onUnpin,
  seasonId,
}: {
  field: Field;
  onEdit: (field: Field) => void;
  onDelete: (field: Field) => void;
  onSelect?: (field: Field) => void;
  selected?: boolean;
  isPinned: boolean;
  onPin: (field: Field) => void;
  onUnpin: (field: Field) => void;
  seasonId?: string | null;
}) {
  const currentCycle = field.vegetationData?.find((v) => v.seasonId === seasonId);
  const cropLabel = currentCycle?.cropName ?? 'Unknown crop';
  return (
    <div
      className={ cn(
        'grid cursor-pointer grid-cols-[52px_1fr_auto] gap-x-3 rounded-lg border border-border/70 px-4 py-4 transition-colors duration-fast',
        selected
          ? 'border-l-[3px] border-l-primary bg-primary/5'
          : 'bg-card/35 hover:bg-accent/10',
      ) }
      onClick={ () => onSelect?.(field) }
      role="button"
      tabIndex={ 0 }
      onKeyDown={ (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(field); } } }
    >
      <div className="row-span-2 self-center">
        <FieldThumbnail geometry={field.geometry} size={52} />
      </div>

      <p className="min-w-0 self-center truncate text-base font-semibold text-foreground">
        {isPinned && <MapPin className="mr-1 inline size-3.5 text-primary" strokeWidth={1.75} />}
        {field.name}
      </p>
      <div className="self-center justify-self-end">
        <FieldMenu field={field} onEdit={onEdit} onDelete={onDelete} isPinned={isPinned} onPin={onPin} onUnpin={onUnpin} />
      </div>

      <span className="self-center truncate text-xs text-muted-foreground">{cropLabel}</span>
      <span className="self-center justify-self-end text-xs text-muted-foreground tnum">
        {field.areaHa != null ? `${field.areaHa.toFixed(2)} ha` : '—'}
      </span>
    </div>
  );
}

const LAST_FIELD_KEY = 'akasha.lastFieldPerSeason';
const PINNED_KEY = 'akasha.pinnedFields';

export function getLastFieldPerSeason(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(LAST_FIELD_KEY) ?? '{}');
  } catch {
    return {};
  }
}

export function setLastFieldForSeason(seasonId: string, fieldId: string) {
  try {
    const map = getLastFieldPerSeason();
    map[seasonId] = fieldId;
    localStorage.setItem(LAST_FIELD_KEY, JSON.stringify(map));
  } catch {
    // localStorage unavailable
  }
}

function getPinnedFields(): Record<string, string[]> {
  try {
    return JSON.parse(localStorage.getItem(PINNED_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function setPinnedFieldsForSeason(seasonId: string, fieldIds: string[]) {
  try {
    const map = getPinnedFields();
    map[seasonId] = fieldIds;
    localStorage.setItem(PINNED_KEY, JSON.stringify(map));
  } catch {
    // localStorage unavailable
  }
}

const EMPTY_CTA_BUTTONS = [
  { label: 'Add Field', icon: Plus, action: 'add-field' as const },
];

export default function GlobalViewPanel({ onClose, seasonId }: Props) {
  const fieldsQ = useFields();
  const seasonsQ = useSeasons();
  const deleteField = useDeleteField();
  const updateField = useUpdateField();
  const view = useMapView();
  const { selectedPlotId } = view;
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [editingField, setEditingField] = useState<Field | null>(null);
  const [deletingField, setDeletingField] = useState<Field | null>(null);
  const [savingField, setSavingField] = useState(false);

  const allFields = useMemo(() => (Array.isArray(fieldsQ.data) ? fieldsQ.data : []), [fieldsQ.data]);
  const allSeasons = useMemo(
    () => (Array.isArray(seasonsQ.data) ? seasonsQ.data : []),
    [seasonsQ.data],
  );

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

  const [pinnedFieldIds, setPinnedFieldIds] = useState<string[]>(() => {
    return seasonId ? (getPinnedFields()[seasonId] ?? []) : [];
  });

  const handlePin = (field: Field) => {
    if (!seasonId) return;
    const next = pinnedFieldIds.includes(field.id) ? pinnedFieldIds : [...pinnedFieldIds, field.id];
    setPinnedFieldIds(next);
    setPinnedFieldsForSeason(seasonId, next);
  };

  const handleUnpin = (field: Field) => {
    if (!seasonId) return;
    const next = pinnedFieldIds.filter((id) => id !== field.id);
    setPinnedFieldIds(next);
    setPinnedFieldsForSeason(seasonId, next);
  };

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredFields = useMemo(() => {
    const matched = !normalizedQuery
      ? seasonFields
      : seasonFields.filter((f) => {
          const searchable = [
            f.name,
            f.areaHa?.toString(),
            ...(f.seasonIds?.map((sid) => seasonNames[sid]).filter(Boolean) ?? []),
          ].filter(Boolean).join(' ').toLocaleLowerCase();
          return searchable.includes(normalizedQuery);
        });
    return [...matched].sort((a, b) => {
      const aPinned = pinnedFieldIds.includes(a.id) ? 0 : 1;
      const bPinned = pinnedFieldIds.includes(b.id) ? 0 : 1;
      if (aPinned !== bPinned) return aPinned - bPinned;
      return a.name.localeCompare(b.name);
    });
  }, [seasonFields, normalizedQuery, seasonNames, pinnedFieldIds]);

  const handleDelete = (field: Field) => {
    setDeletingField(field);
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
                          navigate(seasonId ? `/monitoring/field-create?seasonId=${seasonId}` : '/monitoring/field-create');
                        }
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md border-2 border-dashed border-primary/40 bg-primary/[0.08] px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary/[0.15] transition-colors duration-fast"
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
                  seasonId={seasonId}
                  selected={field.id === selectedPlotId}
                  isPinned={pinnedFieldIds.includes(field.id)}
                  onPin={handlePin}
                  onUnpin={handleUnpin}
                  onEdit={setEditingField}
                  onDelete={handleDelete}
                  onSelect={ (f) => {
                    if (seasonId) setLastFieldForSeason(seasonId, f.id);
                    view.setSelectedPlotId(f.id);
                    view.setFocusNonce(Date.now());
                    onClose();
                    navigate(`/monitoring/field-analytics/field/${f.id}`);
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
              navigate(seasonId ? `/monitoring/field-create?seasonId=${seasonId}` : '/monitoring/field-create');
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
          key={editingField.id}
          field={editingField}
          open={!!editingField}
          onOpenChange={(open) => { if (!open) setEditingField(null); }}
          onSave={(fieldId, name, geometry, vegetationData, groupId) => {
            setSavingField(true);
            updateField.mutate(
              { fieldId, payload: { name, ...(geometry ? { geometry } : {}), ...(vegetationData ? { vegetationData } : {}), ...(groupId !== undefined ? { groupId } : {}) } },
              { onSuccess: () => { setSavingField(false); setEditingField(null); }, onError: () => setSavingField(false) },
            );
          }}
          saving={savingField}
          onDelete={(fieldId) => deleteField.mutateAsync(fieldId)}
        />
      )}

      <AlertDialogRoot open={!!deletingField} onOpenChange={(open) => { if (!open) setDeletingField(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Delete field?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete "{deletingField?.name}"? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={async () => {
              if (!deletingField) return;
              try {
                await deleteField.mutateAsync(deletingField.id);
              } catch {
                // error handled by query state
              }
              setDeletingField(null);
            }}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </>
  );
}
