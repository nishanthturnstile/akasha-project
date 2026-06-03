import { AlertTriangle, CheckCircle2, RefreshCw, Satellite } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DisplayModeToggle } from '@/components/layers/DisplayModeToggle';
import type { FieldSceneListResponse, Plot } from '@/types/api';

interface FieldSceneStatusPanelProps {
  selectedPlot: Plot | null;
  response: FieldSceneListResponse | undefined;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onSync: () => void;
  syncing: boolean;
  displayModes: string[];
  displayMode: string;
  onDisplayModeChange: (mode: string) => void;
}

export function FieldSceneStatusPanel({
  selectedPlot,
  response,
  loading,
  error,
  onRetry,
  onSync,
  syncing,
  displayModes,
  displayMode,
  onDisplayModeChange,
}: FieldSceneStatusPanelProps) {
  if (!selectedPlot) return null;

  const isSynced =
    selectedPlot.externalProvider === 'eos' &&
    selectedPlot.externalFieldId &&
    selectedPlot.providerSyncStatus === 'synced';
  const hasFieldScenes = response?.scope === 'field' && response.scenes.length > 0;
  const fallbackReason = response?.scope === 'global_fallback' ? response.fallbackReason : null;

  return (
    <section
      className="glass flex w-[300px] flex-col gap-3 rounded-md p-3"
      data-testid="field-scene-status"
      aria-label="Selected field scenes"
    >
      <div className="flex items-start gap-2">
        <Satellite className="mt-0.5 size-4 shrink-0 text-primary" strokeWidth={ 1.75 } />
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-foreground">
            { selectedPlot.name }
          </p>
          <p className="text-[11px] text-muted-foreground">
            { hasFieldScenes ? `${response.scenes.length} field scenes` : 'Field-aware monitoring' }
          </p>
        </div>
      </div>

      { isSynced ? (
        <div className="flex items-center gap-1.5 text-[12px] text-success" data-testid="field-sync-ok">
          <CheckCircle2 className="size-3.5" strokeWidth={ 1.75 } />
          Synced to provider
        </div>
      ) : (
        <Button
          variant="primary"
          size="sm"
          onClick={ onSync }
          disabled={ syncing }
          data-testid="field-sync-button"
        >
          <RefreshCw className="size-4" strokeWidth={ 1.75 } />
          { syncing ? 'Syncing' : 'Sync field' }
        </Button>
      ) }

      { loading && (
        <p className="text-[12px] text-muted-foreground" data-testid="field-scenes-loading">
          Loading field scenes...
        </p>
      ) }

      { error && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-[12px] text-destructive"
          data-testid="field-scenes-error"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" strokeWidth={ 1.75 } />
          <span className="min-w-0 flex-1">{ error }</span>
          <button type="button" className="font-medium underline" onClick={ onRetry }>
            Retry
          </button>
        </div>
      ) }

      { fallbackReason && !error && (
        <p
          className="rounded-md border border-warning/30 bg-warning/10 px-2 py-1.5 text-[12px] text-warning"
          data-testid="field-scenes-fallback"
        >
          { fallbackReason }
        </p>
      ) }

      { hasFieldScenes && displayModes.length > 1 && (
        <div className="flex flex-col gap-1.5" data-testid="field-display-modes">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Display
          </span>
          <DisplayModeToggle
            modes={ displayModes }
            value={ displayMode }
            onChange={ onDisplayModeChange }
          />
        </div>
      ) }
    </section>
  );
}
