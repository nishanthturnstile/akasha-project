import { useParams, Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileText,
  LockKeyhole,
  Loader2,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { useIngestionJob, useIngestionJobEvents } from '@/lib/queries';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import type { IngestionJobDetail, IngestionJobEvent } from '@/types/api';
import OrchestrationPipeline from './components/OrchestrationPipeline';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  return value.slice(0, 10);
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = value.slice(0, 10);
  const t = value.slice(11, 19);
  return `${d} ${t} UTC`;
}

function fmtCount(value: number | null | undefined): string {
  if (value == null) return '—';
  return value.toLocaleString();
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
    return <CheckCircle2 className="h-4 w-4" aria-hidden="true" />;
  }
  if (s === 'running') return <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />;
  if (s === 'planned' || s === 'queued' || s === 'skipped_not_due') {
    return <Clock className="h-4 w-4" aria-hidden="true" />;
  }
  if (s === 'blocked_by_lock' || s === 'skipped_gated') {
    return <LockKeyhole className="h-4 w-4" aria-hidden="true" />;
  }
  if (s === 'failed' || s === 'validation_failed' || s === 'cancelled') {
    return <XCircle className="h-4 w-4" aria-hidden="true" />;
  }
  return <AlertTriangle className="h-4 w-4" aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Section primitives
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">{ children }</p>
  );
}

function KVRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-x-4 border-t border-border/50 py-2 text-sm">
      <dt className="text-muted-foreground">{ label }</dt>
      <dd className="break-all">{ value ?? '—' }</dd>
    </div>
  );
}

function KVGrid({ children }: { children: React.ReactNode }) {
  return <dl>{ children }</dl>;
}

/** Display a JSON-like record as a compact definition list — no raw URIs shown. */
function RecordDisplay({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No data.</p>;
  }
  return (
    <dl className="divide-y divide-border/50 rounded-lg border border-border/60 bg-background/60 px-3">
      { entries.map(([key, val]) => (
        <div key={ key } className="grid grid-cols-[200px_1fr] gap-x-4 py-2 text-sm">
          <dt className="font-mono text-xs text-muted-foreground break-all">{ key }</dt>
          <dd className="break-all text-foreground">
            { val === null || val === undefined
              ? <span className="text-muted-foreground">null</span>
              : typeof val === 'object'
                ? <code className="text-xs">{ JSON.stringify(val) }</code>
                : String(val) }
          </dd>
        </div>
      )) }
    </dl>
  );
}

/** Render an artifact handle as a monospace label — never as a clickable external URL. */
function ArtifactHandle({ label, handle }: { label: string; handle: string | null | undefined }) {
  if (!handle) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-border/50 bg-background/60 px-3 py-2 text-sm">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <p className="text-xs text-muted-foreground">{ label }</p>
          <p className="text-muted-foreground">Not available</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3 rounded-md border border-border/50 bg-background/60 px-3 py-2 text-sm">
      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{ label }</p>
        <code className="block break-all font-mono text-xs text-foreground">{ handle }</code>
      </div>
    </div>
  );
}

function ProblemList({ items, label }: { items: string[]; label: string }) {
  if (items.length === 0) {
    return (
      <p className="rounded-md border border-border/50 px-3 py-2 text-sm text-muted-foreground">
        No { label } recorded.
      </p>
    );
  }
  return (
    <ul className="grid gap-1.5" role="list" aria-label={ label }>
      { items.map((item, idx) => (
        <li
          key={ idx }
          className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100"
        >
          { item }
        </li>
      )) }
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Tab panels
// ---------------------------------------------------------------------------

function PipelineTab({
  job,
  events,
  eventsError,
  eventsLoading,
}: {
  job: IngestionJobDetail;
  events: IngestionJobEvent[];
  eventsError: unknown;
  eventsLoading: boolean;
}) {
  return (
    <div className="grid gap-3">
      { eventsLoading && (
        <p
          className="rounded-md border border-info/30 bg-info/10 px-3 py-2 text-sm text-info"
          role="status"
        >
          Loading pipeline events. Job-detail fallback evidence remains available.
        </p>
      ) }
      { Boolean(eventsError) && (
        <p
          className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100"
          role="status"
        >
          Pipeline events are unavailable. Showing the internal orchestration view from safe job-detail
          fallback data.
        </p>
      ) }
      <OrchestrationPipeline job={ job } events={ events } />
    </div>
  );
}

function SummaryTab({ job }: { job: IngestionJobDetail }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section>
        <SectionLabel>Identity</SectionLabel>
        <KVGrid>
          <KVRow label="Job ID" value={ <code className="font-mono text-xs">{ job.jobId }</code> } />
          <KVRow label="Source" value={ job.sourceId } />
          <KVRow label="Provider" value={ job.provider } />
          <KVRow label="AOI" value={ job.aoiId } />
          <KVRow label="State" value={
            <Badge variant={ stateVariant(job.state) } className="inline-flex items-center gap-1">
              <StateIcon state={ job.state } />
              { job.state }
            </Badge>
          } />
          { job.failureKind && (
            <KVRow label="Failure kind" value={
              <span className="text-destructive">{ job.failureKind }</span>
            } />
          ) }
          <KVRow label="Schedule decision" value={ job.scheduleDecision } />
        </KVGrid>
      </section>

      <section>
        <SectionLabel>Timing</SectionLabel>
        <KVGrid>
          <KVRow label="Window start" value={ fmtDate(job.windowStart) } />
          <KVRow label="Window end" value={ fmtDate(job.windowEnd) } />
          <KVRow label="Started at" value={ fmtDateTime(job.startedAt) } />
          <KVRow label="Finished at" value={ fmtDateTime(job.finishedAt) } />
          <KVRow label="Updated at" value={ fmtDateTime(job.updatedAt) } />
          <KVRow label="Next due" value={ fmtDateTime(job.nextDueAt) } />
        </KVGrid>
      </section>

      <section>
        <SectionLabel>Counts</SectionLabel>
        <div className="grid grid-cols-4 gap-3">
          { (
            [
              { label: 'Found', value: job.foundCount, tone: '' },
              { label: 'Selected', value: job.selectedCount, tone: 'text-warning' },
              { label: 'Downloaded', value: job.downloadedCount, tone: 'text-success' },
              { label: 'Rejected', value: job.rejectedCount, tone: 'text-destructive' },
            ] as const
          ).map(({ label, value, tone }) => (
            <article key={ label } className="rounded-lg border border-border/60 bg-background/60 p-3 text-center">
              <p className="text-xs text-muted-foreground">{ label }</p>
              <p className={ `mt-1 text-2xl font-semibold tabular-nums ${tone}` }>{ fmtCount(value) }</p>
            </article>
          )) }
        </div>
      </section>

      { job.message && (
        <section>
          <SectionLabel>Message</SectionLabel>
          <p className="rounded-md border border-border/50 bg-background/60 px-3 py-2 text-sm">
            { job.message }
          </p>
        </section>
      ) }
    </div>
  );
}

function ProviderInputsTab({ job }: { job: IngestionJobDetail }) {
  return (
    <div className="grid gap-6">
      <section>
        <SectionLabel>Provider input summary</SectionLabel>
        <RecordDisplay data={ job.providerInputSummary } />
      </section>
      <section>
        <SectionLabel>Job request parameters</SectionLabel>
        <RecordDisplay data={ job.request } />
      </section>
      <section>
        <SectionLabel>Provider response summary</SectionLabel>
        <RecordDisplay data={ job.providerResponseSummary } />
      </section>
    </div>
  );
}

function CandidatesTab({ job }: { job: IngestionJobDetail }) {
  return (
    <div className="grid gap-6">
      <section>
        <SectionLabel>Search manifest</SectionLabel>
        <ArtifactHandle label="Search manifest handle" handle={ job.searchManifestHandle } />
      </section>

      <section>
        <SectionLabel>Candidate counts</SectionLabel>
        <div className="grid grid-cols-3 gap-3">
          { (
            [
              { label: 'Found', value: job.foundCount, tone: '' },
              { label: 'Selected', value: job.selectedCount, tone: 'text-warning' },
              { label: 'Rejected', value: job.rejectedCount, tone: 'text-destructive' },
            ] as const
          ).map(({ label, value, tone }) => (
            <article key={ label } className="rounded-lg border border-border/60 bg-background/60 p-3 text-center">
              <p className="text-xs text-muted-foreground">{ label }</p>
              <p className={ `mt-1 text-2xl font-semibold tabular-nums ${tone}` }>{ fmtCount(value) }</p>
            </article>
          )) }
        </div>
      </section>

      <section>
        <SectionLabel>Rejection reasons ({ job.rejectionReasons.length })</SectionLabel>
        <ProblemList items={ job.rejectionReasons } label="rejection reasons" />
      </section>
    </div>
  );
}

function DownloadsTab({ job }: { job: IngestionJobDetail }) {
  return (
    <div className="grid gap-6">
      <section>
        <SectionLabel>Download manifest</SectionLabel>
        <ArtifactHandle label="Download manifest handle" handle={ job.downloadManifestHandle } />
      </section>

      <section>
        <SectionLabel>Prepare manifests ({ job.prepareManifestHandles.length })</SectionLabel>
        { job.prepareManifestHandles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No prepare manifests recorded.</p>
        ) : (
          <div className="grid gap-2">
            { job.prepareManifestHandles.map((handle, idx) => (
              <ArtifactHandle
                key={ idx }
                label={ `Prepare manifest ${idx + 1}` }
                handle={ handle }
              />
            )) }
          </div>
        ) }
      </section>

      <section>
        <SectionLabel>Downloaded</SectionLabel>
        <article className="rounded-lg border border-border/60 bg-background/60 p-4 text-center w-36">
          <p className="text-xs text-muted-foreground">Downloaded</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums text-success">
            { fmtCount(job.downloadedCount) }
          </p>
        </article>
      </section>
    </div>
  );
}

function VerificationTab({ job }: { job: IngestionJobDetail }) {
  return (
    <div className="grid gap-6">
      <section>
        <SectionLabel>Verification summary</SectionLabel>
        <RecordDisplay data={ job.verificationSummary } />
      </section>

      <section>
        <SectionLabel>Validation problems ({ job.validationProblems.length })</SectionLabel>
        <ProblemList items={ job.validationProblems } label="validation problems" />
      </section>
    </div>
  );
}

function LedgerTab({ job }: { job: IngestionJobDetail }) {
  const rows = job.ledgerRows;
  if (rows.length === 0) {
    return (
      <p className="rounded-md border border-border/50 px-3 py-2 text-sm text-muted-foreground">
        No ledger rows recorded for this job.
      </p>
    );
  }

  // Collect all unique keys across rows for dynamic columns
  const allKeys = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));

  return (
    <div>
      <SectionLabel>Ledger entries ({ rows.length })</SectionLabel>
      <ScrollArea className="max-h-[480px]">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-card/80 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr>
                { allKeys.map((k) => (
                  <th key={ k } className="whitespace-nowrap py-2 pr-4 font-medium">{ k }</th>
                )) }
              </tr>
            </thead>
            <tbody>
              { rows.map((row, idx) => (
                <tr key={ idx } className="border-t border-border/50 align-top hover:bg-accent/30">
                  { allKeys.map((k) => {
                    const val = row[k];
                    return (
                      <td key={ k } className="py-2 pr-4 text-foreground">
                        { val === null || val === undefined
                          ? <span className="text-muted-foreground">—</span>
                          : typeof val === 'object'
                            ? <code className="text-[11px]">{ JSON.stringify(val) }</code>
                            : String(val) }
                      </td>
                    );
                  }) }
                </tr>
              )) }
            </tbody>
          </table>
        </div>
      </ScrollArea>
    </div>
  );
}

function LogsTab({ job }: { job: IngestionJobDetail }) {
  const handleEntries = Object.entries(job.artifactHandles);

  return (
    <div className="grid gap-6">
      { job.message && (
        <section>
          <SectionLabel>Job message</SectionLabel>
          <p className="rounded-md border border-border/50 bg-background/60 px-3 py-2 text-sm">
            { job.message }
          </p>
        </section>
      ) }

      { job.failureKind && (
        <section>
          <SectionLabel>Failure</SectionLabel>
          <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            <strong>Kind:</strong> { job.failureKind }
          </p>
        </section>
      ) }

      <section>
        <SectionLabel>Artifact handles ({ handleEntries.length })</SectionLabel>
        { handleEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No artifact handles registered for this job.</p>
        ) : (
          <div className="grid gap-2">
            { handleEntries.map(([key, handle]) => (
              <ArtifactHandle key={ key } label={ key } handle={ handle } />
            )) }
          </div>
        ) }
        <p className="mt-2 text-xs text-muted-foreground">
          Artifact handles are storage keys managed server-side. Raw content is not exposed here.
        </p>
      </section>
    </div>
  );
}

function ActionsTab({
  job,
  onRefresh,
  isRefreshing,
}: {
  job: IngestionJobDetail;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <div className="grid gap-6">
      <section>
        <SectionLabel>Schedule context</SectionLabel>
        <KVGrid>
          <KVRow label="Schedule decision" value={ job.scheduleDecision } />
          <KVRow label="Next due" value={ fmtDateTime(job.nextDueAt) } />
        </KVGrid>
      </section>

      <section>
        <SectionLabel>Actions</SectionLabel>
        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={ isRefreshing }
            onClick={ onRefresh }
            aria-label="Refresh job detail"
          >
            <RefreshCw className={ `h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}` } aria-hidden="true" />
            Refresh job detail
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Job state: <strong className="text-foreground">{ job.state }</strong>.
          { job.state === 'running'
            ? ' Refresh to track progress.'
            : ' No further actions are available from the UI for terminal jobs.' }
        </p>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function IngestionJobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const safeJobId = jobId ?? '';
  const jobQ = useIngestionJob(safeJobId);
  const eventsQ = useIngestionJobEvents(safeJobId);
  const job = jobQ.data;
  const events = eventsQ.data?.events ?? [];

  return (
    <main
      className="h-full overflow-auto bg-background p-4 text-foreground"
      data-testid="ingestion-job-detail-page"
    >
      {/* Back navigation */}
      <div className="mb-3">
        <Link
          to="/admin/ingestion/jobs"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Back to ingestion jobs list"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Ingestion jobs
        </Link>
      </div>

      {/* Header */}
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
              Operator console · Job detail
            </p>
            <h1 className="mt-1 flex flex-wrap items-center gap-2 text-xl font-semibold">
              { job ? (
                <>
                  <Badge
                    variant={ stateVariant(job.state) }
                    className="inline-flex items-center gap-1 text-xs"
                  >
                    <StateIcon state={ job.state } />
                    { job.state }
                  </Badge>
                  <span className="font-mono text-base">{ job.sourceId }</span>
                  { job.aoiId && (
                    <span className="text-base font-normal text-muted-foreground">/ { job.aoiId }</span>
                  ) }
                </>
              ) : (
                <span className="font-mono text-base">{ safeJobId }</span>
              ) }
            </h1>
            { job && (
              <p className="mt-1 font-mono text-xs text-muted-foreground">{ job.jobId }</p>
            ) }
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={ jobQ.isFetching }
            onClick={ () => void jobQ.refetch() }
            aria-label="Refresh job detail"
          >
            <RefreshCw
              className={ `h-3.5 w-3.5 ${jobQ.isFetching ? 'animate-spin' : ''}` }
              aria-hidden="true"
            />
            Refresh
          </Button>
        </div>
      </section>

      {/* Error */}
      { jobQ.error && (
        <p
          className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200"
          role="alert"
        >
          Failed to load job detail.{ ' ' }
          { (jobQ.error as Error).message ?? 'An unexpected error occurred.' }
        </p>
      ) }

      {/* Skeleton */}
      { jobQ.isLoading && (
        <div className="glass scan-sweep mt-4 h-48 rounded-xl" aria-busy="true" aria-label="Loading job detail" />
      ) }

      {/* Content */}
      { job && (
        <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
          <Tabs defaultValue="pipeline">
            <div className="overflow-x-auto pb-1">
              <TabsList className="mb-1 flex-nowrap whitespace-nowrap">
                <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="provider-inputs">Provider Inputs</TabsTrigger>
                <TabsTrigger value="candidates">Candidates</TabsTrigger>
                <TabsTrigger value="downloads">Downloads</TabsTrigger>
                <TabsTrigger value="verification">Verification</TabsTrigger>
                <TabsTrigger value="ledger">Ledger</TabsTrigger>
                <TabsTrigger value="logs">Logs</TabsTrigger>
                <TabsTrigger value="actions">Actions</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="pipeline" forceMount>
              <PipelineTab
                job={ job }
                events={ events }
                eventsError={ eventsQ.error }
                eventsLoading={ eventsQ.isLoading }
              />
            </TabsContent>

            <TabsContent value="summary" forceMount>
              <SummaryTab job={ job } />
            </TabsContent>

            <TabsContent value="provider-inputs" forceMount>
              <ProviderInputsTab job={ job } />
            </TabsContent>

            <TabsContent value="candidates" forceMount>
              <CandidatesTab job={ job } />
            </TabsContent>

            <TabsContent value="downloads" forceMount>
              <DownloadsTab job={ job } />
            </TabsContent>

            <TabsContent value="verification" forceMount>
              <VerificationTab job={ job } />
            </TabsContent>

            <TabsContent value="ledger" forceMount>
              <LedgerTab job={ job } />
            </TabsContent>

            <TabsContent value="logs" forceMount>
              <LogsTab job={ job } />
            </TabsContent>

            <TabsContent value="actions" forceMount>
              <ActionsTab
                job={ job }
                onRefresh={ () => void jobQ.refetch() }
                isRefreshing={ jobQ.isFetching }
              />
            </TabsContent>
          </Tabs>
        </section>
      ) }
    </main>
  );
}
