import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Layers,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sprout,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { Plot } from '@/types/api';

type BadgeTone = 'neutral' | 'success' | 'warning' | 'destructive' | 'info' | 'outline';

interface BadgeCopy {
  label: string;
  variant: BadgeTone;
}

export interface AllFieldsPanelProps {
  plots?: Plot[];
  isLoading?: boolean;
  error?: Error | string | null;
  onRetry?: () => void;
  selectedPlotId?: string | null;
  onSelect?: (plot: Plot) => void;
  onEdit?: (plot: Plot) => void;
  onDelete?: (plot: Plot) => void;
  onAdd?: () => void;
  onImport?: () => void;
  className?: string;
}

const STATUS_COPY: Record<NonNullable<Plot['status']>, BadgeCopy> = {
  planned: { label: 'Planned', variant: 'info' },
  active: { label: 'Active', variant: 'success' },
  inactive: { label: 'Inactive', variant: 'neutral' },
  archived: { label: 'Archived', variant: 'outline' },
};

const AREA_FORMATTER = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

function formatArea(areaHa: number | null): string {
  if (areaHa == null || !Number.isFinite(areaHa)) return 'Area unavailable';
  return `${AREA_FORMATTER.format(areaHa)} ha`;
}

function fieldSubtitle(plot: Plot): string {
  const parts = [plot.groupName, plot.cropType, plot.variety, plot.seasonLabel].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : 'No crop metadata';
}

function searchableText(plot: Plot): string {
  return [
    plot.name,
    plot.groupName,
    plot.cropType,
    plot.variety,
    plot.seasonLabel,
    plot.status,
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase();
}

function errorMessage(error: Error | string | null | undefined): string {
  if (!error) return 'Unable to load fields.';
  if (typeof error === 'string') return error;
  return error.message || 'Unable to load fields.';
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-2" data-testid="all-fields-loading">
      {[0, 1, 2].map((row) => (
        <div key={ row } className="rounded-lg border border-border/70 bg-card/35 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-7 w-20" />
          </div>
          <Skeleton className="mb-2 h-3 w-52" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16 rounded-pill" />
            <Skeleton className="h-5 w-20 rounded-pill" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  query,
  onAdd,
  onImport,
  onClearSearch,
}: {
  query: string;
  onAdd?: () => void;
  onImport?: () => void;
  onClearSearch: () => void;
}) {
  const hasQuery = query.length > 0;

  return (
    <div
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border/80 bg-card/35 px-4 py-8 text-center"
      data-testid={ hasQuery ? 'all-fields-no-results' : 'all-fields-empty' }
    >
      <div className="flex size-11 items-center justify-center rounded-pill bg-primary/10 text-primary">
        { hasQuery ? <Search className="size-5" strokeWidth={ 1.75 } /> : <Sprout className="size-5" strokeWidth={ 1.75 } /> }
      </div>
      <div>
        <h3 className="font-display text-[15px] font-semibold tracking-[-0.01em] text-foreground">
          { hasQuery ? 'No fields match your search' : 'No fields yet' }
        </h3>
        <p className="mt-1 max-w-[28ch] text-[13px] leading-5 text-muted-foreground">
          { hasQuery
            ? 'Try another name, crop, season, group, or status.'
            : 'Add a field boundary or import field GeoJSON to begin monitoring.' }
        </p>
      </div>
      { hasQuery ? (
        <Button type="button" variant="outline" size="sm" onClick={ onClearSearch }>
          <X className="size-4" strokeWidth={ 1.75 } /> Clear search
        </Button>
      ) : (
        <div className="flex flex-wrap justify-center gap-2">
          <Button type="button" size="sm" onClick={ onAdd } disabled={ !onAdd }>
            <Plus className="size-4" strokeWidth={ 1.75 } /> Add field
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={ onImport } disabled={ !onImport }>
            <Upload className="size-4" strokeWidth={ 1.75 } /> Import
          </Button>
        </div>
      ) }
    </div>
  );
}

function FieldCard({
  plot,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: {
  plot: Plot;
  selected: boolean;
  onSelect?: (plot: Plot) => void;
  onEdit?: (plot: Plot) => void;
  onDelete?: (plot: Plot) => void;
}) {
  const status = plot.status ? STATUS_COPY[plot.status] : null;

  return (
    <article
      className={ cn(
        'rounded-lg border transition-[background-color,border-color,box-shadow] duration-fast ease-standard',
        selected
          ? 'border-primary/55 bg-primary/[0.08] shadow-e1'
          : 'border-border/70 bg-card/40 hover:border-border hover:bg-accent/40',
      ) }
      data-selected={ selected }
      data-testid={ `field-card-${plot.id}` }
    >
      <div className="flex items-start gap-2 p-3">
        <button
          type="button"
          className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-pressed={ selected }
          onClick={ () => onSelect?.(plot) }
          data-testid={ `field-card-select-${plot.id}` }
        >
          <span className="flex min-w-0 items-start gap-2">
            <span
              aria-hidden="true"
              className={ cn(
                'mt-1.5 flex size-3.5 shrink-0 items-center justify-center rounded-pill border',
                selected ? 'border-primary' : 'border-muted-foreground/50',
              ) }
            >
              { selected && <span className="size-1.5 rounded-pill bg-primary" /> }
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-display text-[14px] font-semibold tracking-[-0.01em] text-foreground">
                { plot.name }
              </span>
              <span className="mt-1 block truncate text-[12px] text-muted-foreground">
                { fieldSubtitle(plot) }
              </span>
            </span>
          </span>
        </button>

        <div className="flex shrink-0 flex-col items-end gap-2">
          <span className="rounded-md bg-background/45 px-2 py-1 font-mono text-[12px] leading-none text-foreground tnum">
            { formatArea(plot.areaHa) }
          </span>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={ (e) => {
                e.stopPropagation();
                onEdit?.(plot);
              } }
              disabled={ !onEdit }
              aria-label={ `Edit field ${plot.name}` }
              data-testid={ `field-card-edit-${plot.id}` }
              className="size-7"
            >
              <Pencil className="size-3.5" strokeWidth={ 1.75 } />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={ (e) => {
                e.stopPropagation();
                onDelete?.(plot);
              } }
              disabled={ !onDelete }
              aria-label={ `Delete field ${plot.name}` }
              data-testid={ `field-card-delete-${plot.id}` }
              className="size-7 text-destructive hover:text-destructive"
            >
              <Trash2 className="size-3.5" strokeWidth={ 1.75 } />
            </Button>
          </div>
        </div>
      </div>

      { status && (
        <div className="flex flex-wrap gap-1.5 border-t border-border/60 px-3 py-2">
          <Badge variant={ status.variant }>{ status.label }</Badge>
        </div>
      ) }
    </article>
  );
}

export function AllFieldsPanel({
  plots,
  isLoading = false,
  error = null,
  onRetry,
  selectedPlotId = null,
  onSelect,
  onEdit,
  onDelete,
  onAdd,
  onImport,
  className,
}: AllFieldsPanelProps) {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const fields = useMemo(() => plots ?? [], [plots]);
  const filteredFields = useMemo(() => {
    if (!normalizedQuery) return fields;
    return fields.filter((plot) => searchableText(plot).includes(normalizedQuery));
  }, [fields, normalizedQuery]);

  const selectedField = selectedPlotId
    ? fields.find((plot) => plot.id === selectedPlotId) ?? null
    : null;

  const body = (() => {
    if (isLoading) return <LoadingState />;

    if (error) {
      return (
        <div
          className="flex flex-col items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3"
          data-testid="all-fields-error"
        >
          <div className="flex items-start gap-2 text-[13px] text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" strokeWidth={ 1.75 } />
            <div>
              <p className="font-medium">Fields unavailable</p>
              <p className="mt-0.5 leading-5 text-destructive/90">{ errorMessage(error) }</p>
            </div>
          </div>
          { onRetry && (
            <Button type="button" variant="outline" size="sm" onClick={ onRetry } data-testid="all-fields-retry">
              <RefreshCw className="size-4" strokeWidth={ 1.75 } /> Retry
            </Button>
          ) }
        </div>
      );
    }

    if (fields.length === 0 || filteredFields.length === 0) {
      return (
        <EmptyState
          query={ normalizedQuery }
          onAdd={ onAdd }
          onImport={ onImport }
          onClearSearch={ () => setQuery('') }
        />
      );
    }

    return (
      <ScrollArea className="max-h-[min(30rem,calc(100vh-18rem))] pr-2" data-testid="all-fields-list">
        <div className="flex flex-col gap-2">
          { filteredFields.map((plot) => (
            <FieldCard
              key={ plot.id }
              plot={ plot }
              selected={ plot.id === selectedPlotId }
              onSelect={ onSelect }
              onEdit={ onEdit }
              onDelete={ onDelete }
            />
          )) }
        </div>
      </ScrollArea>
    );
  })();

  return (
    <section
      className={ cn('glass flex w-[360px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden animate-panel-in', className) }
      aria-label="All fields"
      data-testid="all-fields-panel"
    >
      <header className="contour px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Layers className="size-4 text-primary" strokeWidth={ 1.75 } />
              <h2 className="font-display text-base font-semibold tracking-[-0.01em]">All fields</h2>
            </div>
            <p className="mt-1 truncate text-[12px] text-muted-foreground">
              { selectedField ? `Selected: ${selectedField.name}` : `${fields.length} field${fields.length === 1 ? '' : 's'}` }
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={ onImport }
              disabled={ !onImport }
              aria-label="Import field GeoJSON"
              data-testid="all-fields-import"
            >
              <Upload className="size-4" strokeWidth={ 1.75 } />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              onClick={ onAdd }
              disabled={ !onAdd }
              aria-label="Add field"
              data-testid="all-fields-add"
            >
              <Plus className="size-4" strokeWidth={ 1.75 } />
            </Button>
          </div>
        </div>
      </header>

      <Separator />

      <div className="flex flex-col gap-3 p-4">
        <label className="relative block" htmlFor="all-fields-search">
          <span className="sr-only">Search fields</span>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            strokeWidth={ 1.75 }
          />
          <input
            id="all-fields-search"
            type="search"
            value={ query }
            onChange={ (event) => setQuery(event.target.value) }
            placeholder="Search fields, crops, seasons…"
            disabled={ isLoading || Boolean(error) }
            className="h-9 w-full rounded-md border border-input bg-background/55 pl-9 pr-3 text-[13px] text-foreground shadow-e1 transition-colors duration-fast placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="all-fields-search"
          />
        </label>

        { body }
      </div>
    </section>
  );
}
