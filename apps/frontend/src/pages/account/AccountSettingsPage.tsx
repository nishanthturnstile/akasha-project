import { useState } from 'react';
import { AlertTriangle, Check, RefreshCw, Save } from 'lucide-react';
import { useAccountMe, useAccountSettings, useUpdateAccountSettings } from '@/lib/queries';
import { ApiError } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

const DEFAULT_THRESHOLD = 20;

function settingsThreshold(settings: { opticalCloudThresholdPercent?: number | null } | null | undefined): number {
  const value = settings?.opticalCloudThresholdPercent;
  return Math.max(0, Math.min(70, Math.round(value ?? DEFAULT_THRESHOLD)));
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return 'We could not save your imagery quality preference.';
}

export default function AccountSettingsPage() {
  const accountQ = useAccountMe();
  const settingsQ = useAccountSettings();
  const updateSettings = useUpdateAccountSettings();
  const [draftThreshold, setDraftThreshold] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);

  const threshold = draftThreshold ?? settingsThreshold(settingsQ.data);

  const valid = Number.isInteger(threshold) && threshold >= 0 && threshold <= 70;
  const save = () => {
    if (!valid) return;
    updateSettings.mutate(
      { opticalCloudThresholdPercent: threshold },
      {
        onSuccess: () => {
          setDraftThreshold(null);
          setDirty(false);
        },
      },
    );
  };

  const account = accountQ.data;
  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="account-settings-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Account</p>
        <h1 className="mt-1 text-2xl font-semibold">Account settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          { account ? `${account.user.email} · ${account.currentTeam.name}` : 'Loading account...' }
        </p>
        { account?.authMode === 'dev' && (
          <p className="mt-3 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
            Local development auth is active. Enable AUTH_MODE before customer data is used.
          </p>
        ) }
      </section>
      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Imagery</p>
            <h2 className="mt-1 text-lg font-semibold">Imagery quality</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Set the single field imagery quality limit for combined cloud, cirrus, and shadow
              coverage. It determines which acquisitions qualify for analysis, but never changes
              ingestion or how imagery is collected.
            </p>
          </div>
          <output
            htmlFor="imagery-quality-threshold"
            className="rounded-pill border border-primary/20 bg-primary/10 px-3 py-1 font-mono text-lg font-semibold tabular-nums text-primary"
            data-testid="imagery-quality-value"
          >
            { threshold }%
          </output>
        </div>

        { settingsQ.isError && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
            <span className="flex items-center gap-2"><AlertTriangle className="size-4" /> Unable to load imagery settings.</span>
            <Button variant="outline" size="sm" onClick={ () => void settingsQ.refetch() }>
              <RefreshCw className="size-4" /> Retry
            </Button>
          </div>
        )}

        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
              <label htmlFor="imagery-quality-threshold" className="text-sm font-medium">
              Combined cloud + cirrus + shadow threshold
            </label>
            <p id="imagery-quality-threshold-help" className="mt-1 text-xs text-muted-foreground">
              0% is strictest and 70% keeps more marginal acquisitions visible.
            </p>
          </div>
          <span className="font-mono text-xs tabular-nums text-muted-foreground">0–70%</span>
        </div>
        <Slider
          id="imagery-quality-threshold"
          value={ [threshold] }
          min={ 0 }
          max={ 70 }
          step={ 1 }
          onValueChange={ ([value]) => {
            if (value == null) return;
            setDraftThreshold(value);
            setDirty(true);
            updateSettings.reset();
          } }
          aria-label="Imagery quality threshold"
          aria-describedby="imagery-quality-threshold-help"
          className="mt-4"
          data-testid="imagery-quality-slider"
        />
        { !valid && (
          <p className="mt-2 text-sm text-destructive" role="alert">Enter a whole percentage from 0 to 70.</p>
        ) }
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            onClick={ save }
            disabled={ !valid || !dirty || updateSettings.isPending }
            data-testid="imagery-quality-save"
          >
            <Save className="size-4" /> { updateSettings.isPending ? 'Saving…' : 'Save' }
          </Button>
          { updateSettings.isSuccess && !dirty && (
            <span className="flex items-center gap-1.5 text-sm text-success" role="status" data-testid="imagery-quality-saved">
              <Check className="size-4" /> Saved
            </span>
          ) }
          { updateSettings.isError && (
            <span className="flex flex-wrap items-center gap-2 text-sm text-destructive" role="alert" data-testid="imagery-quality-error">
              { errorMessage(updateSettings.error) }
              <Button variant="outline" size="sm" onClick={ save } disabled={ !valid || updateSettings.isPending }>
                <RefreshCw className="size-4" /> Retry
              </Button>
            </span>
          ) }
        </div>
      </section>
      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Team memberships</h2>
        { account?.memberships.map((membership) => (
          <p key={ membership.teamId } className="mt-2 text-sm text-muted-foreground">
            { membership.teamName } — { membership.role }
          </p>
        )) }
      </section>
    </main>
  );
}
