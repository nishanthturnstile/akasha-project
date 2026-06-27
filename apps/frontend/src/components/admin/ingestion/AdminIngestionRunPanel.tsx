import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Loader2, PlayCircle } from 'lucide-react';
import { ApiError } from '@/lib/api';
import { useTriggerIngestionJob } from '@/lib/queries';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type {
  IngestionScheduleItem,
  TriggerIngestionJobRequest,
  TriggerIngestionJobResponse,
} from '@/types/api';

interface RunTarget {
  sourceId: string;
  aoiId?: string | null;
}

interface AdminIngestionRunPanelProps {
  schedules: IngestionScheduleItem[];
  prefill?: RunTarget | null;
  liveTriggerEnabled?: boolean;
}

const WINDOW_DAY_OPTIONS = [12, 30, 45] as const;
const LIVE_ACKNOWLEDGMENT = 'LIVE CANARY';

function uniq(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.map((value) => value?.trim()).filter(Boolean) as string[]))
    .sort((a, b) => a.localeCompare(b));
}

function scheduleLabel(schedule: IngestionScheduleItem): string {
  const parts = [schedule.sourceId];
  if (schedule.provider) parts.push(schedule.provider);
  if (!schedule.scheduleEnabled) parts.push('not enabled');
  return parts.join(' · ');
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'Unable to submit the ingestion request.';
}

function firstAoiForSource(schedules: IngestionScheduleItem[], sourceId: string): string {
  return schedules.find((schedule) => schedule.sourceId === sourceId)?.aoiId ?? 'bangalore-60km';
}

function initialSourceId(prefill: RunTarget | null | undefined, sourceOptions: IngestionScheduleItem[]): string {
  return prefill?.sourceId ?? sourceOptions[0]?.sourceId ?? '';
}

function initialAoiId(
  prefill: RunTarget | null | undefined,
  sourceOptions: IngestionScheduleItem[],
  schedules: IngestionScheduleItem[],
): string {
  if (prefill?.aoiId) return prefill.aoiId;
  const sourceId = initialSourceId(prefill, sourceOptions);
  if (sourceId) return firstAoiForSource(schedules, sourceId);
  return sourceOptions[0]?.aoiId ?? 'bangalore-60km';
}

export default function AdminIngestionRunPanel({
  schedules,
  prefill,
  liveTriggerEnabled = false,
}: AdminIngestionRunPanelProps) {
  const trigger = useTriggerIngestionJob();
  const sourceOptions = useMemo(() => {
    const seen = new Set<string>();
    return schedules.filter((schedule) => {
      if (seen.has(schedule.sourceId)) return false;
      seen.add(schedule.sourceId);
      return true;
    });
  }, [schedules]);
  const [sourceId, setSourceId] = useState(() => initialSourceId(prefill, sourceOptions));
  const [aoiId, setAoiId] = useState(() => initialAoiId(prefill, sourceOptions, schedules));
  const [dryRun, setDryRun] = useState(true);
  const [windowDays, setWindowDays] = useState<number>(12);
  const [maxDownloads, setMaxDownloads] = useState<number>(1);
  const [notes, setNotes] = useState('');
  const [liveChecked, setLiveChecked] = useState(false);
  const [liveAck, setLiveAck] = useState('');
  const [lastResponse, setLastResponse] = useState<TriggerIngestionJobResponse | null>(null);

  const aoiOptions = useMemo(() => {
    const fromSource = uniq(
      schedules
        .filter((schedule) => !sourceId || schedule.sourceId === sourceId)
        .map((schedule) => schedule.aoiId),
    );
    return fromSource.length > 0 ? fromSource : uniq(schedules.map((schedule) => schedule.aoiId));
  }, [schedules, sourceId]);
  const selectedAoiId = aoiOptions.includes(aoiId) ? aoiId : aoiOptions[0] ?? aoiId;

  const isLiveMode = !dryRun;
  const liveAcknowledged = liveChecked && liveAck.trim() === LIVE_ACKNOWLEDGMENT;
  const canSubmit = Boolean(sourceId && selectedAoiId) && (!isLiveMode || liveAcknowledged) && !trigger.isPending;

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload: TriggerIngestionJobRequest = {
      sourceId,
      aoiId: selectedAoiId,
      dryRun,
      confirmLive: isLiveMode && liveAcknowledged,
      windowDays,
      maxDownloads,
      notes: notes.trim(),
    };
    try {
      const response = await trigger.mutateAsync(payload);
      setLastResponse(response);
    } catch {
      setLastResponse(null);
    }
  };

  return (
    <section className="overflow-hidden rounded-2xl border border-emerald-400/25 bg-card/95 shadow-[0_18px_60px_rgba(10,44,35,0.20)]">
      <div className="border-b border-border/70 bg-linear-to-r from-emerald-500/15 via-card to-amber-500/10 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-emerald-300">Admin trigger</p>
            <h2 className="mt-1 flex items-center gap-2 text-xl font-semibold">
              <PlayCircle className="h-5 w-5 text-emerald-300" aria-hidden="true" />
              Run one ingestion source
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Submit a bounded request to the staging runner inbox. Dry run is the safe default.
            </p>
          </div>
          <Badge variant={ liveTriggerEnabled ? 'warning' : 'success' }>
            { liveTriggerEnabled ? 'Live canary available' : 'Dry-run only' }
          </Badge>
        </div>
      </div>

      <form className="grid gap-4 p-4 lg:grid-cols-[1.2fr_0.8fr]" onSubmit={ onSubmit }>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Source</span>
            <select
              value={ sourceId }
              onChange={ (event) => {
                const next = event.target.value;
                const first = schedules.find((schedule) => schedule.sourceId === next);
                setSourceId(next);
                setAoiId(first?.aoiId ?? 'bangalore-60km');
                setLastResponse(null);
              } }
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              aria-label="Ingestion source"
            >
              { sourceOptions.map((schedule) => (
                <option
                  key={ `${schedule.sourceId}:${schedule.aoiId ?? 'global'}` }
                  value={ schedule.sourceId }
                >
                  { scheduleLabel(schedule) }
                </option>
              )) }
            </select>
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">AOI</span>
            <select
              value={ selectedAoiId }
              onChange={ (event) => {
                setAoiId(event.target.value);
                setLastResponse(null);
              } }
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              aria-label="Ingestion AOI"
            >
              { aoiOptions.map((option) => (
                <option key={ option } value={ option }>{ option }</option>
              )) }
            </select>
          </label>

          <fieldset className="rounded-xl border border-border/70 p-3 sm:col-span-2">
            <legend className="px-1 text-sm font-medium">Mode</legend>
            <div className="mt-1 flex flex-wrap gap-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-sm">
                <input
                  type="radio"
                  name="ingestion-mode"
                  checked={ dryRun }
                  onChange={ () => {
                    setDryRun(true);
                    setLastResponse(null);
                  } }
                />
                Dry run
              </label>
              { liveTriggerEnabled && (
                <label className="flex cursor-pointer items-center gap-2 rounded-full border border-amber-400/50 bg-amber-500/10 px-3 py-2 text-sm">
                  <input
                    type="radio"
                    name="ingestion-mode"
                    checked={ !dryRun }
                    onChange={ () => {
                      setDryRun(false);
                      setLastResponse(null);
                    } }
                  />
                  Live canary
                </label>
              ) }
            </div>
          </fieldset>

          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Window days</span>
            <select
              value={ windowDays }
              onChange={ (event) => setWindowDays(Number(event.target.value)) }
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              aria-label="Ingestion window days"
            >
              { WINDOW_DAY_OPTIONS.map((option) => (
                <option key={ option } value={ option }>{ option }</option>
              )) }
            </select>
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Max downloads</span>
            <input
              type="number"
              min={ 1 }
              max={ 20 }
              value={ maxDownloads }
              onChange={ (event) => setMaxDownloads(Number(event.target.value)) }
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              aria-label="Max downloads"
            />
          </label>

          <label className="grid gap-1.5 text-sm sm:col-span-2">
            <span className="font-medium">Operator notes</span>
            <input
              type="text"
              maxLength={ 500 }
              value={ notes }
              onChange={ (event) => setNotes(event.target.value) }
              placeholder="Why this manual run is needed…"
              className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              aria-label="Operator notes"
            />
          </label>
        </div>

        <div className="flex flex-col justify-between gap-3 rounded-xl border border-border/70 bg-background/60 p-3">
          { isLiveMode ? (
            <div className="rounded-lg border border-amber-400/50 bg-amber-500/10 p-3 text-sm">
              <div className="flex gap-2 font-medium text-amber-100">
                <AlertTriangle className="mt-0.5 h-4 w-4" aria-hidden="true" />
                Live canary confirmation
              </div>
              <label className="mt-3 flex items-start gap-2 text-muted-foreground">
                <input
                  type="checkbox"
                  checked={ liveChecked }
                  onChange={ (event) => setLiveChecked(event.target.checked) }
                  aria-label="Confirm live ingestion side effects"
                />
                <span>I understand this can download data and update staging ingestion state.</span>
              </label>
              <label className="mt-3 grid gap-1 text-muted-foreground">
                <span>Type { LIVE_ACKNOWLEDGMENT } to continue</span>
                <input
                  value={ liveAck }
                  onChange={ (event) => setLiveAck(event.target.value) }
                  className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  aria-label="Live canary acknowledgment"
                />
              </label>
            </div>
          ) : (
            <p className="rounded-lg border border-emerald-400/35 bg-emerald-500/10 p-3 text-sm text-emerald-100">
              Dry run is selected. The backend will submit a planning request without live downloads.
            </p>
          ) }

          { trigger.error && (
            <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
              { safeErrorMessage(trigger.error) }
            </p>
          ) }

          { lastResponse && (
            <div
              role="status"
              className={
                lastResponse.status === 'submitted'
                  ? 'rounded-md border border-emerald-400/40 bg-emerald-500/10 p-3 text-sm text-emerald-100'
                  : 'rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100'
              }
            >
              <div className="flex items-center gap-2 font-medium">
                { lastResponse.status === 'submitted' ? (
                  <>
                    <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                    Submitted — waiting for staging runner pickup
                  </>
                ) : (
                  <>
                    <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                    { lastResponse.message || 'Ingestion trigger is not currently available.' }
                  </>
                ) }
              </div>
              <div className="mt-2 flex flex-wrap gap-3">
                <Link className="underline underline-offset-4" to={ lastResponse.jobsUrl }>
                  View filtered jobs
                </Link>
                <Link className="underline underline-offset-4" to="/admin/ingestion/jobs">
                  All ingestion jobs
                </Link>
              </div>
            </div>
          ) }

          <Button type="submit" disabled={ !canSubmit } className="w-full justify-center">
            { trigger.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> }
            Submit ingestion request
          </Button>
        </div>
      </form>
    </section>
  );
}
