import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  HardDrive,
  RefreshCw,
  Satellite,
  XCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useImagerySourceMonitoring } from '@/lib/queries';
import type {
  ImagerySourceMonitoringSource,
  MonitoringFailure,
  StoragePrefixUsage,
} from '@/types/api';

function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a';
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a';
  if (value === 0) return '0 B';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const scaled = value / 1024 ** index;
  return `${formatNumber(scaled, scaled >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'n/a';
  return value.slice(0, 10);
}

function healthTone(source: ImagerySourceMonitoringSource): string {
  if (source.availabilityStatus === 'gated') {
    return 'border-zinc-500/40 bg-zinc-500/10 text-zinc-100';
  }
  if (source.status === 'error') {
    return 'border-red-500/50 bg-red-500/10 text-red-100';
  }
  if (source.status === 'warning') {
    return 'border-amber-500/50 bg-amber-500/10 text-amber-100';
  }
  return 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100';
}

function healthLabel(source: ImagerySourceMonitoringSource): string {
  if (source.availabilityStatus === 'gated') return 'gated';
  if (source.status === 'error') return 'error';
  if (source.isUpstreamDataStale) return 'upstream stale';
  if (source.status === 'warning') return 'attention';
  if (source.lastError) return 'error';
  if (source.isSuccessfulCompositeStale) return 'stale composite';
  if (source.isStale) return 'stale catalog';
  if (source.warnings.length || (source.tileUnavailableReasons?.length ?? 0) > 0) return 'attention';
  return 'ok';
}

function StatusPill({ source }: { source: ImagerySourceMonitoringSource }) {
  const label = healthLabel(source);
  const Icon = label === 'ok' ? CheckCircle2 : label === 'error' ? XCircle : AlertTriangle;
  return (
    <span className={ `inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${healthTone(source)}` }>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      { label }
    </span>
  );
}

function LatestJobPill({ source }: { source: ImagerySourceMonitoringSource }) {
  const jobId = source.latestSchedulerJobId;
  if (!jobId) return <span className="text-xs text-muted-foreground">—</span>;
  const state = source.latestSchedulerJobState ?? 'unknown';
  const isRunning = state === 'running' || state === 'queued';
  const isFailed = state === 'failed' || state === 'validation_failed' || state === 'cancelled';
  const pillClass = isFailed
    ? 'border-red-500/50 bg-red-500/10 text-red-200 hover:bg-red-500/20'
    : isRunning
      ? 'border-amber-500/50 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20'
      : 'border-border/60 bg-card/80 text-muted-foreground hover:bg-card';
  return (
    <Link
      to={ `/admin/ingestion/jobs/${encodeURIComponent(jobId)}` }
      className={ `inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors ${pillClass}` }
      title={ `Job ${jobId} · ${state}` }
    >
      <Clock3 className="h-3 w-3" aria-hidden="true" />
      { state }
    </Link>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'default',
}: {
  icon: typeof Satellite;
  label: string;
  value: string;
  detail: string;
  tone?: 'default' | 'warn' | 'ok';
}) {
  const toneClass =
    tone === 'warn'
      ? 'border-amber-500/40 bg-amber-500/10'
      : tone === 'ok'
        ? 'border-emerald-500/40 bg-emerald-500/10'
        : 'border-border/80 bg-card/90';
  return (
    <article className={ `rounded-xl border p-4 ${toneClass}` }>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{ label }</p>
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </div>
      <p className="mt-3 text-2xl font-semibold">{ value }</p>
      <p className="mt-1 text-sm text-muted-foreground">{ detail }</p>
    </article>
  );
}

function SourceRow({ source }: { source: ImagerySourceMonitoringSource }) {
  const reasonValues = [
    ...source.statusReasons,
    ...source.warnings,
    ...(source.tileUnavailableReasons ?? []),
    source.hasUnresolvedIngestionFailure
      ? source.lastIngestionFailure?.error ?? 'unresolved ingestion failure'
      : '',
    source.lastError ?? '',
  ].filter((reason): reason is string => Boolean(reason));
  const reasons = Array.from(new Set(reasonValues));
  return (
    <tr className="border-t border-border/60 align-top">
      <td className="py-3 pr-4">
        <div className="font-medium">{ source.label ?? source.sourceId }</div>
        <div className="mt-1 text-xs text-muted-foreground">{ source.sourceId }</div>
      </td>
      <td className="py-3 pr-4"><StatusPill source={ source } /></td>
      <td className="py-3 pr-4 text-sm">
        <div>{ formatDate(source.latestAvailableDate) }</div>
        <div className="text-xs text-muted-foreground">
          { source.daysSinceLatestAvailable === null || source.daysSinceLatestAvailable === undefined
            ? 'no catalog date'
            : `${source.daysSinceLatestAvailable} day(s) ago` }
        </div>
      </td>
      <td className="py-3 pr-4 text-sm">
        <div>{ formatDate(source.latestSuccessfulCompositeDate) }</div>
        <div className="text-xs text-muted-foreground">
          { source.latestSuccessfulCompositeAoiId ?? 'no AOI success' }
        </div>
      </td>
      <td className="py-3 pr-4 text-sm">
        <div>{ formatDate(source.latestSuccessfulSearchUpdatedAt) }</div>
        <div className="text-xs text-muted-foreground">
          { source.daysSinceLatestSuccessfulSearch === null
            || source.daysSinceLatestSuccessfulSearch === undefined
            ? source.latestSuccessfulSearchAoiId ?? 'no search heartbeat'
            : `${source.daysSinceLatestSuccessfulSearch} day(s) ago` }
        </div>
      </td>
      <td className="py-3 pr-4 text-sm">
        <div>{ formatNumber(source.coveragePercent, 1) }%</div>
        <div className="text-xs text-muted-foreground">
          usable { formatNumber(source.usablePixelPercent, 1) }%
        </div>
      </td>
      <td className="py-3 pr-4 text-sm">
        <div>{ source.tileAvailableDateCount } / { source.dateCount }</div>
        <div className="text-xs text-muted-foreground">{ source.refreshPolicy ?? 'manual' }</div>
      </td>
      <td className="py-3 pr-4"><LatestJobPill source={ source } /></td>
      <td className="py-3 text-sm text-muted-foreground">
        { reasons.length ? reasons.slice(0, 3).join(' | ') : 'No active warning' }
      </td>
    </tr>
  );
}

function StorageRow({ prefix }: { prefix: StoragePrefixUsage }) {
  const hasZeroByte = (prefix.zeroByteObjectCount ?? 0) > 0;
  return (
    <tr className="border-t border-border/60">
      <td className="py-2 pr-4 font-medium">{ prefix.prefix }</td>
      <td className="py-2 pr-4">{ formatNumber(prefix.objectCount) }</td>
      <td className="py-2 pr-4">{ formatBytes(prefix.bytes) }</td>
      <td className={ `py-2 ${hasZeroByte ? 'text-amber-100' : 'text-muted-foreground'}` }>
        { formatNumber(prefix.zeroByteObjectCount ?? 0) }
      </td>
    </tr>
  );
}

function FailureRow({ failure }: { failure: MonitoringFailure }) {
  return (
    <article className="rounded-md border border-border/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{ failure.failureKind }</span>
        <span className="text-xs text-muted-foreground">{ formatDate(failure.updatedAt) }</span>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{ failure.productId ?? 'unknown product' }</p>
      { failure.error && <p className="mt-2 text-sm text-amber-100">{ failure.error }</p> }
    </article>
  );
}

export default function MonitoringGlobalView() {
  const monitoringQ = useImagerySourceMonitoring();
  const data = monitoringQ.data;
  const sources = data?.sources ?? [];
  const activeSources = sources.filter((source) => source.availabilityStatus !== 'gated');
  const attentionSources = activeSources.filter((source) => source.status !== 'ok');
  const latestCompositeDates = activeSources
    .map((source) => source.latestSuccessfulCompositeDate)
    .filter(Boolean)
    .sort();
  const latestComposite = latestCompositeDates[latestCompositeDates.length - 1];
  const storage = data?.storage;
  const zeroByteCount = storage?.zeroByteObjectCount ?? 0;
  const ledger = data?.ingestionLedger;
  const failures = ledger?.lastFailures ?? [];

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="monitoring-global-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Operator monitoring</p>
            <h1 className="mt-1 text-2xl font-semibold">Imagery source health</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Generated { data ? formatDate(data.generatedAt) : 'after refresh' }
            </p>
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm disabled:opacity-50"
            disabled={ monitoringQ.isFetching }
            onClick={ () => void monitoringQ.refetch() }
            type="button"
          >
            <RefreshCw className={ `h-4 w-4 ${monitoringQ.isFetching ? 'animate-spin' : ''}` } aria-hidden="true" />
            Refresh
          </button>
        </div>
      </section>

      { monitoringQ.error && (
        <p className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100" role="status">
          Imagery source monitoring could not be loaded.
        </p>
      ) }

      { monitoringQ.isLoading && <div className="glass scan-sweep mt-4 h-28 rounded-xl" /> }

      { data && (
        <>
          <section className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={ Satellite }
              label="Active sources"
              value={ formatNumber(activeSources.length) }
              detail={ `${formatNumber(attentionSources.length)} source(s) need attention` }
              tone={ attentionSources.length ? 'warn' : 'ok' }
            />
            <MetricCard
              icon={ Clock3 }
              label="Latest composite"
              value={ formatDate(latestComposite) }
              detail={ `${data.staleAfterDays} day stale threshold` }
            />
            <MetricCard
              icon={ HardDrive }
              label="Storage"
              value={ formatBytes(storage?.bytes) }
              detail={ `${formatNumber(storage?.objectCount)} object(s) in ${storage?.bucket ?? 'bucket'}` }
              tone={ zeroByteCount > 0 ? 'warn' : 'default' }
            />
            <MetricCard
              icon={ Database }
              label="Ledger failures"
              value={ formatNumber(failures.length) }
              detail={ ledger?.status ?? 'ledger unavailable' }
              tone={ failures.length ? 'warn' : 'ok' }
            />
          </section>

          <section className="mt-4 overflow-x-auto rounded-xl border border-border/80 bg-card/90 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Source refresh status</h2>
              <p className="text-sm text-muted-foreground">{ sources.length } registered source(s)</p>
            </div>
            <table className="mt-3 min-w-280 w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                <tr>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">State</th>
                  <th className="py-2 pr-4">Latest catalog</th>
                  <th className="py-2 pr-4">Composite success</th>
                  <th className="py-2 pr-4">Search heartbeat</th>
                  <th className="py-2 pr-4">Coverage</th>
                  <th className="py-2 pr-4">Tiles</th>
                  <th className="py-2 pr-4">Latest job</th>
                  <th className="py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                { sources.map((source) => <SourceRow key={ source.sourceId } source={ source } />) }
              </tbody>
            </table>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-[1fr_380px]">
            <article className="overflow-x-auto rounded-xl border border-border/80 bg-card/90 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">Object storage by source prefix</h2>
                <p className={ `text-sm ${zeroByteCount > 0 ? 'text-amber-100' : 'text-muted-foreground'}` }>
                  { formatNumber(zeroByteCount) } zero-byte object(s)
                </p>
              </div>
              <table className="mt-3 min-w-130 w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Prefix</th>
                    <th className="py-2 pr-4">Objects</th>
                    <th className="py-2 pr-4">Bytes</th>
                    <th className="py-2">Zero-byte</th>
                  </tr>
                </thead>
                <tbody>
                  { (storage?.byPrefix ?? []).map((prefix) => <StorageRow key={ prefix.prefix } prefix={ prefix } />) }
                  { !storage?.byPrefix.length && (
                    <tr>
                      <td className="py-3 text-muted-foreground" colSpan={ 4 }>
                        No storage prefixes reported.
                      </td>
                    </tr>
                  ) }
                </tbody>
              </table>
            </article>

            <article className="rounded-xl border border-border/80 bg-card/90 p-4">
              <h2 className="text-lg font-semibold">Recent ingestion failures</h2>
              <div className="mt-3 grid gap-2">
                { failures.slice(0, 5).map((failure) => (
                  <FailureRow
                    key={ `${failure.sourceId ?? 'source'}-${failure.productId ?? failure.updatedAt}` }
                    failure={ failure }
                  />
                )) }
                { failures.length === 0 && (
                  <p className="rounded-md border border-border/80 p-3 text-sm text-muted-foreground">
                    No recent failures reported by the ingestion ledger.
                  </p>
                ) }
              </div>
            </article>
          </section>
        </>
      ) }
    </main>
  );
}
