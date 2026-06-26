import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Loader2,
  RefreshCw,
  Satellite,
  XCircle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  useImagerySourceMonitoring,
  useIngestionJobs,
  useIngestionSchedules,
} from '@/lib/queries';
import type {
  ImagerySourceMonitoringSource,
  IngestionJobSummary,
  IngestionScheduleItem,
} from '@/types/api';

type Tone = 'default' | 'ok' | 'warn' | 'danger' | 'info';
type BadgeVariant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral';
type SourceHealth = 'ok' | 'attention' | 'error' | 'gated';

const JOBS_ROUTE = '/admin/ingestion/jobs';
const SCHEDULES_ROUTE = '/admin/ingestion/schedules';
const FAILURE_STATES = new Set(['failed', 'validation_failed', 'cancelled']);
const SUCCESS_STATES = new Set(['succeeded']);

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = value.slice(0, 10);
  const time = value.length >= 16 ? value.slice(11, 16) : '';
  return time ? `${date} ${time}` : date;
}

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat().format(value);
}

function jobUpdatedAt(job: IngestionJobSummary): string {
  return job.updatedAt ?? job.finishedAt ?? job.startedAt ?? '';
}

function newestJob(jobs: IngestionJobSummary[], predicate: (job: IngestionJobSummary) => boolean) {
  return jobs
    .filter(predicate)
    .sort((a, b) => jobUpdatedAt(b).localeCompare(jobUpdatedAt(a)))[0];
}

function stateVariant(state: string | null | undefined): BadgeVariant {
  const normalized = state?.toLowerCase() ?? '';
  if (SUCCESS_STATES.has(normalized)) return 'success';
  if (normalized === 'running' || normalized === 'queued') return 'info';
  if (normalized === 'planned' || normalized.startsWith('skipped') || normalized === 'blocked_by_lock') {
    return 'warning';
  }
  if (FAILURE_STATES.has(normalized)) return 'destructive';
  return 'neutral';
}

function sourceHealthLabel(source: ImagerySourceMonitoringSource): SourceHealth {
  if (source.availabilityStatus === 'gated') return 'gated';
  if (source.status === 'error' || source.lastError || source.hasUnresolvedIngestionFailure) {
    return 'error';
  }
  if (
    source.status === 'warning'
    || source.isStale
    || source.isSuccessfulCompositeStale
    || source.isSuccessfulSearchStale
    || source.isUpstreamDataStale
    || source.warnings.length > 0
    || (source.tileUnavailableReasons?.length ?? 0) > 0
  ) {
    return 'attention';
  }
  return 'ok';
}

function sourceCounts(sources: ImagerySourceMonitoringSource[]) {
  return sources.reduce(
    (counts, source) => {
      const label = sourceHealthLabel(source);
      return { ...counts, [label]: counts[label] + 1 };
    },
    { ok: 0, attention: 0, error: 0, gated: 0 },
  );
}

function statusText(status: string | null | undefined): string {
  if (!status) return 'Unknown';
  return status.replace(/_/g, ' ');
}

function CardShell({
  to,
  tone,
  children,
  ariaLabel,
}: {
  to?: string;
  tone: Tone;
  children: React.ReactNode;
  ariaLabel: string;
}) {
  const toneClass =
    tone === 'ok'
      ? 'border-success/35 bg-success/10'
      : tone === 'warn'
        ? 'border-warning/35 bg-warning/10'
        : tone === 'danger'
          ? 'border-destructive/35 bg-destructive/10'
          : tone === 'info'
            ? 'border-info/35 bg-info/10'
            : 'border-border/80 bg-card/90';
  const className = `group rounded-xl border p-4 transition-colors ${toneClass} ${
    to ? 'hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring' : ''
  }`;

  if (to) {
    return (
      <Link to={ to } aria-label={ ariaLabel } className={ className }>
        { children }
      </Link>
    );
  }

  return (
    <article aria-label={ ariaLabel } className={ className }>
      { children }
    </article>
  );
}

function OverviewCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'default',
  to,
  badge,
}: {
  icon: typeof Satellite;
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
  to?: string;
  badge?: React.ReactNode;
}) {
  return (
    <CardShell to={ to } tone={ tone } ariaLabel={ label }>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{ label }</p>
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <p className="text-2xl font-semibold">{ value }</p>
        { badge }
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{ detail }</p>
      { to && (
        <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-info">
          Open
          <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
        </span>
      ) }
    </CardShell>
  );
}

function JobCard({
  label,
  job,
  emptyDetail,
  tone,
}: {
  label: string;
  job?: IngestionJobSummary;
  emptyDetail: string;
  tone: Tone;
}) {
  return (
    <OverviewCard
      icon={ label.includes('failed') ? XCircle : CheckCircle2 }
      label={ label }
      value={ job ? job.sourceId : 'None reported' }
      detail={ job ? `${fmtDateTime(jobUpdatedAt(job))} · ${job.aoiId ?? 'global AOI'}` : emptyDetail }
      tone={ job ? tone : 'default' }
      to={ job ? `${JOBS_ROUTE}/${encodeURIComponent(job.jobId)}` : JOBS_ROUTE }
      badge={ job && <Badge variant={ stateVariant(job.state) }>{ job.state }</Badge> }
    />
  );
}

function AlertMessage({
  children,
  tone = 'danger',
}: {
  children: React.ReactNode;
  tone?: 'danger' | 'warn' | 'muted';
}) {
  const className =
    tone === 'warn'
      ? 'border-warning/40 bg-warning/10 text-warning'
      : tone === 'muted'
        ? 'border-border/60 bg-muted/30 text-muted-foreground'
        : 'border-destructive/40 bg-destructive/10 text-destructive';

  return (
    <p className={ `mt-4 rounded-md border p-3 text-sm ${className}` } role={ tone === 'danger' ? 'alert' : 'status' }>
      { children }
    </p>
  );
}

function dueCounts(schedules: IngestionScheduleItem[]) {
  return schedules.reduce(
    (counts, schedule) => ({
      due: counts.due + (schedule.isDue === true && schedule.isOverdue !== true ? 1 : 0),
      overdue: counts.overdue + (schedule.isOverdue === true ? 1 : 0),
    }),
    { due: 0, overdue: 0 },
  );
}

function sourceHealthSummary(sources: ImagerySourceMonitoringSource[]): {
  value: string;
  detail: string;
  tone: Tone;
} {
  const counts = sourceCounts(sources);
  const activeTotal = counts.ok + counts.attention + counts.error;
  const issueTotal = counts.attention + counts.error;
  const value =
    sources.length === 0
      ? 'No sources'
      : issueTotal > 0
        ? `${formatNumber(issueTotal)} need attention`
        : `${formatNumber(counts.ok)} healthy`;
  const detail =
    sources.length === 0
      ? 'Monitoring source registry returned no rows'
      : `${formatNumber(activeTotal)} active · ${formatNumber(counts.gated)} gated`;
  const tone = counts.error > 0 ? 'danger' : issueTotal > 0 ? 'warn' : 'ok';

  return { value, detail, tone };
}

export default function AdminIngestionOverview() {
  const monitoringQ = useImagerySourceMonitoring();
  const schedulesQ = useIngestionSchedules();
  const jobsQ = useIngestionJobs({ limit: 50 });

  const schedules = schedulesQ.data?.schedules ?? [];
  const jobs = jobsQ.data?.jobs ?? [];
  const sources = monitoringQ.data?.sources ?? [];
  const counts = dueCounts(schedules);
  const failedJobs = jobs.filter((job) => FAILURE_STATES.has(job.state.toLowerCase()));
  const latestSuccessfulJob = newestJob(jobs, (job) => SUCCESS_STATES.has(job.state.toLowerCase()));
  const latestFailedJob = newestJob(jobs, (job) => FAILURE_STATES.has(job.state.toLowerCase()));
  const schedulerStatus = schedulesQ.data?.status ?? (schedulesQ.isLoading ? 'loading' : 'unknown');
  const schedulerTone: Tone =
    schedulesQ.data?.status === 'ok'
      ? 'ok'
      : schedulesQ.data?.status === 'unconfigured'
        ? 'warn'
        : schedulesQ.error || schedulesQ.data?.status === 'unavailable'
          ? 'danger'
          : 'default';
  const health = sourceHealthSummary(sources);
  const isLoading = monitoringQ.isLoading || schedulesQ.isLoading || jobsQ.isLoading;

  return (
    <main
      className="h-full overflow-auto bg-background p-4 text-foreground"
      data-testid="admin-ingestion-overview-page"
    >
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
              Admin · Internal operations
            </p>
            <h1 className="mt-1 text-2xl font-semibold">Ingestion overview</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Read-only scheduler, job-run, and imagery source health summary for operators.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={ SCHEDULES_ROUTE }>Schedules</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={ JOBS_ROUTE }>Jobs</Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={ monitoringQ.isFetching || schedulesQ.isFetching || jobsQ.isFetching }
              onClick={ () => {
                void monitoringQ.refetch();
                void schedulesQ.refetch();
                void jobsQ.refetch();
              } }
              aria-label="Refresh ingestion overview"
            >
              <RefreshCw
                className={
                  `h-3.5 w-3.5 ${
                    monitoringQ.isFetching || schedulesQ.isFetching || jobsQ.isFetching
                      ? 'animate-spin'
                      : ''
                  }`
                }
                aria-hidden="true"
              />
              Refresh
            </Button>
          </div>
        </div>
      </section>

      { monitoringQ.error && (
        <AlertMessage>Imagery source health could not be loaded.</AlertMessage>
      ) }
      { schedulesQ.error && (
        <AlertMessage>Ingestion schedules could not be loaded.</AlertMessage>
      ) }
      { jobsQ.error && (
        <AlertMessage>Ingestion jobs could not be loaded.</AlertMessage>
      ) }
      { schedulesQ.data?.lastError && (
        <AlertMessage tone="warn">
          Scheduler overview is available with a warning. Check the API logs for operator-only
          diagnostics.
        </AlertMessage>
      ) }
      { jobsQ.data?.lastError && (
        <AlertMessage tone="warn">
          Job overview is available with a warning. Check the API logs for operator-only
          diagnostics.
        </AlertMessage>
      ) }
      { schedulesQ.data?.status === 'unconfigured' && (
        <AlertMessage tone="muted">
          The ingestion scheduler is not configured for this environment yet.
        </AlertMessage>
      ) }

      { isLoading && (
        <div
          className="glass scan-sweep mt-4 h-32 rounded-xl"
          aria-busy="true"
          aria-label="Loading ingestion overview"
        />
      ) }

      <section className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <OverviewCard
          icon={ CalendarClock }
          label="Scheduler status"
          value={ statusText(schedulerStatus) }
          detail={
            schedulesQ.data?.generatedAt
              ? `Generated ${fmtDateTime(schedulesQ.data.generatedAt)}`
              : 'Awaiting scheduler snapshot'
          }
          tone={ schedulerTone }
          to={ SCHEDULES_ROUTE }
          badge={
            schedulerStatus === 'loading'
              ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
              : <Badge variant={ schedulerTone === 'ok' ? 'success' : schedulerTone === 'danger' ? 'destructive' : 'warning' }>
                { statusText(schedulerStatus) }
              </Badge>
          }
        />
        <OverviewCard
          icon={ Clock3 }
          label="Due / overdue"
          value={ `${formatNumber(counts.due)} due · ${formatNumber(counts.overdue)} overdue` }
          detail="Counts use backend isDue and isOverdue schedule fields"
          tone={ counts.overdue > 0 ? 'danger' : counts.due > 0 ? 'warn' : 'ok' }
          to={ SCHEDULES_ROUTE }
        />
        <OverviewCard
          icon={ AlertTriangle }
          label="Failed jobs"
          value={ formatNumber(failedJobs.length) }
          detail={ jobsQ.data?.nextCursor ? 'Recent page only; narrow jobs for history' : 'Failed, validation failed, or cancelled runs' }
          tone={ failedJobs.length > 0 ? 'danger' : 'ok' }
          to={ JOBS_ROUTE }
        />
        <JobCard
          label="Latest successful job"
          job={ latestSuccessfulJob }
          emptyDetail="No successful jobs in the latest scheduler page"
          tone="ok"
        />
        <JobCard
          label="Latest failed job"
          job={ latestFailedJob }
          emptyDetail="No failed jobs in the latest scheduler page"
          tone="danger"
        />
        <OverviewCard
          icon={ Satellite }
          label="Source health"
          value={ health.value }
          detail={ health.detail }
          tone={ health.tone }
        />
      </section>
    </main>
  );
}
