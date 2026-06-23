import { Map as MapIcon, Pencil, Sparkles } from 'lucide-react';
import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import MapPage from '@/pages/MapPage';
import FieldAnalyticsPanel from '@/components/analytics/FieldAnalyticsPanel';
import { useConfig, useFields } from '@/lib/queries';
import { useMapView } from '@/state/useMapView';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions } from '@/types/api';

function formatAreaHa(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)} ha`;
}

export default function FieldAnalyticsPage() {
  const { selectedPlotId, clearSelectedPlot, cloudMask, periodFrom, periodTo, activeSourceId, overlaysVisible } = useMapView();
  const fieldsQ = useFields();
  const configQ = useConfig();

  const selectedField = useMemo(() => {
    if (!selectedPlotId || !fieldsQ.data) return null;
    return fieldsQ.data.find((f) => f.id === selectedPlotId) ?? null;
  }, [fieldsQ.data, selectedPlotId]);

  const effectiveSourceId = activeSourceId ?? undefined;
  const supportedIndices = configQ.data?.supportedIndices ?? ['NDVI'];

  return (
    <div className="flex h-full flex-col gap-4 p-4 min-h-0">
      {/* Field info header card */}
      <div className="shrink-0 flex items-center justify-between rounded-md border border-border bg-background px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={ () => clearSelectedPlot() }
            disabled={ !selectedField }
            aria-label="Back to all fields"
            className="flex size-8 items-center justify-center rounded-md text-foreground/80 hover:bg-accent/60 disabled:opacity-30"
          >
            <span aria-hidden="true" className="text-base leading-none">←</span>
          </button>
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-primary/40 bg-primary/10 text-primary">
            <MapIcon className="size-4" strokeWidth={ 1.75 } />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-sm font-semibold text-foreground">
                { selectedField?.name ?? 'No field selected' }
              </span>
              { selectedField && (
                <span className="rounded border border-border/60 px-1.5 py-0.5 font-mono text-[11px] font-medium text-foreground/80">
                  { formatAreaHa(selectedField.areaHa) }
                </span>
              ) }
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={ !selectedField }
            className="h-8 gap-1.5 text-[12px]"
          >
            <Pencil className="size-3.5" strokeWidth={ 1.75 } />
            Edit
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled
            className="h-8 gap-1.5 text-[12px]"
          >
            <Sparkles className="size-3.5" strokeWidth={ 1.75 } />
            Overview
          </Button>
        </div>
      </div>

      {/* Map card — flex-1 when global view (full height), flex-[13] when analytics visible */}
      <div className={cn('min-h-0 rounded-md border border-border overflow-hidden', overlaysVisible ? 'flex-[13]' : 'flex-1')}>
        <MapPage hideFieldHeader hidePlotToolbar simplifiedMapControls topLeftCoords />
      </div>

      {/* Analytics panel card — only when field selected and not in global view */}
      {selectedField && overlaysVisible && (
        <div className="min-h-0 flex-[7] rounded-md border border-border bg-background">
          <FieldAnalyticsPanel
            field={selectedField}
            sourceId={effectiveSourceId}
            indices={supportedIndices}
            cloudMask={cloudMask as CloudMaskOptions}
            periodFrom={periodFrom}
            periodTo={periodTo}
          />
        </div>
      )}
    </div>
  );
}
