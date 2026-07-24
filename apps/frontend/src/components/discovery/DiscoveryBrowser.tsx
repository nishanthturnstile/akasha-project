import { Filter, MapPin, MoreVertical, Pin, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetRoot,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { useDiscoveryUrlState } from '@/hooks/useDiscoveryUrlState';
import {
  useFieldDiscovery,
  useFieldDiscoveryFacets,
  useScoutTaskDiscovery,
  useUpdateScoutTask,
} from '@/lib/queries';
import { cn } from '@/lib/utils';
import { useMapView } from '@/state/useMapView';
import type {
  DiscoveryFieldSummary,
  DiscoverySort,
  DiscoveryTaskSummary,
} from '@/types/api';

const PINNED_KEY = 'akasha.pinnedFields';
const SORT_OPTIONS: Array<{ value: DiscoverySort; label: string }> = [
  { value: 'name_asc', label: 'Name A–Z' },
  { value: 'name_desc', label: 'Name Z–A' },
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'area_asc', label: 'Area Low→High' },
  { value: 'area_desc', label: 'Area High→Low' },
];

function readPins(seasonId: string): string[] {
  try {
    const all = JSON.parse(localStorage.getItem(PINNED_KEY) ?? '{}') as Record<string, string[]>;
    return all[seasonId] ?? [];
  } catch {
    return [];
  }
}

function writePins(seasonId: string, fieldIds: string[]) {
  try {
    const all = JSON.parse(localStorage.getItem(PINNED_KEY) ?? '{}') as Record<string, string[]>;
    all[seasonId] = fieldIds;
    localStorage.setItem(PINNED_KEY, JSON.stringify(all));
  } catch {
    // Storage can be unavailable; the in-memory selection still works.
  }
}

function FieldCard({
  field,
  pinned,
  selected,
  onPin,
  onFind,
  onOpen,
}: {
  field: DiscoveryFieldSummary;
  pinned: boolean;
  selected: boolean;
  onPin: () => void;
  onFind: () => void;
  onOpen: () => void;
}) {
  const location = [field.district, field.country].filter(Boolean).join(', ');
  return (
    <article
      className={cn(
        'rounded-lg border bg-card/60 p-3',
        selected ? 'border-l-[3px] border-l-primary border-y-primary/40 border-r-primary/40' : 'border-border/70',
      )}
      aria-current={selected ? 'true' : undefined}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" title={field.name}>{field.name}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground" title={field.crop?.name ?? 'No crop'}>
            {field.crop?.name ?? 'No crop'}{field.group ? ` · ${field.group.name}` : ''}
          </p>
          {location && <p className="truncate text-xs text-muted-foreground" title={location}>{location}</p>}
        </div>
        <div className="flex shrink-0 items-start gap-1">
          <span className="pt-1 text-xs text-muted-foreground tnum">
            {field.areaHa == null ? '—' : `${field.areaHa.toFixed(2)} ha`}
          </span>
          <details className="relative">
            <summary
              className="flex size-7 cursor-pointer list-none items-center justify-center rounded-md hover:bg-accent"
              aria-label={`Field options for ${field.name}`}
            >
              <MoreVertical className="size-4" />
            </summary>
            <div className="absolute right-0 z-popover mt-1 w-36 rounded-md border border-border bg-popover p-1 shadow-e2">
              <button
                type="button"
                className="w-full rounded px-2 py-2 text-left text-xs hover:bg-accent"
                onClick={onOpen}
              >
                Open analytics
              </button>
            </div>
          </details>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <button
          type="button"
          className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs hover:bg-accent"
          onClick={onPin}
          aria-label={`${pinned ? 'Unpin' : 'Pin'} ${field.name}`}
        >
          <Pin className="size-3.5" aria-hidden="true" />
          {pinned ? 'Unpin' : 'Pin'}
        </button>
        <button
          type="button"
          className="inline-flex min-h-9 items-center gap-1.5 rounded-md bg-primary px-2.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          onClick={onFind}
          aria-label={`Find ${field.name} on map`}
        >
          <MapPin className="size-3.5" aria-hidden="true" />
          Find Field
        </button>
      </div>
    </article>
  );
}

function TaskCard({
  task,
  selected,
  onFind,
}: {
  task: DiscoveryTaskSummary;
  selected: boolean;
  onFind: () => void;
}) {
  const updateTask = useUpdateScoutTask();
  const name = task.field?.name ?? task.fieldNameSnapshot ?? 'Unavailable field';
  return (
    <article
      className={cn(
        'rounded-lg border bg-card/60 p-3',
        selected ? 'border-l-[3px] border-l-primary border-y-primary/40 border-r-primary/40' : 'border-border/70',
      )}
      aria-current={selected ? 'true' : undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-semibold" title={name}>{name}</p>
        <span className="rounded-pill bg-muted px-2 py-0.5 text-[11px] capitalize">{task.priority}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground" title={task.notes ?? 'No notes'}>
        {task.notes ?? 'No notes'}
      </p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          className="min-h-9 rounded-md border border-border px-2.5 text-xs hover:bg-accent"
          disabled={updateTask.isPending}
          onClick={() => void updateTask.mutateAsync({
            taskId: task.id,
            payload: { status: task.status === 'new' ? 'closed' : 'new' },
          })}
        >
          {task.status === 'new' ? 'Close task' : 'Reopen task'}
        </button>
        <button
          type="button"
          className="inline-flex min-h-9 items-center gap-1.5 rounded-md bg-primary px-2.5 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-45"
          disabled={!task.findFieldAvailable}
          onClick={onFind}
          title={!task.findFieldAvailable ? 'The linked field is unavailable.' : undefined}
        >
          <MapPin className="size-3.5" aria-hidden="true" />
          Find Field
        </button>
      </div>
    </article>
  );
}

function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <nav className="flex items-center justify-between border-t border-border/60 pt-3" aria-label="Discovery pages">
      <button
        type="button"
        className="rounded-md border border-border px-3 py-1.5 text-xs disabled:opacity-40"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>
      <span className="text-xs text-muted-foreground">Page {page} of {totalPages}</span>
      <button
        type="button"
        className="rounded-md border border-border px-3 py-1.5 text-xs disabled:opacity-40"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}

interface DiscoveryBrowserProps {
  target: 'monitoring' | 'scouting';
  seasonId: string | null;
  className?: string;
}

export function DiscoveryBrowser({ target, seasonId, className }: DiscoveryBrowserProps) {
  const { filters, update } = useDiscoveryUrlState(
    target,
    seasonId,
    target === 'scouting' ? 'new' : undefined,
  );
  const [search, setSearch] = useState(filters?.q ?? '');
  const [filterOpen, setFilterOpen] = useState(false);
  const [stagedCrops, setStagedCrops] = useState<number[]>([]);
  const [stagedGroups, setStagedGroups] = useState<string[]>([]);
  const [stagedUngrouped, setStagedUngrouped] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => seasonId ? readPins(seasonId) : []);
  const view = useMapView();
  const navigate = useNavigate();
  const facetsQ = useFieldDiscoveryFacets(seasonId, target, filters?.status);
  const requestFilters = filters ? { ...filters, pinnedFieldIds: pinnedIds } : null;
  const fieldsQ = useFieldDiscovery(target === 'monitoring' ? requestFilters : null);
  const tasksQ = useScoutTaskDiscovery(target === 'scouting' ? requestFilters : null);
  const page = target === 'monitoring' ? fieldsQ.data : tasksQ.data;
  const query = target === 'monitoring' ? fieldsQ : tasksQ;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if ((filters?.q ?? '') !== search.trim()) update({ q: search.trim() });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [filters?.q, search, update]);

  useEffect(() => {
    if (!page || !filters || query.isFetching) return;
    const applied = page.appliedFilters;
    const stale =
      applied.cropIds.join(',') !== (filters.cropIds ?? []).join(',')
      || applied.groupIds.join(',') !== (filters.groupIds ?? []).join(',')
      || applied.includeUngrouped !== Boolean(filters.includeUngrouped);
    if (stale) {
      update({
        cropIds: applied.cropIds,
        groupIds: applied.groupIds,
        includeUngrouped: applied.includeUngrouped,
      });
    } else if ((filters.page ?? 1) > Math.max(1, page.totalPages)) {
      update({ page: Math.max(1, page.totalPages) }, { keepPage: true });
    }
  }, [filters, page, query.isFetching, update]);

  function openFilters() {
    setStagedCrops(filters?.cropIds ?? []);
    setStagedGroups(filters?.groupIds ?? []);
    setStagedUngrouped(Boolean(filters?.includeUngrouped));
    setFilterOpen(true);
  }

  function togglePin(fieldId: string) {
    if (!seasonId) return;
    const next = pinnedIds.includes(fieldId)
      ? pinnedIds.filter((id) => id !== fieldId)
      : [...pinnedIds, fieldId].slice(0, 50);
    setPinnedIds(next);
    writePins(seasonId, next);
  }

  function findField(field: DiscoveryFieldSummary) {
    view.setSelectedPlotId(field.id);
    view.setFocusNonce(view.focusNonce + 1);
    setAnnouncement(`Map centered on ${field.name}.`);
  }

  const appliedCount =
    (filters?.cropIds?.length ?? 0)
    + (filters?.groupIds?.length ?? 0)
    + (filters?.includeUngrouped ? 1 : 0);
  const cropNames = useMemo(
    () => new Map(facetsQ.data?.crops.map((item) => [item.id, item.name]) ?? []),
    [facetsQ.data],
  );
  const groupNames = useMemo(
    () => new Map(facetsQ.data?.groups.map((item) => [item.id, item.name]) ?? []),
    [facetsQ.data],
  );
  const normalizedSavedFilters = Boolean(
    page
    && filters
    && (
      page.appliedFilters.cropIds.join(',') !== (filters.cropIds ?? []).join(',')
      || page.appliedFilters.groupIds.join(',') !== (filters.groupIds ?? []).join(',')
      || page.appliedFilters.includeUngrouped !== Boolean(filters.includeUngrouped)
    ),
  );
  const liveMessage = announcement
    || (normalizedSavedFilters
      ? 'Unavailable saved filters were removed.'
      : page
        ? `${page.total} result${page.total === 1 ? '' : 's'} loaded.`
        : '');

  return (
    <section className={cn('flex min-h-0 flex-1 flex-col', className)} aria-label={`${target} discovery`}>
      <div className="space-y-2 border-b border-border/60 px-4 py-3">
        {target === 'scouting' && (
          <div className="flex gap-2" aria-label="Task status">
            {(['new', 'closed'] as const).map((status) => (
              <button
                key={status}
                type="button"
                className={cn(
                  'rounded-pill px-3 py-1 text-xs capitalize',
                  filters?.status === status ? 'bg-primary text-primary-foreground' : 'border border-border',
                )}
                onClick={() => update({ status })}
              >
                {status}
              </button>
            ))}
          </div>
        )}
        <label className="relative block">
          <span className="sr-only">Search field names</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                update({ q: search.trim() });
              }
            }}
            placeholder="Search field names"
            className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-8 text-sm"
          />
          {search && (
            <button
              type="button"
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2"
              onClick={() => { setSearch(''); update({ q: '' }); }}
            >
              <X className="size-4" />
            </button>
          )}
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-xs"
            onClick={openFilters}
          >
            <Filter className="size-3.5" />
            Filter{appliedCount ? `(${appliedCount})` : ''}
          </button>
          <label className="min-w-0 flex-1">
            <span className="sr-only">Sort results</span>
            <select
              value={filters?.sort ?? 'name_asc'}
              onChange={(event) => update({ sort: event.target.value as DiscoverySort })}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-xs"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        {appliedCount > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Applied filters">
            {(filters?.cropIds ?? []).map((id) => (
              <button
                type="button"
                key={`crop-${id}`}
                className="rounded-pill bg-muted px-2 py-1 text-[11px]"
                onClick={() => update({ cropIds: filters?.cropIds?.filter((value) => value !== id) })}
              >
                {cropNames.get(id) ?? `Crop ${id}`} ×
              </button>
            ))}
            {(filters?.groupIds ?? []).map((id) => (
              <button
                type="button"
                key={`group-${id}`}
                className="rounded-pill bg-muted px-2 py-1 text-[11px]"
                onClick={() => update({ groupIds: filters?.groupIds?.filter((value) => value !== id) })}
              >
                {groupNames.get(id) ?? 'Group'} ×
              </button>
            ))}
            {filters?.includeUngrouped && (
              <button
                type="button"
                className="rounded-pill bg-muted px-2 py-1 text-[11px]"
                onClick={() => update({ includeUngrouped: false })}
              >
                Without group ×
              </button>
            )}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        {query.isLoading && !page ? (
          <div className="space-y-2">{[0, 1, 2].map((id) => <Skeleton key={id} className="h-28 rounded-lg" />)}</div>
        ) : query.error ? (
          <div className="rounded-lg border border-destructive/30 p-4 text-sm text-destructive">
            Could not load results.
            <button type="button" className="ml-2 underline" onClick={() => void query.refetch()}>Retry</button>
          </div>
        ) : !page?.items.length && !page?.pinnedItems.length ? (
          <div className="rounded-lg border border-dashed border-border p-6 text-center">
            <p className="text-sm font-medium">{filters?.q || appliedCount ? 'No matching results' : 'Nothing here yet'}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {filters?.q || appliedCount ? 'Try changing the search or filters.' : 'Add a field or scouting task to get started.'}
            </p>
          </div>
        ) : (
          <div className={cn('space-y-4', query.isFetching && 'opacity-70')} aria-busy={query.isFetching}>
            {!!page?.pinnedItems.length && (
              <section aria-label="Pinned fields">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pinned</h3>
                <div className="space-y-2">
                  {page.pinnedItems.map((field) => (
                    <FieldCard
                      key={`pinned-${field.id}`}
                      field={field}
                      pinned
                      selected={view.selectedPlotId === field.id}
                      onPin={() => togglePin(field.id)}
                      onFind={() => findField(field)}
                      onOpen={() => {
                        view.setSelectedPlotId(field.id);
                        view.setGlobalViewOpen(false);
                        view.setOverlaysVisible(true);
                        navigate(`/monitoring/field-analytics/field/${field.id}`);
                      }}
                    />
                  ))}
                </div>
              </section>
            )}
            <section aria-label="Results">
              {!!page?.pinnedItems.length && <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">All results</h3>}
              <div className="space-y-2">
                {target === 'monitoring'
                  ? fieldsQ.data?.items.map((field) => (
                      <FieldCard
                        key={field.id}
                        field={field}
                        pinned={pinnedIds.includes(field.id)}
                        selected={view.selectedPlotId === field.id}
                        onPin={() => togglePin(field.id)}
                        onFind={() => findField(field)}
                        onOpen={() => {
                          view.setSelectedPlotId(field.id);
                          view.setGlobalViewOpen(false);
                          view.setOverlaysVisible(true);
                          navigate(`/monitoring/field-analytics/field/${field.id}`);
                        }}
                      />
                    ))
                  : tasksQ.data?.items.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        selected={Boolean(task.field && view.selectedPlotId === task.field.id)}
                        onFind={() => task.field && findField(task.field)}
                      />
                    ))}
              </div>
            </section>
            <Pagination
              page={page?.page ?? 1}
              totalPages={page?.totalPages ?? 0}
              onPage={(nextPage) => update({ page: nextPage }, { keepPage: true })}
            />
          </div>
        )}
      </div>

      <p className="sr-only" aria-live="polite">{liveMessage}</p>

      <SheetRoot
        open={filterOpen}
        onOpenChange={(open) => {
          setFilterOpen(open);
          if (open) openFilters();
        }}
      >
        <SheetContent side="right" aria-label={`${target} filters`}>
          <SheetHeader>
            <SheetTitle>Filter discovery</SheetTitle>
            <SheetDescription>Changes apply only when you choose Apply.</SheetDescription>
          </SheetHeader>
          <div className="h-[calc(100%-8.5rem)] overflow-auto px-4 py-4">
            {facetsQ.error ? (
              <p className="text-sm text-destructive">Filter options could not be loaded.</p>
            ) : (
              <div className="space-y-5">
                <fieldset>
                  <legend className="mb-2 text-sm font-semibold">Crop</legend>
                  <div className="space-y-2">
                    {facetsQ.data?.crops.map((crop) => (
                      <label key={crop.id} className="flex min-h-9 items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={stagedCrops.includes(crop.id)}
                          onChange={() => setStagedCrops((current) =>
                            current.includes(crop.id)
                              ? current.filter((id) => id !== crop.id)
                              : [...current, crop.id])}
                        />
                        {crop.name}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset>
                  <legend className="mb-2 text-sm font-semibold">Group</legend>
                  <div className="space-y-2">
                    {facetsQ.data?.groups.map((group) => (
                      <label key={group.id} className="flex min-h-9 items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={stagedGroups.includes(group.id)}
                          onChange={() => setStagedGroups((current) =>
                            current.includes(group.id)
                              ? current.filter((id) => id !== group.id)
                              : [...current, group.id])}
                        />
                        {group.name}
                      </label>
                    ))}
                    {facetsQ.data?.hasUngrouped && (
                      <label className="flex min-h-9 items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={stagedUngrouped}
                          onChange={(event) => setStagedUngrouped(event.target.checked)}
                        />
                        Without group
                      </label>
                    )}
                  </div>
                </fieldset>
              </div>
            )}
          </div>
          <SheetFooter>
            <button type="button" className="rounded-md border border-border px-4 py-2 text-sm" onClick={() => setFilterOpen(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => {
                update({
                  cropIds: stagedCrops,
                  groupIds: stagedGroups,
                  includeUngrouped: stagedUngrouped,
                });
                setFilterOpen(false);
              }}
            >
              Apply
            </button>
          </SheetFooter>
        </SheetContent>
      </SheetRoot>
    </section>
  );
}
