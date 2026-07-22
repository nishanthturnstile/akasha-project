import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock,
  RefreshCw,
  Search,
  XCircle,
} from 'lucide-react';
import AdminIngestionRunPanel from '@/components/admin/ingestion/AdminIngestionRunPanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useConfig, useIngestionSchedules } from '@/lib/queries';
import type { IngestionScheduleItem } from '@/types/api';

type BadgeVariant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral' | 'outline';
type DueFilter = '' | 'due' | 'overdue' | 'current';

interface Filters {
  sourceId: string;
  provider: string;
  scheduleState: string;
  productExposure: string;
  dueState: DueFilter;
  validationState: string;
}

interface DueStatus {
  key: 'overdue' | 'due' | 'current' | 'unknown';
  label: string;
  variant: BadgeVariant;
}

interface RunTarget {
  sourceId: string;
  aoiId?: string | null;
}

const EMPTY_FILTERS: Filters = {
  sourceId: '',
  provider: '',
  scheduleState: '',
  productExposure: '',
  dueState: '',
  validationState: '',
};
const EMPTY_SCHEDULES: IngestionScheduleItem[] = [];

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = value.slice(0, 10);
  const time = value.length >= 16 ? value.slice(11, 16) : '';
  return time ? `${date} ${time}` : date;
}

function fmtCadence(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)} d`;
}

function normalized(value: string | null | undefined): string {
  return value?.trim().toLowerCase() ?? '';
}

function displayValue(value: string | null | undefined): string {
  return value?.trim() || '—';
}

function uniqueOptions(
  schedules: IngestionScheduleItem[],
  read: (schedule: IngestionScheduleItem) => string | null | undefined,
): string[] {
  return Array.from(
    new Set(
      schedules
        .map((schedule) => read(schedule)?.trim())
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort((a, b) => a.localeCompare(b));
}

function fallbackDueStatus(
  schedule: IngestionScheduleItem,
  generatedAt: string | null | undefined,
): DueStatus {
  if (!schedule.nextDueAt) {
    return { key: 'unknown', label: 'Not scheduled', variant: 'neutral' };
  }

  const dueAt = Date.parse(schedule.nextDueAt);
  const basis = generatedAt ? Date.parse(generatedAt) : Date.now();
  if (!Number.isFinite(dueAt) || !Number.isFinite(basis)) {
    return { key: 'unknown', label: 'Unknown', variant: 'neutral' };
  }

  if (dueAt < basis - 24 * 60 * 60 * 1000) {
    return { key: 'overdue', label: 'Overdue', variant: 'destructive' };
  }
  if (dueAt <= basis) {
    return { key: 'due', label: 'Due', variant: 'warning' };
  }
  return { key: 'current', label: 'Current', variant: 'success' };
}

function dueStatus(schedule: IngestionScheduleItem, generatedAt: string | null | undefined): DueStatus {
  if (schedule.isOverdue === true) {
    return { key: 'overdue', label: 'Overdue', variant: 'destructive' };
  }
  if (schedule.isDue === true) {
    return { key: 'due', label: 'Due', variant: 'warning' };
  }
  if (schedule.isDue === false) {
    return { key: 'current', label: 'Current', variant: 'success' };
  }
  if (schedule.isOverdue === false) {
    const fallback = fallbackDueStatus(schedule, generatedAt);
    return fallback.key === 'overdue'
      ? { key: 'current', label: 'Current', variant: 'success' }
      : fallback;
  }
  return fallbackDueStatus(schedule, generatedAt);
}

function stateVariant(value: string | null | undefined): BadgeVariant {
  const s = normalized(value);
  if (s === 'active' || s === 'enabled' || s === 'validated' || s === 'public') return 'success';
  if (s === 'planned' || s === 'trial' || s === 'internal' || s === 'limited') return 'info';
  if (s === 'gated' || s === 'paused' || s === 'disabled' || s === 'deferred') return 'warning';
  if (s === 'failed' || s === 'validation_failed' || s === 'invalid' || s === 'blocked') {
    return 'destructive';
  }
  return value ? 'outline' : 'neutral';
}

function DueStatusBadge({ status }: { status: DueStatus }) {
  const Icon =
    status.key === 'overdue'
      ? XCircle
      : status.key === 'due'
        ? Clock
        : status.key === 'current'
          ? CheckCircle2
          : AlertTriangle;

  return (
    <Badge variant={ status.variant } className="inline-flex items-center gap-1">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      { status.label }
    </Badge>
  );
}

function StateBadge({ value }: { value: string | null | undefined }) {
  return (
    <Badge variant={ stateVariant(value) }>
      { displayValue(value) }
    </Badge>
  );
}

function nextWindow(schedule: IngestionScheduleItem): string {
  const start = fmtDateTime(schedule.nextWindowStart);
  const end = fmtDateTime(schedule.nextWindowEnd);
  if (start === '—' && end === '—') return '—';
  if (end === '—' || end === start) return start;
  return `${start} → ${end}`;
}

function scheduleMatchesFilters(
  schedule: IngestionScheduleItem,
  filters: Filters,
  status: DueStatus,
): boolean {
  const sourceMatch =
    !filters.sourceId || normalized(schedule.sourceId).includes(normalized(filters.sourceId));
  const providerMatch = !filters.provider || schedule.provider === filters.provider;
  const scheduleMatch =
    !filters.scheduleState || schedule.scheduleState === filters.scheduleState;
  const exposureMatch =
    !filters.productExposure || schedule.productExposure === filters.productExposure;
  const dueMatch =
    !filters.dueState
    || (filters.dueState === 'current'
      ? status.key === 'current' || status.key === 'unknown'
      : status.key === filters.dueState);
  const validationMatch =
    !filters.validationState || schedule.validationState === filters.validationState;
  return sourceMatch && providerMatch && scheduleMatch && exposureMatch && dueMatch && validationMatch;
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  allLabel: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>{ label }</span>
      <select
        value={ value }
        onChange={ (event) => onChange(event.target.value) }
        className="h-8 rounded-md border border-border bg-background px-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        aria-label={ `Filter by ${label.toLowerCase()}` }
      >
        <option value="">{ allLabel }</option>
        { options.map((option) => (
          <option key={ option } value={ option }>
            { option }
          </option>
        )) }
      </select>
    </label>
  );
}

function FilterBar({
  filters,
  onFiltersChange,
  schedules,
}: {
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  schedules: IngestionScheduleItem[];
}) {
  const providerOptions = useMemo(
    () => uniqueOptions(schedules, (schedule) => schedule.provider),
    [schedules],
  );
  const scheduleOptions = useMemo(
    () => uniqueOptions(schedules, (schedule) => schedule.scheduleState),
    [schedules],
  );
  const exposureOptions = useMemo(
    () => uniqueOptions(schedules, (schedule) => schedule.productExposure),
    [schedules],
  );
  const validationOptions = useMemo(
    () => uniqueOptions(schedules, (schedule) => schedule.validationState),
    [schedules],
  );

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">Filter by source ID</span>
        <input
          type="text"
          value={ filters.sourceId }
          onChange={ (event) => setFilter('sourceId', event.target.value) }
          placeholder="Source ID…"
          className="h-8 rounded-md border border-border bg-background px-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filter by source ID"
        />
      </label>
      <FilterSelect
        label="Provider"
        value={ filters.provider }
        onChange={ (value) => setFilter('provider', value) }
        options={ providerOptions }
        allLabel="All providers"
      />
      <FilterSelect
        label="Schedule"
        value={ filters.scheduleState }
        onChange={ (value) => setFilter('scheduleState', value) }
        options={ scheduleOptions }
        allLabel="All states"
      />
      <FilterSelect
        label="Exposure"
        value={ filters.productExposure }
        onChange={ (value) => setFilter('productExposure', value) }
        options={ exposureOptions }
        allLabel="All exposure"
      />
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Due</span>
        <select
          value={ filters.dueState }
          onChange={ (event) => setFilter('dueState', event.target.value as DueFilter) }
          className="h-8 rounded-md border border-border bg-background px-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filter by due or overdue status"
        >
          <option value="">All due states</option>
          <option value="due">Due</option>
          <option value="overdue">Overdue</option>
          <option value="current">Current / unscheduled</option>
        </select>
      </label>
      <FilterSelect
        label="Validation"
        value={ filters.validationState }
        onChange={ (value) => setFilter('validationState', value) }
        options={ validationOptions }
        allLabel="All validation"
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={ () => onFiltersChange(EMPTY_FILTERS) }
      >
        Clear
      </Button>
    </div>
  );
}

function ScheduleRow({
  schedule,
  generatedAt,
  onRunSource,
}: {
  schedule: IngestionScheduleItem;
  generatedAt: string | null | undefined;
  onRunSource: (target: RunTarget) => void;
}) {
  const status = dueStatus(schedule, generatedAt);
  return (
    <tr className="border-t border-border/60 align-top hover:bg-accent/40 transition-colors">
      <td className="py-3 pr-4">
        <div className="font-mono text-xs font-medium text-info">{ schedule.sourceId }</div>
        { schedule.adapter && schedule.adapter !== schedule.provider && (
          <div className="mt-1 text-[11px] text-muted-foreground">adapter { schedule.adapter }</div>
        ) }
      </td>
      <td className="py-3 pr-4 text-sm text-muted-foreground">{ displayValue(schedule.provider) }</td>
      <td className="py-3 pr-4 text-sm text-muted-foreground">{ displayValue(schedule.aoiId) }</td>
      <td className="py-3 pr-4"><StateBadge value={ schedule.lifecycleState } /></td>
      <td className="py-3 pr-4">
        <StateBadge value={ schedule.scheduleState } />
        <div className="mt-1 text-[11px] text-muted-foreground">
          { schedule.scheduleEnabled ? 'enabled' : 'not enabled' }
        </div>
      </td>
      <td className="py-3 pr-4"><StateBadge value={ schedule.productExposure } /></td>
      <td className="py-3 pr-4"><StateBadge value={ schedule.validationState } /></td>
      <td className="py-3 pr-4 text-xs text-muted-foreground whitespace-nowrap">
        { fmtDateTime(schedule.lastRunAt) }
      </td>
      <td className="py-3 pr-4 text-xs text-success whitespace-nowrap">
        { fmtDateTime(schedule.lastSuccessAt) }
      </td>
      <td className="py-3 pr-4 text-xs text-destructive whitespace-nowrap">
        { fmtDateTime(schedule.lastFailureAt) }
      </td>
      <td className="py-3 pr-4 text-xs text-muted-foreground whitespace-nowrap">
        { fmtDateTime(schedule.nextDueAt) }
      </td>
      <td className="py-3 pr-4 text-xs text-muted-foreground whitespace-nowrap">
        { nextWindow(schedule) }
      </td>
      <td className="py-3 pr-4 text-xs text-muted-foreground">{ fmtCadence(schedule.cadenceDays) }</td>
      <td className="py-3 pr-4 text-xs text-muted-foreground">
        <span className="line-clamp-2 max-w-55">
          { displayValue(schedule.dueReason) }
        </span>
      </td>
      <td className="py-3 pr-4"><DueStatusBadge status={ status } /></td>
      <td className="py-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={ () => onRunSource({ sourceId: schedule.sourceId, aoiId: schedule.aoiId }) }
          aria-label={ `Run this source ${schedule.sourceId}` }
        >
          Run this source
        </Button>
      </td>
    </tr>
  );
}

export default function IngestionSchedules() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [runTarget, setRunTarget] = useState<RunTarget | null>(null);
  const configQ = useConfig();
  const schedulesQ = useIngestionSchedules();
  const schedules = schedulesQ.data?.schedules ?? EMPTY_SCHEDULES;
  const generatedAt = schedulesQ.data?.generatedAt;
  const runPanelKey = `${runTarget?.sourceId ?? 'default'}:${runTarget?.aoiId ?? ''}:${schedules
    .map((schedule) => `${schedule.sourceId}:${schedule.aoiId ?? ''}`)
    .join('|')}`;
  const decoratedSchedules = useMemo(
    () => schedules.map((schedule) => ({ schedule, status: dueStatus(schedule, generatedAt) })),
    [schedules, generatedAt],
  );
  const filteredSchedules = useMemo(
    () =>
      decoratedSchedules
        .filter(({ schedule, status }) => scheduleMatchesFilters(schedule, filters, status))
        .map(({ schedule }) => schedule),
    [decoratedSchedules, filters],
  );
  const dueCount = decoratedSchedules.filter(({ status }) => status.key === 'due').length;
  const overdueCount = decoratedSchedules.filter(({ status }) => status.key === 'overdue').length;
  const isUnconfigured = schedulesQ.data?.status === 'unconfigured';
  const isUnavailable = schedulesQ.data?.status === 'unavailable';
  const hasRetainedSchedules = schedules.length > 0;
  const shouldRenderSchedules =
    !schedulesQ.isLoading
    && !isUnconfigured
    && (!schedulesQ.error || hasRetainedSchedules)
    && (!isUnavailable || hasRetainedSchedules);

  return (
    <main
      className="h-full overflow-auto bg-background p-4 text-foreground"
      data-testid="ingestion-schedules-page"
    >
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
              Admin · Internal operations
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Ingestion schedules</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Source and AOI cadence, exposure, validation, and due state for the read-only
              scheduler console.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={ overdueCount > 0 ? 'destructive' : 'neutral' }>
              { overdueCount } overdue
            </Badge>
            <Badge variant={ dueCount > 0 ? 'warning' : 'neutral' }>
              { dueCount } due
            </Badge>
            <Button
              variant="outline"
              size="sm"
              disabled={ schedulesQ.isFetching }
              onClick={ () => void schedulesQ.refetch() }
              aria-label="Refresh schedules"
            >
              <RefreshCw
                className={ `h-3.5 w-3.5 ${schedulesQ.isFetching ? 'animate-spin' : ''}` }
                aria-hidden="true"
              />
              Refresh
            </Button>
          </div>
        </div>
        <div className="mt-3 border-t border-border/60 pt-3">
          <FilterBar filters={ filters } onFiltersChange={ setFilters } schedules={ schedules } />
        </div>
      </section>

      <div className="mt-4">
        <AdminIngestionRunPanel
          key={ runPanelKey }
          schedules={ schedules }
          prefill={ runTarget }
          liveTriggerEnabled={ configQ.data?.adminIngestionLiveTriggerEnabled === true }
        />
      </div>

      { schedulesQ.error && (
        <p
          className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
          role="alert"
        >
          Failed to load ingestion schedules. { (schedulesQ.error as Error).message ?? '' }
        </p>
      ) }

      { schedulesQ.data?.lastError && (
        <p
          className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning"
          role="status"
        >
          Scheduler schedules are available with a warning: { schedulesQ.data.lastError }
        </p>
      ) }

      { isUnconfigured && (
        <p className="mt-4 rounded-md border border-border/60 bg-muted/30 p-4 text-sm text-muted-foreground">
          The ingestion scheduler is not configured for this environment yet. No cadence rows are
          expected until scheduler artifacts are present.
        </p>
      ) }

      { isUnavailable && (
        <p className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-4 text-sm text-warning">
          Ingestion schedules are temporarily unavailable. Refresh after the scheduler ledger is
          reachable.
        </p>
      ) }

      { schedulesQ.isLoading && (
        <div
          className="glass scan-sweep mt-4 h-32 rounded-xl"
          aria-busy="true"
          aria-label="Loading schedules"
        />
      ) }

      { shouldRenderSchedules && (
        <section className="mt-4 rounded-xl border border-border/80 bg-card/90">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              Source/AOI cadence
              { schedules.length > 0 && (
                <span className="text-sm font-normal text-muted-foreground">
                  ({ filteredSchedules.length } of { schedules.length })
                </span>
              ) }
            </h2>
            { generatedAt && (
              <span className="text-xs text-muted-foreground">
                Generated { fmtDateTime(generatedAt) }
              </span>
            ) }
          </div>
          <ScrollArea className="h-[calc(100vh-300px)] min-h-90">
            <div className="px-4 pb-4">
              { schedules.length === 0 ? (
                <p className="mt-4 rounded-md border border-border/60 p-4 text-center text-sm text-muted-foreground">
                  No ingestion schedules are currently reported by the scheduler.
                </p>
              ) : filteredSchedules.length === 0 ? (
                <p className="mt-4 rounded-md border border-border/60 p-4 text-center text-sm text-muted-foreground">
                  No schedules match the current filters.
                </p>
              ) : (
                <table className="mt-3 min-w-375 w-full text-left text-sm">
                  <thead className="sticky top-0 bg-card/95 text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    <tr>
                      <th className="py-2 pr-4">Source ID</th>
                      <th className="py-2 pr-4">Provider</th>
                      <th className="py-2 pr-4">AOI</th>
                      <th className="py-2 pr-4">Lifecycle</th>
                      <th className="py-2 pr-4">Schedule</th>
                      <th className="py-2 pr-4">Exposure</th>
                      <th className="py-2 pr-4">Validation</th>
                      <th className="py-2 pr-4">Last run</th>
                      <th className="py-2 pr-4">Last success</th>
                      <th className="py-2 pr-4">Last failure</th>
                      <th className="py-2 pr-4">Next due</th>
                      <th className="py-2 pr-4">Next window</th>
                      <th className="py-2 pr-4">Cadence</th>
                      <th className="py-2 pr-4">Due reason</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2">Run</th>
                    </tr>
                  </thead>
                  <tbody>
                    { filteredSchedules.map((schedule) => (
                      <ScheduleRow
                        key={ `${schedule.sourceId}:${schedule.aoiId ?? 'global'}` }
                        schedule={ schedule }
                        generatedAt={ generatedAt }
                        onRunSource={ setRunTarget }
                      />
                    )) }
                  </tbody>
                </table>
              ) }
            </div>
          </ScrollArea>
        </section>
      ) }
    </main>
  );
}
