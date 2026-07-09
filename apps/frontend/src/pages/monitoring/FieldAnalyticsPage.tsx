import { Map as MapIcon, Pencil } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { AddFieldDropdown } from '@/components/fields/AddFieldDropdown';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';
import MapPage from '@/pages/MapPage';
import { IndexPanel } from '@/components/scaffold/IndexPanel';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import { useConfig, useDates, useDeleteField, useFields, useSources, useUpdateField } from '@/lib/queries';
import { useMapView } from '@/state/useMapView';
import { useSeasonContext } from '@/state/seasonContext';
import type { CloudMaskOptions, Source } from '@/types/api';

function formatAreaHa(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)} ha`;
}

function maskOptionsForSource(source: Source | null | undefined): Array<keyof CloudMaskOptions> {
  return source?.availableMaskOptions ?? ['clouds', 'cloudShadows', 'cirrus'];
}

function sanitizeCloudMaskForSource(
  value: CloudMaskOptions,
  source: Source | null | undefined,
): CloudMaskOptions {
  const available = new Set(maskOptionsForSource(source));
  return {
    clouds: available.has('clouds') ? value.clouds : false,
    cloudShadows: available.has('cloudShadows') ? value.cloudShadows : false,
    cirrus: available.has('cirrus') ? value.cirrus : false,
  };
}

function defaultDisplayModeForSource(source: Source | null | undefined, fallback: string): string {
  return (
    source?.defaultMapDisplayMode ??
    source?.defaultDisplayMode ??
    source?.mapDisplayModes?.[0] ??
    source?.displayModes?.[0] ??
    fallback
  );
}

export default function FieldAnalyticsPage() {
  const navigate = useNavigate();
  const { selectedPlotId, clearSelectedPlot, cloudMask, periodFrom, periodTo, activeSourceId, selectedDate: dateOverride, displayMode, overlaysVisible, mapFullscreen } = useMapView();
  const fieldsQ = useFields();
  const configQ = useConfig();
  const sourcesQ = useSources();
  const updateField = useUpdateField();
  const deleteField = useDeleteField();
  const { seasonId } = useSeasonContext();
  const [editFieldOpen, setEditFieldOpen] = useState(false);
  const [savingField, setSavingField] = useState(false);

  const selectedField = useMemo(() => {
    if (!selectedPlotId || !fieldsQ.data) return null;
    return fieldsQ.data.find((f) => f.id === selectedPlotId) ?? null;
  }, [fieldsQ.data, selectedPlotId]);

  const effectiveSourceId = activeSourceId ?? sourcesQ.data?.[0]?.id;
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((source) => source.id === effectiveSourceId) ?? null,
    [sourcesQ.data, effectiveSourceId],
  );
  const datesQ = useDates(effectiveSourceId);
  const selectedDate = useMemo(() => {
    if (!datesQ.data || !configQ.data) return null;
    if (dateOverride && datesQ.data.some((entry) => entry.acquisitionDate === dateOverride)) {
      return dateOverride;
    }
    return selectDefaultDate(datesQ.data, configQ.data.usablePixelThresholdPercent, {
      sourceKind: selectedSource?.kind,
    })?.acquisitionDate ?? null;
  }, [configQ.data, dateOverride, datesQ.data, selectedSource?.kind]);
  const supportedIndices = selectedSource?.supportedIndices ?? configQ.data?.supportedIndices ?? ['NDVI'];
  const activeDisplayMode = displayMode ?? defaultDisplayModeForSource(
    selectedSource,
    configQ.data?.defaultIndex ?? 'NDVI',
  );
  const effectiveCloudMask = sanitizeCloudMaskForSource(
    cloudMask as CloudMaskOptions,
    selectedSource,
  );

  const seasonFields = useMemo(() => {
    if (!fieldsQ.data || !seasonId) return fieldsQ.data ?? [];
    return fieldsQ.data.filter((f) => f.seasonIds?.includes(seasonId)) ?? [];
  }, [fieldsQ.data, seasonId]);

  return (
    <div className="h-full flex flex-col gap-4 p-4 min-h-0">
      {overlaysVisible && (
      <div className="flex items-stretch rounded-md border border-border bg-background">
        <div className="flex items-center gap-3 px-4 py-3 min-w-0 flex-1">
          <button
            type="button"
            onClick={ () => clearSelectedPlot() }
            disabled={ !selectedField }
            aria-label="Back to all fields"
            className="flex size-8 items-center justify-center rounded-md text-foreground/80 hover:bg-accent/60 disabled:opacity-30"
          >
            <span aria-hidden="true" className="text-base leading-none">←</span>
          </button>

          <div className="w-px self-stretch bg-border/60" />

          <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-primary/40 bg-primary/10 text-primary">
            <MapIcon className="size-4" strokeWidth={ 1.75 } />
          </div>

          <div className="w-px self-stretch bg-border/60" />

          <span className="font-display text-sm font-semibold text-foreground">
            { selectedField?.name ?? 'No field selected' }
          </span>

          { selectedField && (
            <>
              <div className="w-px self-stretch bg-border/60" />
              <span className="rounded border border-border/60 px-1.5 py-0.5 font-mono text-[11px] font-medium text-foreground/80">
                { formatAreaHa(selectedField.areaHa) }
              </span>
            </>
          ) }

          <div className="w-px self-stretch bg-border/60" />

          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={ !selectedField }
            onClick={ () => setEditFieldOpen(true) }
            className="h-8 gap-1.5 text-[12px]"
          >
            <Pencil className="size-3.5" strokeWidth={ 1.75 } />
            Edit
          </Button>
        </div>
        <div className="flex items-center gap-2 px-4 py-3">
          <AddFieldDropdown
            fields={ seasonFields }
            onNavigate={ navigate }
            defaultSeasonId={ seasonId }
            testId="analytics-add-field"
          />
        </div>
      </div>
      )}

      {/* Map card */}
      <div className={cn('rounded-md border border-border overflow-hidden', overlaysVisible && !mapFullscreen ? 'h-[50vh] min-h-[300px]' : 'flex-1 min-h-0')}>
        <MapPage hidePlotToolbar simplifiedMapControls topLeftCoords showFullscreen />
      </div>

      {/* Analytics panel */}
      {selectedField && overlaysVisible && !mapFullscreen && (
        <div className="rounded-md border border-border bg-background">
          <IndexPanel
            className="w-full max-w-none rounded-none border-0 bg-transparent shadow-none"
            selectedPlot={selectedField}
            selectedDate={selectedDate}
            sourceId={effectiveSourceId}
            displayMode={activeDisplayMode}
            supportedIndices={supportedIndices}
            cloudMask={effectiveCloudMask}
            sourceMaskMethod={selectedSource?.maskMethod ?? null}
            sourceMetricsProvisional={selectedSource?.metricsProvisional ?? false}
            periodFrom={periodFrom}
            periodTo={periodTo}
            vegetationData={selectedField?.vegetationData}
          />
        </div>
      )}

      {selectedField && (
        <EditFieldDialog
          key={selectedField.id}
          field={selectedField}
          open={editFieldOpen}
          onOpenChange={setEditFieldOpen}
          onSave={(fieldId, name, geometry, vegetationData, groupId) => {
            setSavingField(true);
            updateField.mutate(
              { fieldId, payload: { name, ...(geometry ? { geometry } : {}), ...(vegetationData ? { vegetationData } : {}), ...(groupId !== undefined ? { groupId } : {}) } },
              { onSuccess: () => { setSavingField(false); setEditFieldOpen(false); }, onError: () => setSavingField(false) },
            );
          }}
          saving={savingField}
          onDelete={(fieldId) => deleteField.mutateAsync(fieldId)}
        />
      )}

    </div>
  );
}
