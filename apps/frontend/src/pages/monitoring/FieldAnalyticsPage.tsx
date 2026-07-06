import { Map as MapIcon, Pencil } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { AddFieldDropdown } from '@/components/fields/AddFieldDropdown';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';
import MapPage from '@/pages/MapPage';
import FieldAnalyticsPanel from '@/components/analytics/FieldAnalyticsPanel';
import { useConfig, useDates, useDeleteField, useFields, useSources, useUpdateField } from '@/lib/queries';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import { selectEffectiveSourceId } from '@/lib/sourceSelection';
import { useMapView } from '@/state/useMapView';
import { useSeasonContext } from '@/state/seasonContext';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions } from '@/types/api';

function formatAreaHa(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)} ha`;
}

export default function FieldAnalyticsPage() {
  const { selectedPlotId, setSelectedPlotId, setFocusNonce, clearSelectedPlot, cloudMask, periodFrom, periodTo, activeSourceId, selectedDate, displayMode, overlaysVisible, mapFullscreen } = useMapView();
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

  const seasonFields = useMemo(() => {
    if (!seasonId) return fieldsQ.data ?? [];
    return (fieldsQ.data ?? []).filter((f) => f.seasonIds?.includes(seasonId));
  }, [fieldsQ.data, seasonId]);

  const effectiveSourceId = useMemo(
    () => selectEffectiveSourceId({
      activeSourceId,
      defaultSourceId: configQ.data?.defaultSourceId,
      sources: sourcesQ.data,
    }),
    [activeSourceId, configQ.data?.defaultSourceId, sourcesQ.data],
  );
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((source) => source.id === effectiveSourceId),
    [effectiveSourceId, sourcesQ.data],
  );
  const datesQ = useDates(effectiveSourceId);
  const effectiveSelectedDate = useMemo(() => {
    if (!datesQ.data || !configQ.data) return selectedDate ?? null;
    if (selectedDate && datesQ.data.some((d) => d.acquisitionDate === selectedDate)) {
      return selectedDate;
    }
    return selectDefaultDate(datesQ.data, configQ.data.usablePixelThresholdPercent, {
      sourceKind: selectedSource?.kind,
    })?.acquisitionDate ?? null;
  }, [configQ.data, datesQ.data, selectedDate, selectedSource?.kind]);
  const supportedIndices = selectedSource?.supportedIndices ?? configQ.data?.supportedIndices ?? ['NDVI'];

  const navigate = useNavigate();
  const navigateWithImageryState = useCallback((path: string) => {
    const [pathname, query = ''] = path.split('?');
    const params = new URLSearchParams(query);
    if (effectiveSourceId && !params.has('source')) params.set('source', effectiveSourceId);
    if (selectedDate && !params.has('scene')) params.set('scene', selectedDate);
    if (periodFrom && !params.has('from')) params.set('from', periodFrom);
    if (periodTo && !params.has('to')) params.set('to', periodTo);
    if (displayMode && !params.has('layer')) params.set('layer', displayMode);
    const search = params.toString();
    navigate(search ? `${pathname}?${search}` : pathname);
  }, [displayMode, effectiveSourceId, navigate, periodFrom, periodTo, selectedDate]);

  return (
    <div className="flex h-full flex-col gap-4 p-4 min-h-0">
      { overlaysVisible && (
        <div className="shrink-0 flex items-stretch rounded-md border border-border bg-background">
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
              onNavigate={ navigateWithImageryState }
              onSelectField={ (fieldId) => { setSelectedPlotId(fieldId); setFocusNonce(Date.now()); } }
              defaultSeasonId={ seasonId }
            />
          </div>
        </div>
      ) }

      {/* Map card — flex-1 when fullscreen/global, flex-[13] when analytics visible */ }
      <div className={ cn('min-h-0 rounded-md border border-border overflow-hidden', overlaysVisible && !mapFullscreen ? 'flex-[13]' : 'flex-1') }>
        <MapPage hidePlotToolbar simplifiedMapControls topLeftCoords />
      </div>

      {/* Analytics panel card — hidden when mapFullscreen is active */ }
      { selectedField && overlaysVisible && !mapFullscreen && (
        <div className="min-h-0 flex-[7] rounded-md border border-border bg-background">
          <FieldAnalyticsPanel
            field={ selectedField }
            sourceId={ effectiveSourceId }
            indices={ supportedIndices }
            selectedDate={ effectiveSelectedDate }
            displayMode={ displayMode }
            cloudMask={ cloudMask as CloudMaskOptions }
            periodFrom={ periodFrom }
            periodTo={ periodTo }
          />
        </div>
      ) }

      { selectedField && (
        <EditFieldDialog
          key={ selectedField.id }
          field={ selectedField }
          open={ editFieldOpen }
          onOpenChange={ setEditFieldOpen }
          onSave={ (fieldId, name, geometry, vegetationData, groupId) => {
            setSavingField(true);
            updateField.mutate(
              { fieldId, payload: { name, ...(geometry ? { geometry } : {}), ...(vegetationData ? { vegetationData } : {}), ...(groupId !== undefined ? { groupId } : {}) } },
              { onSuccess: () => { setSavingField(false); setEditFieldOpen(false); }, onError: () => setSavingField(false) },
            );
          } }
          saving={ savingField }
          onDelete={ (fieldId) => deleteField.mutateAsync(fieldId) }
        />
      ) }
    </div>
  );
}
