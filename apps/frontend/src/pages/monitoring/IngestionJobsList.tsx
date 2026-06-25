import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Download,
  LockKeyhole,
  Loader2,
  RefreshCw,
  Search,
  XCircle,
} from 'lucide-react';
import { useIngestionJobs } from '@/lib/queries';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { IngestionJobSummary } from '@/types/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.slice(0, 10);
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return `${value.slice(0, 10)} ${value.slice(11, 16)}`;
}

function fmtCount(value: number | null | undefined): string {
  if (value == null) return '—';
  return String(value);
}

type StateBadgeVariant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral';

function stateVariant(state: string): StateBadgeVariant {
  const s = state.toLowerCase();
  if (s === 'succeeded') return 'success';
  if (s === 'running' || s === 'queued') return 'info';
  if (
    s === 'planned'
    || s === 'blocked_by_lock'
    || s === 'skipped_not_due'
    || s === 'skipped_gated'
  ) return 'warning';
  if (s === 'failed' || s === 'validation_failed' || s === 'cancelled') return 'destructive';
  return 'neutral';
}

function StateIcon({ state }: { state: string }) {
  const s = state.toLowerCase();
  if (s === 'succeeded') {
    return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  if (s === 'running') return <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
  if (s === 'planned' || s === 'queued' || s === 'skipped_not_due') {
    return <Clock className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  if (s === 'blocked_by_lock' || s === 'skipped_gated') {
    return <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  if (s === 'failed' || s === 'validation_failed' || s === 'cancelled') {
    return <XCircle className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  return <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function JobRow({ job }: { job: IngestionJobSummary }) {
  const variant = stateVariant(job.state);
  return (
    <tr className="group border-t border-border/60 align-top hover:bg-accent/40 transition-colors">
      <td className="py-3 pr-4">
        <Link
          to={ `/admin/ingestion/jobs/${encodeURIComponent(job.jobId)}` }
          className="inline-flex items-center gap-1.5 font-mono text-xs text-info hover:underline focus-visible:underline outline-none"
          aria-label={ `View job ${job.jobId}` }
        >
          { job.jobId.slice(0, 20) }{ job.jobId.length > 20 ? '…' : '' }
          <ChevronRight className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
        </Link>
      </td>
      <td className="py-3 pr-4 text-sm">
        <div className="font-medium">{ job.sourceId }</div>
        { job.provider && <div className="mt-0.5 text-xs text-muted-foreground">{ job.provider }</div> }
      </td>
      <td className="py-3 pr-4 text-sm text-muted-foreground">{ job.aoiId ?? '—' }</td>
      <td className="py-3 pr-4">
        <Badge variant={ variant } className="inline-flex items-center gap-1">
          <StateIcon state={ job.state } />
          { job.state }
        </Badge>
        { job.failureKind && (
          <div className="mt-1 text-xs text-destructive">{ job.failureKind }</div>
        ) }
      </td>
      <td className="py-3 pr-4 text-xs text-muted-foreground">
        <div>{ fmtDate(job.windowStart) }</div>
        { job.windowEnd && job.windowEnd !== job.windowStart && (
          <div className="text-[11px]">→ { fmtDate(job.windowEnd) }</div>
        ) }
      </td>
      <td className="py-3 pr-4">
        <div className="grid grid-cols-4 gap-x-2 text-center text-xs">
          <span title="Found" className="text-muted-foreground">
            <span className="block font-semibold text-foreground">{ fmtCount(job.foundCount) }</span>
            found
          </span>
          <span title="Selected" className="text-muted-foreground">
            <span className="block font-semibold text-warning">{ fmtCount(job.selectedCount) }</span>
            sel
          </span>
          <span title="Downloaded" className="text-muted-foreground">
            <span className="block font-semibold text-success">{ fmtCount(job.downloadedCount) }</span>
            dl
          </span>
          <span title="Rejected" className="text-muted-foreground">
            <span className="block font-semibold text-destructive">{ fmtCount(job.rejectedCount) }</span>
            rej
          </span>
        </div>
      </td>
      <td className="py-3 pr-4 text-xs text-muted-foreground">
        { job.message
          ? <span className="line-clamp-2 max-w-[220px]">{ job.message }</span>
          : '—' }
      </td>
      <td className="py-3 text-xs text-muted-foreground whitespace-nowrap">
        { fmtDateTime(job.updatedAt ?? job.finishedAt ?? job.startedAt) }
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const STATE_OPTIONS = [
  { value: '', label: 'All states' },
  { value: 'planned', label: 'Planned' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'validation_failed', label: 'Validation failed' },
  { value: 'blocked_by_lock', label: 'Blocked by lock' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'skipped_not_due', label: 'Skipped not due' },
  { value: 'skipped_gated', label: 'Skipped gated' },
];

function FilterBar({
  state,
  onStateChange,
  sourceId,
  onSourceChange,
}: {
  state: string;
  onStateChange: (v: string) => void;
  sourceId: string;
  onSourceChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">Filter by source ID</span>
        <input
          type="text"
          value={ sourceId }
          onChange={ (e) => onSourceChange(e.target.value) }
          placeholder="Source ID…"
          className="h-8 rounded-md border border-border bg-background px-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filter by source ID"
        />
      </label>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>State</span>
        <select
          value={ state }
          onChange={ (e) => onStateChange(e.target.value) }
          className="h-8 rounded-md border border-border bg-background px-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filter by job state"
        >
          { STATE_OPTIONS.map((opt) => (
            <option key={ opt.value } value={ opt.value }>
              { opt.label }
            </option>
          )) }
        </select>
      </label>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IngestionJobsList() {
  const [stateFilter, setStateFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');

  const filters = {
    ...(stateFilter ? { state: stateFilter } : {}),
    ...(sourceFilter ? { sourceId: sourceFilter } : {}),
    limit: 50,
  };

  const jobsQ = useIngestionJobs(filters);
  const jobs = jobsQ.data?.jobs ?? [];

  return (
    <main
      className="h-full overflow-auto bg-background p-4 text-foreground"
      data-testid="ingestion-jobs-list-page"
    >
      {/* Header */}
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
              Operator console · Ingestion scheduler
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Ingestion jobs</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Scheduled and manual ingestion job runs across all imagery sources.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={ jobsQ.isFetching }
              onClick={ () => void jobsQ.refetch() }
              aria-label="Refresh job list"
            >
              <RefreshCw
                className={ `h-3.5 w-3.5 ${jobsQ.isFetching ? 'animate-spin' : ''}` }
                aria-hidden="true"
              />
              Refresh
            </Button>
          </div>
        </div>
        <div className="mt-3 border-t border-border/60 pt-3">
          <FilterBar
            state={ stateFilter }
            onStateChange={ setStateFilter }
            sourceId={ sourceFilter }
            onSourceChange={ setSourceFilter }
          />
        </div>
      </section>

      {/* Error */}
      { jobsQ.error && (
        <p
          className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200"
          role="alert"
        >
          Failed to load ingestion jobs. { (jobsQ.error as Error).message ?? '' }
        </p>
      ) }

      {/* Skeleton */}
      { jobsQ.isLoading && (
        <div className="glass scan-sweep mt-4 h-32 rounded-xl" aria-busy="true" aria-label="Loading jobs" />
      ) }

      {/* Table */}
      { !jobsQ.isLoading && (
        <section className="mt-4 rounded-xl border border-border/80 bg-card/90">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
            <h2 className="text-base font-semibold">
              Job runs
              { jobs.length > 0 && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  ({ jobs.length }{ jobsQ.data?.nextCursor ? '+' : '' })
                </span>
              ) }
            </h2>
            { jobsQ.data?.generatedAt && (
              <span className="text-xs text-muted-foreground">
                Generated { fmtDateTime(jobsQ.data.generatedAt) }
              </span>
            ) }
          </div>
          <ScrollArea className="h-[calc(100vh-280px)] min-h-[320px]">
            <div className="px-4 pb-4">
              { jobs.length === 0 && !jobsQ.isLoading ? (
                <p className="mt-4 rounded-md border border-border/60 p-4 text-center text-sm text-muted-foreground">
                  No ingestion jobs match the current filters.
                </p>
              ) : (
                <table className="mt-3 min-w-[900px] w-full text-left text-sm">
                  <thead className="sticky top-0 bg-card/95 text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    <tr>
                      <th className="py-2 pr-4">Job ID</th>
                      <th className="py-2 pr-4">Source / Provider</th>
                      <th className="py-2 pr-4">AOI</th>
                      <th className="py-2 pr-4">State</th>
                      <th className="py-2 pr-4">Window</th>
                      <th className="py-2 pr-4">
                        <Download className="inline h-3 w-3 mr-1" aria-hidden="true" />
                        Counts
                      </th>
                      <th className="py-2 pr-4">Message</th>
                      <th className="py-2">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    { jobs.map((job) => (
                      <JobRow key={ job.jobId } job={ job } />
                    )) }
                  </tbody>
                </table>
              ) }
              { jobsQ.data?.nextCursor && (
                <p className="mt-3 text-center text-xs text-muted-foreground">
                  More results available — narrow filters to page deeper.
                </p>
              ) }
            </div>
          </ScrollArea>
        </section>
      ) }
    </main>
  );
}
