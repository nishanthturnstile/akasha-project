import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleOff,
  Database,
  FileCheck2,
  GitBranch,
  Loader2,
  LockKeyhole,
  Radio,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type {
  IngestionJobDetail,
  IngestionJobEvent,
  PipelineStageId,
  PipelineStageState,
} from '@/types/api';

const PIPELINE_STAGE_ORDER = [
  'planned',
  'approved_runtime',
  'lock',
  'search',
  'select',
  'download',
  'prepare',
  'composite',
  'verify',
  'upload',
  'stac',
  'ledger',
] as const satisfies readonly PipelineStageId[];

type StageId = (typeof PIPELINE_STAGE_ORDER)[number];

type StageSourceKind =
  | 'event-backed'
  | 'job-detail'
  | 'artifact-ledger'
  | 'unavailable';

interface StageDataSource {
  label: string;
  shortLabel: string;
  kind: StageSourceKind;
  fields: string;
  note: string;
}

const STAGE_DATA_SOURCE_MATRIX: Record<StageId, StageDataSource> = {
  planned: {
    label: 'Event-backed',
    shortLabel: 'Event',
    kind: 'event-backed',
    fields: 'job_created, dry_run_plan',
    note: 'Only currently reliable stage event. Falls back to job state when events are absent.',
  },
  approved_runtime: {
    label: 'Inferred from job detail',
    shortLabel: 'Inferred',
    kind: 'job-detail',
    fields: 'state',
    note: 'Runtime approval is inferred from scheduler state until a dedicated event exists.',
  },
  lock: {
    label: 'Unavailable/Internal operations',
    shortLabel: 'Internal',
    kind: 'unavailable',
    fields: 'state',
    note: 'Lock acquire/release is not yet exposed as safe per-stage telemetry.',
  },
  search: {
    label: 'Inferred from job detail',
    shortLabel: 'Inferred',
    kind: 'job-detail',
    fields: 'foundCount, failureKind',
    note: 'Provider search progress is inferred from candidate counts and failure kind.',
  },
  select: {
    label: 'Inferred from job detail',
    shortLabel: 'Inferred',
    kind: 'job-detail',
    fields: 'selectedCount, failureKind',
    note: 'Selection progress is inferred from selected candidate counts.',
  },
  download: {
    label: 'Inferred from job detail',
    shortLabel: 'Inferred',
    kind: 'job-detail',
    fields: 'downloadedCount, failureKind',
    note: 'Download progress is inferred from downloaded candidate counts.',
  },
  prepare: {
    label: 'Inferred from artifact handles/ledger rows',
    shortLabel: 'Artifacts',
    kind: 'artifact-ledger',
    fields: 'artifactHandles, ledgerRows, failureKind',
    note: 'COG preparation is inferred from sanitized artifact/ledger evidence.',
  },
  composite: {
    label: 'Inferred from artifact handles/ledger rows',
    shortLabel: 'Artifacts',
    kind: 'artifact-ledger',
    fields: 'artifactHandles, ledgerRows, failureKind',
    note: 'Composite work is inferred only when sanitized evidence names it explicitly.',
  },
  verify: {
    label: 'Inferred from job detail',
    shortLabel: 'Inferred',
    kind: 'job-detail',
    fields: 'verificationSummary, failureKind',
    note: 'Verification is inferred from validation/verification summaries.',
  },
  upload: {
    label: 'Inferred from artifact handles/ledger rows',
    shortLabel: 'Artifacts',
    kind: 'artifact-ledger',
    fields: 'artifactHandles, ledgerRows, failureKind',
    note: 'Upload is inferred only from sanitized storage artifact/ledger evidence.',
  },
  stac: {
    label: 'Inferred from artifact handles/ledger rows',
    shortLabel: 'Artifacts',
    kind: 'artifact-ledger',
    fields: 'artifactHandles, ledgerRows, failureKind',
    note: 'STAC registration is inferred from sanitized catalog/ledger evidence.',
  },
  ledger: {
    label: 'Inferred from artifact handles/ledger rows',
    shortLabel: 'Ledger',
    kind: 'artifact-ledger',
    fields: 'ledgerRows',
    note: 'Ledger write is inferred from sanitized ledger rows returned by the BFF.',
  },
};

interface StageDisplay {
  id: StageId;
  label: string;
  description: string;
  state: PipelineStageState;
  message: string;
  timestamp?: string;
  relatedTab?: string;
}

interface EventCompat {
  timestamp?: string;
  eventType?: string;
  event_type?: string;
  stage?: string;
  status?: string;
  message?: string;
}

const STAGE_LABELS: Record<StageId, { label: string; description: string; relatedTab?: string }> = {
  planned: {
    label: 'Planned',
    description: 'Scheduler accepted the job request or dry-run plan.',
  },
  approved_runtime: {
    label: 'Approved runtime',
    description: 'Schedule gates allowed the job to move into runtime execution.',
  },
  lock: {
    label: 'Lock',
    description: 'Single-run lock checks that prevent concurrent source/AOI jobs.',
  },
  search: {
    label: 'Search',
    description: 'Provider/catalog search for available source products.',
    relatedTab: 'Candidates',
  },
  select: {
    label: 'Select',
    description: 'Candidate filtering and scene selection.',
    relatedTab: 'Candidates',
  },
  download: {
    label: 'Download',
    description: 'Provider product download or retrieval.',
    relatedTab: 'Downloads',
  },
  prepare: {
    label: 'Prepare',
    description: 'COG preparation and manifest generation.',
    relatedTab: 'Logs',
  },
  composite: {
    label: 'Composite',
    description: 'Composite generation for AOI/date products.',
    relatedTab: 'Logs',
  },
  verify: {
    label: 'Verify',
    description: 'COG, manifest, and validation checks.',
    relatedTab: 'Verification',
  },
  upload: {
    label: 'Upload',
    description: 'Server-side object storage upload.',
    relatedTab: 'Logs',
  },
  stac: {
    label: 'STAC',
    description: 'Catalog item registration.',
    relatedTab: 'Logs',
  },
  ledger: {
    label: 'Ledger',
    description: 'Scheduler ledger persistence for operator audit.',
    relatedTab: 'Ledger',
  },
};

const FAILURE_KEYWORDS: Record<StageId, string[]> = {
  planned: ['plan', 'request'],
  approved_runtime: ['gate', 'gated', 'schedule', 'runtime', 'approval', 'not_due'],
  lock: ['lock', 'concurrent'],
  search: ['search', 'discover', 'provider', 'coverage', 'catalog_query'],
  select: ['select', 'candidate', 'reject', 'filter'],
  download: ['download', 'fetch', 'retrieve'],
  prepare: ['prepare', 'cog', 'manifest'],
  composite: ['composite', 'mosaic'],
  verify: ['verify', 'verification', 'validate', 'validation'],
  upload: ['upload', 'storage', 'object', 'minio', 's3'],
  stac: ['stac', 'catalog', 'pgstac'],
  ledger: ['ledger', 'sqlite', 'audit'],
};

const TERMINAL_FAILURE_STATES = new Set(['failed', 'validation_failed', 'cancelled']);
const RUNNING_STATES = new Set(['running']);
const SUSPENDED_STATES = new Set(['skipped_not_due', 'skipped_gated']);
const RAW_REFERENCE_PATTERN = /([A-Z]:\\|\\\\|\/(?:srv\/akasha|tmp|var\/tmp|data|mnt|home|root|etc)(?:\/|$)|(?:https?|s3|gs|file):\/\/)/i;

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = value.slice(0, 10);
  const time = value.slice(11, 19);
  return time ? `${date} ${time} UTC` : date;
}

function fmtCount(value: number | null | undefined): string {
  if (value == null) return '—';
  return value.toLocaleString();
}

function displayText(value: string | null | undefined, fallback: string): string {
  const text = value?.trim();
  if (!text) return fallback;
  if (RAW_REFERENCE_PATTERN.test(text)) {
    return 'Detail redacted by monitoring safeguards.';
  }
  return text;
}

function eventTypeOf(event: IngestionJobEvent): string {
  const compat = event as EventCompat;
  return compat.eventType ?? compat.event_type ?? '';
}

function latestEvent(
  events: IngestionJobEvent[] | undefined,
  predicate: (event: IngestionJobEvent) => boolean,
): IngestionJobEvent | undefined {
  if (!events?.length) return undefined;
  const matches = events.filter(predicate);
  return matches.length > 0 ? matches[matches.length - 1] : undefined;
}

function latestPlannedEvent(events: IngestionJobEvent[] | undefined): IngestionJobEvent | undefined {
  return latestEvent(events, (event) => {
    const compat = event as EventCompat;
    const type = eventTypeOf(event);
    return type === 'job_created' || type === 'dry_run_plan' || compat.stage === 'planned';
  });
}

function latestStatusEvent(events: IngestionJobEvent[] | undefined): IngestionJobEvent | undefined {
  return latestEvent(events, (event) => eventTypeOf(event) === 'status_change');
}

function hasRecordEntries(value: Record<string, unknown> | undefined): boolean {
  return Boolean(value && Object.keys(value).length > 0);
}

function artifactEvidence(job: IngestionJobDetail, needles: string[]): boolean {
  const haystack = Object.entries(job.artifactHandles ?? {})
    .map(([key, value]) => `${key} ${value}`)
    .join(' ')
    .toLowerCase();
  return needles.some((needle) => haystack.includes(needle));
}

function ledgerEvidence(job: IngestionJobDetail, needles: string[]): boolean {
  const rows = job.ledgerRows ?? [];
  if (rows.length === 0) return false;
  const haystack = rows
    .map((row) => Object.entries(row).map(([key, value]) => `${key} ${String(value)}`).join(' '))
    .join(' ')
    .toLowerCase();
  return needles.some((needle) => haystack.includes(needle));
}

function failureStage(job: IngestionJobDetail): StageId | undefined {
  const state = job.state.toLowerCase();
  if (state === 'blocked_by_lock') return 'lock';
  if (state === 'validation_failed') return 'verify';
  if (!TERMINAL_FAILURE_STATES.has(state) || !job.failureKind) return undefined;

  const failure = job.failureKind.toLowerCase();
  return PIPELINE_STAGE_ORDER.find((stageId) =>
    FAILURE_KEYWORDS[stageId].some((keyword) => failure.includes(keyword)),
  );
}

function stageHasEvidence(job: IngestionJobDetail, stageId: StageId): boolean {
  switch (stageId) {
    case 'planned':
      return Boolean(job.state);
    case 'approved_runtime':
      return Boolean(
        job.state
        && !SUSPENDED_STATES.has(job.state.toLowerCase())
        && job.state.toLowerCase() !== 'planned'
      );
    case 'search':
      return job.foundCount != null;
    case 'select':
      return job.selectedCount != null;
    case 'download':
      return job.downloadedCount != null;
    case 'prepare':
      return artifactEvidence(job, ['prepare', 'prepare_manifest', 'cog'])
        || ledgerEvidence(job, ['prepare', 'prepare_manifest', 'cog']);
    case 'composite':
      return artifactEvidence(job, ['composite', 'mosaic'])
        || ledgerEvidence(job, ['composite', 'mosaic']);
    case 'verify':
      return hasRecordEntries(job.verificationSummary);
    case 'upload':
      return artifactEvidence(job, ['upload', 'storage', 'object', 'bucket'])
        || ledgerEvidence(job, ['upload', 'storage', 'object', 'bucket']);
    case 'stac':
      return artifactEvidence(job, ['stac', 'catalog', 'pgstac', 'item'])
        || ledgerEvidence(job, ['stac', 'catalog', 'pgstac', 'item']);
    case 'ledger':
      return (job.ledgerRows ?? []).length > 0;
    case 'lock':
      return false;
    default:
      return false;
  }
}

function inferredMessage(job: IngestionJobDetail, stageId: StageId): string {
  switch (stageId) {
    case 'planned':
      return 'Plan inferred from job detail because no planned event was returned.';
    case 'approved_runtime':
      if (job.state.toLowerCase() === 'queued') {
        return 'Job queued; worker execution has not started.';
      }
      return SUSPENDED_STATES.has(job.state.toLowerCase())
        ? `Runtime not approved: ${job.state}.`
        : 'Runtime approval inferred from job state.';
    case 'search':
      return `Found candidates: ${fmtCount(job.foundCount)}.`;
    case 'select':
      return `Selected candidates: ${fmtCount(job.selectedCount)}.`;
    case 'download':
      return `Downloaded products: ${fmtCount(job.downloadedCount)}.`;
    case 'prepare':
      return 'Preparation evidence is present in sanitized artifact or ledger metadata.';
    case 'composite':
      return 'Composite evidence is present in sanitized artifact or ledger metadata.';
    case 'verify':
      return 'Verification summary is available.';
    case 'upload':
      return 'Upload evidence is present in sanitized artifact or ledger metadata.';
    case 'stac':
      return 'STAC/catalog evidence is present in sanitized artifact or ledger metadata.';
    case 'ledger':
      return `Ledger rows returned: ${fmtCount((job.ledgerRows ?? []).length)}.`;
    case 'lock':
      return 'Lock status is internal until lock telemetry is instrumented.';
    default:
      return 'No stage evidence is available.';
  }
}

function firstUnresolvedStage(stages: StageDisplay[]): StageId | undefined {
  return stages.find((stage) => stage.state === 'not_reached')?.id;
}

function deriveStages(job: IngestionJobDetail, events?: IngestionJobEvent[]): StageDisplay[] {
  const plannedEvent = latestPlannedEvent(events);
  const statusEvent = latestStatusEvent(events);
  const state = job.state.toLowerCase();
  const failedStage = failureStage(job);

  const stages = PIPELINE_STAGE_ORDER.map<StageDisplay>((stageId) => {
    const metadata = STAGE_LABELS[stageId];
    const matrix = STAGE_DATA_SOURCE_MATRIX[stageId];
    const base: StageDisplay = {
      id: stageId,
      label: metadata.label,
      description: metadata.description,
      relatedTab: metadata.relatedTab,
      state: 'not_reached',
      message: 'No reliable stage evidence yet.',
    };

    if (stageId === 'planned' && plannedEvent) {
      const compat = plannedEvent as EventCompat;
      return {
        ...base,
        state: 'succeeded',
        timestamp: compat.timestamp,
        message: displayText(compat.message, 'Planning event recorded.'),
      };
    }

    if (failedStage === stageId) {
      return {
        ...base,
        state: state === 'validation_failed' ? 'validation_failed' : 'failed',
        timestamp: job.finishedAt ?? job.updatedAt ?? (statusEvent as EventCompat | undefined)?.timestamp,
        message: displayText(job.failureKind, `${metadata.label} failed.`),
      };
    }

    if (matrix.kind === 'unavailable') {
      return {
        ...base,
        state: 'unavailable',
        message: matrix.note,
      };
    }

    if (stageHasEvidence(job, stageId)) {
      const statusCompat = statusEvent as EventCompat | undefined;
      const isQueuedApproval = stageId === 'approved_runtime' && state === 'queued';
      return {
        ...base,
        state: 'inferred',
        timestamp: isQueuedApproval
          ? (statusCompat?.timestamp ?? job.updatedAt ?? undefined)
          : (job.updatedAt ?? undefined),
        message: isQueuedApproval
          ? displayText(statusCompat?.message, inferredMessage(job, stageId))
          : inferredMessage(job, stageId),
      };
    }

    return base;
  });

  if (RUNNING_STATES.has(state)) {
    const runningStageId = firstUnresolvedStage(stages);
    const runningStage = stages.find((stage) => stage.id === runningStageId);
    if (runningStage) {
      const compat = statusEvent as EventCompat | undefined;
      runningStage.state = 'running';
      runningStage.timestamp = compat?.timestamp ?? job.startedAt ?? job.updatedAt ?? undefined;
      runningStage.message = displayText(
        compat?.message,
        'Job is running; per-stage instrumentation is not yet available.',
      );
    }
  }

  return stages;
}

type BadgeVariant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral' | 'nodata';

function stateVariant(state: PipelineStageState): BadgeVariant {
  if (state === 'succeeded') return 'success';
  if (state === 'running') return 'info';
  if (state === 'failed' || state === 'validation_failed') return 'destructive';
  if (state === 'inferred') return 'warning';
  if (state === 'unavailable') return 'nodata';
  return 'neutral';
}

function stateIcon(state: PipelineStageState) {
  if (state === 'succeeded') return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
  if (state === 'running') return <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
  if (state === 'failed' || state === 'validation_failed') {
    return <XCircle className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  if (state === 'inferred') return <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />;
  if (state === 'unavailable') return <CircleOff className="h-3.5 w-3.5" aria-hidden="true" />;
  return <CircleDashed className="h-3.5 w-3.5" aria-hidden="true" />;
}

function sourceIcon(kind: StageSourceKind) {
  if (kind === 'event-backed') return <Radio className="h-3.5 w-3.5" aria-hidden="true" />;
  if (kind === 'job-detail') return <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />;
  if (kind === 'artifact-ledger') return <Database className="h-3.5 w-3.5" aria-hidden="true" />;
  return <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />;
}

function stateLabel(state: PipelineStageState): string {
  return state.replace(/_/g, ' ');
}

function matrixVariant(kind: StageSourceKind): BadgeVariant {
  if (kind === 'event-backed') return 'success';
  if (kind === 'job-detail') return 'info';
  if (kind === 'artifact-ledger') return 'warning';
  return 'nodata';
}

export default function OrchestrationPipeline({
  job,
  events = [],
}: {
  job: IngestionJobDetail;
  events?: IngestionJobEvent[];
}) {
  const stages = deriveStages(job, events);
  const eventCount = events.length;
  const terminalState = job.state.toLowerCase();
  const hasTerminalFailure = TERMINAL_FAILURE_STATES.has(terminalState)
    || terminalState === 'blocked_by_lock';

  return (
    <div className="grid gap-5" data-testid="orchestration-pipeline">
      <section className="overflow-hidden rounded-xl border border-border/80 bg-card/90">
        <div className="border-b border-border/70 bg-background/40 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
                Admin · Internal operations
              </p>
              <h2 className="mt-1 flex items-center gap-2 text-lg font-semibold">
                <GitBranch className="h-4 w-4 text-info" aria-hidden="true" />
                Orchestration pipeline
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                Stage state is conservative: uninstrumented stages remain inferred,
                unavailable, or not reached instead of inheriting overall job success.
              </p>
            </div>
            <div className="flex flex-wrap gap-2" aria-label="Pipeline telemetry summary">
              <Badge variant={ eventCount > 0 ? 'info' : 'neutral' }>
                { eventCount.toLocaleString() } event{ eventCount === 1 ? '' : 's' }
              </Badge>
              <Badge variant={ hasTerminalFailure ? 'destructive' : 'neutral' }>
                { job.state }
              </Badge>
            </div>
          </div>
        </div>

        { hasTerminalFailure && (
          <div className="border-b border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <div className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>
                Terminal job state: <strong>{ job.state }</strong>
                { job.failureKind ? ` · ${displayText(job.failureKind, 'Failure kind recorded')}` : '' }
              </p>
            </div>
          </div>
        ) }

        <ol
          className="grid gap-3 p-4 lg:grid-cols-2 xl:grid-cols-3"
          aria-label="Ingestion orchestration pipeline stages"
        >
          { stages.map((stage, index) => {
            const matrix = STAGE_DATA_SOURCE_MATRIX[stage.id];
            return (
              <li
                key={ stage.id }
                className="relative rounded-xl border border-border/70 bg-background/60 p-4 shadow-sm"
                aria-label={ `${index + 1}. ${stage.label}: ${stateLabel(stage.state)}; ${matrix.label}` }
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-mono text-[11px] text-muted-foreground">
                      { String(index + 1).padStart(2, '0') } · { stage.id }
                    </p>
                    <h3 className="mt-1 text-base font-semibold">{ stage.label }</h3>
                  </div>
                  <Badge variant={ stateVariant(stage.state) } className="shrink-0 capitalize">
                    { stateIcon(stage.state) }
                    { stateLabel(stage.state) }
                  </Badge>
                </div>

                <p className="mt-2 text-sm text-muted-foreground">{ stage.description }</p>
                <p className="mt-3 text-sm">{ stage.message }</p>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Badge variant={ matrixVariant(matrix.kind) }>
                    { sourceIcon(matrix.kind) }
                    { matrix.shortLabel }
                  </Badge>
                  { stage.timestamp && (
                    <time
                      dateTime={ stage.timestamp }
                      className="text-xs text-muted-foreground"
                    >
                      { fmtDateTime(stage.timestamp) }
                    </time>
                  ) }
                  { stage.relatedTab && (
                    <span className="text-xs text-muted-foreground">
                      Related tab: { stage.relatedTab }
                    </span>
                  ) }
                </div>
              </li>
            );
          }) }
        </ol>
      </section>

      <section className="rounded-xl border border-border/70 bg-card/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              Stage data-source matrix
            </p>
            <h3 className="mt-1 text-sm font-semibold">Evidence contract</h3>
          </div>
          <Badge variant="outline">No raw paths or artifact values rendered</Badge>
        </div>

        <dl className="mt-4 grid gap-2 lg:grid-cols-2">
          { PIPELINE_STAGE_ORDER.map((stageId) => {
            const matrix = STAGE_DATA_SOURCE_MATRIX[stageId];
            return (
              <div
                key={ stageId }
                className="rounded-lg border border-border/60 bg-background/50 p-3"
              >
                <dt className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{ stageId }</span>
                  <Badge variant={ matrixVariant(matrix.kind) }>
                    { sourceIcon(matrix.kind) }
                    { matrix.label }
                  </Badge>
                </dt>
                <dd className="mt-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Fields:</span> { matrix.fields }.
                  {' '}
                  { matrix.note }
                </dd>
              </div>
            );
          }) }
        </dl>
      </section>
    </div>
  );
}
