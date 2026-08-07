import { Pencil } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import { AddFieldDropdown } from '@/components/fields/AddFieldDropdown';
import { FieldThumbnail, getLastFieldPerSeason, setLastFieldForSeason } from '@/components/fields/GlobalViewPanel';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';
import MapPage from '@/pages/MapPage';
import { IndexPanel } from '@/components/scaffold/IndexPanel';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import { selectEffectiveSourceId } from '@/lib/sourceSelection';
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
  const {
    selectedPlotId,
    setSelectedPlotId,
    clearSelectedPlot,
    setFocusNonce,
    cloudMask,
    periodFrom,
    periodTo,
    activeSourceId,
    selectedDate: dateOverride,
    displayMode,
    overlaysVisible,
    mapFullscreen,
    radarEvidenceVisible,
    setRadarEvidenceVisible,
    setMapFullscreen,
    setGlobalViewOpen,
    setOverlaysVisible,
  } = useMapView();

  const prevPlotId = useRef<string | null>(null);
  useEffect(() => {
    if (selectedPlotId && selectedPlotId !== prevPlotId.current) {
      prevPlotId.current = selectedPlotId;
      setMapFullscreen(false);
    }
  }, [selectedPlotId, setMapFullscreen]);

  const fieldsQ = useFields();
  const configQ = useConfig();
  const sourcesQ = useSources();
  const updateField = useUpdateField();
  const deleteField = useDeleteField();
  const { seasonId } = useSeasonContext();
  const [editFieldOpen, setEditFieldOpen] = useState(false);
  const [initialVegSeasonId, setInitialVegSeasonId] = useState<string | undefined>(undefined);
  const [savingField, setSavingField] = useState(false);
  const [noFieldsOpen, setNoFieldsOpen] = useState(false);
  const [lastPromptedSeasonId, setLastPromptedSeasonId] = useState<string | null>(null);

  const selectedField = useMemo(() => {
    if (!selectedPlotId || !fieldsQ.data) return null;
    return fieldsQ.data.find((f) => f.id === selectedPlotId) ?? null;
  }, [fieldsQ.data, selectedPlotId]);

  const latestCrop = useMemo(() => {
    const seasonCycles = selectedField?.vegetationData?.filter((v) => v.seasonId === seasonId) ?? [];
    if (seasonCycles.length === 0) return null;
    const sorted = [...seasonCycles].sort((a, b) => {
      const yearA = a.year ?? 0;
      const yearB = b.year ?? 0;
      if (yearB !== yearA) return yearB - yearA;
      const dateA = a.sowingDate ? new Date(a.sowingDate).getTime() : 0;
      const dateB = b.sowingDate ? new Date(b.sowingDate).getTime() : 0;
      return dateB - dateA;
    });
    return sorted[0];
  }, [selectedField, seasonId]);

  const effectiveSourceId = useMemo(
    () => selectEffectiveSourceId({
      activeSourceId,
      defaultSourceId: configQ.data?.defaultSourceId,
      sources: sourcesQ.data,
    }),
    [activeSourceId, configQ.data?.defaultSourceId, sourcesQ.data],
  );
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((source) => source.id === effectiveSourceId) ?? null,
    [sourcesQ.data, effectiveSourceId],
  );
  const supportedIndices = selectedSource?.supportedIndices
    ?? configQ.data?.supportedIndices
    ?? ['NDVI'];
  const activeDisplayMode = displayMode ?? defaultDisplayModeForSource(
    selectedSource,
    configQ.data?.defaultIndex ?? 'NDVI',
  );
  const timelineIndexType = supportedIndices.includes(activeDisplayMode)
    ? activeDisplayMode
    : supportedIndices[0] ?? 'NDVI';
  const datesQ = useDates(effectiveSourceId, {
    enabled: Boolean(selectedField),
    fieldId: selectedField?.id,
    indexType: timelineIndexType,
  });
  const selectedDate = useMemo(() => {
    if (!datesQ.data || !configQ.data) return null;
    if (dateOverride && datesQ.data.some((entry) => entry.acquisitionDate === dateOverride)) {
      return dateOverride;
    }
    return selectDefaultDate(datesQ.data, configQ.data.usablePixelThresholdPercent, {
      sourceKind: selectedSource?.kind,
    })?.acquisitionDate ?? null;
  }, [configQ.data, dateOverride, datesQ.data, selectedSource?.kind]);
  const effectiveCloudMask = sanitizeCloudMaskForSource(
    cloudMask as CloudMaskOptions,
    selectedSource,
  );

  const seasonFields = useMemo(() => {
    if (!fieldsQ.data || !seasonId) return fieldsQ.data ?? [];
    return fieldsQ.data.filter((f) => f.seasonIds?.includes(seasonId)) ?? [];
  }, [fieldsQ.data, seasonId]);

  // If the active season has no fields and the user is in the field-analytics
  // (map workspace) view, alert them once per visit and offer to draw a field on
  // the map or dismiss into Global View. Never prompt while in Global View —
  // `overlaysVisible` is false there (see AppShell `setGlobalViewMode`). State
  // is adjusted during render (React-recommended; same pattern as AppShell
  // `trackedGroup`) rather than in an effect to avoid cascading render commits.
  const emptySeasonPrompt = Boolean(
    overlaysVisible && seasonId && fieldsQ.isSuccess && seasonFields.length === 0,
  );
  if (noFieldsOpen && !emptySeasonPrompt) {
    setNoFieldsOpen(false);
  } else if (emptySeasonPrompt && seasonId && lastPromptedSeasonId !== seasonId) {
    setLastPromptedSeasonId(seasonId);
    setNoFieldsOpen(true);
  } else if (!emptySeasonPrompt && seasonId && lastPromptedSeasonId === seasonId) {
    setLastPromptedSeasonId(null);
  }

  // A selected field that is not part of the active season (a stale selection
  // restored from localStorage, a deleted field, or an empty season) must not
  // draw a stray boundary on the map. Clear it while in the field-analytics
  // workspace (`overlaysVisible`); Global View deliberately keeps selections
  // for highlighting. Runs before the auto-select effect below so a stale
  // selection is removed in the same commit it could otherwise be re-picked.
  const staleSelectionInAnalytics = Boolean(
    overlaysVisible && seasonId && fieldsQ.isSuccess && selectedPlotId
    && !(selectedField && selectedField.seasonIds?.includes(seasonId)),
  );
  useEffect(() => {
    if (staleSelectionInAnalytics) clearSelectedPlot();
  }, [clearSelectedPlot, staleSelectionInAnalytics]);

  // On mount, auto-select a field for this season from Global View
  // so the map shows a field boundary instead of a blank "No field selected" state.
  const autoSelectedSeason = useRef<string | null>(null);
  useEffect(() => {
    if (selectedPlotId) return;
    if (!seasonId || !fieldsQ.data) return;
    if (autoSelectedSeason.current === seasonId) return;
    autoSelectedSeason.current = seasonId;
    const lastFieldMap = getLastFieldPerSeason();
    const lastFieldId = lastFieldMap[seasonId];
    const fieldId = lastFieldId && seasonFields.some((f) => f.id === lastFieldId)
      ? lastFieldId
      : seasonFields.length > 0
        ? seasonFields.reduce((a, b) =>
          new Date(b.createdAt ?? 0).getTime() > new Date(a.createdAt ?? 0).getTime() ? b : a,
        ).id
        : null;
    if (!fieldId) return;
    setLastFieldForSeason(seasonId, fieldId);
    setSelectedPlotId(fieldId);
    setFocusNonce(Date.now());
  }, [seasonFields, selectedPlotId, seasonId, fieldsQ.data, setSelectedPlotId, setFocusNonce]);

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
    <div className="h-full flex flex-col gap-3 px-4 py-3 overflow-hidden">
      { overlaysVisible && (
        <div className="flex flex-wrap shrink-0 items-stretch gap-y-2 rounded-md border border-border bg-muted/30 px-1.5 sm:px-2">
          <div className="flex items-center py-1 sm:py-1.5">
            <button
              type="button"
              onClick={ () => { clearSelectedPlot(); navigate('/monitoring/field-analytics'); } }
              disabled={ !selectedField }
              className="flex size-8 items-center justify-center rounded-md text-foreground/80 hover:bg-accent/60 disabled:opacity-40"
              aria-label="Back to all fields"
            >
              <span aria-hidden="true" className="text-base leading-none">←</span>
            </button>
          </div>

          <div className="mx-1.5 w-px self-stretch bg-border/60" />

          <div className="flex items-center py-1 sm:py-1.5">
            { selectedField ? (
              <FieldThumbnail geometry={ selectedField.geometry } size={ 32 } />
            ) : (
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border/60 bg-muted/30">
                <span className="text-xs text-muted-foreground">—</span>
              </div>
            ) }
          </div>

          <div className="mx-1.5 w-px self-stretch bg-border/60" />

          <div className="flex items-center py-1 sm:py-1.5 ml-2 sm:ml-3">
            <span className="truncate font-display text-sm font-semibold text-foreground">
              { selectedField?.name ?? 'No field selected' }
            </span>
          </div>

          { selectedField && (
            <>
              <div className="mx-1.5 w-px self-stretch bg-border/60" />
              <div className="flex items-center py-1 sm:py-1.5">
                <div className="flex flex-col items-center gap-0.5">
                  <span className="rounded border border-border/60 px-1.5 py-0.5 font-mono text-xs font-medium text-foreground/80 leading-none">
                    { formatAreaHa(selectedField.areaHa) }
                  </span>
                  <span className="text-[10px] text-muted-foreground leading-none">
                    { latestCrop?.cropName ?? 'Unknown crop' }
                  </span>
                </div>
              </div>

              <div className="mx-1.5 w-px self-stretch bg-border/60" />
              <div className="flex items-center py-1 sm:py-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={ () => { setInitialVegSeasonId(seasonId ?? undefined); setEditFieldOpen(true); } }
                  aria-label="Edit field"
                  className="size-8"
                >
                  <Pencil className="size-4" strokeWidth={ 1.75 } />
                </Button>
              </div>
            </>
          ) }

          <div className="ml-auto flex items-center gap-2 py-1 sm:py-1.5">
            <AddFieldDropdown
              fields={ seasonFields }
              onNavigate={ navigateWithImageryState }
              onSelectField={ (fieldId) => {
                setSelectedPlotId(fieldId);
                setFocusNonce(Date.now());
              } }
              selectedFieldId={ selectedPlotId }
              defaultSeasonId={ seasonId }
              testId="analytics-add-field"
            />
          </div>
        </div>
      ) }

      {/* Map card */ }
      <div className={ cn('rounded-md border border-border overflow-hidden', overlaysVisible && !mapFullscreen ? 'h-[50vh] shrink-0 min-h-0 md:h-[60vh]' : 'flex-1 min-h-0') }>
        <MapPage hidePlotToolbar simplifiedMapControls topLeftCoords showFullscreen />
      </div>

      {/* Analytics panel */ }
      { selectedField && overlaysVisible && !mapFullscreen && (
        <div className="animate-panel-in rounded-md border border-border bg-background overflow-y-auto min-h-0 flex-1">
          <IndexPanel
            className="w-full max-w-none rounded-none border-0 bg-transparent shadow-none"
            selectedPlot={ selectedField }
            selectedDate={ selectedDate }
            sourceId={ effectiveSourceId }
            displayMode={ activeDisplayMode }
            supportedIndices={ supportedIndices }
            cloudMask={ effectiveCloudMask }
            sourceMaskMethod={ selectedSource?.maskMethod ?? null }
            sourceMetricsProvisional={ selectedSource?.metricsProvisional ?? false }
            periodFrom={ periodFrom }
            periodTo={ periodTo }
            vegetationData={ selectedField?.vegetationData }
            seasonIds={ selectedField?.seasonIds }
            onShowAllCrops={ (seasonId) => { setInitialVegSeasonId(seasonId); setEditFieldOpen(true); } }
            radarEvidenceVisible={ radarEvidenceVisible }
            onRadarEvidenceVisibleChange={ setRadarEvidenceVisible }
          />
        </div>
      ) }

      { selectedField && (
        <EditFieldDialog
          key={ selectedField.id }
          field={ selectedField }
          open={ editFieldOpen }
          onOpenChange={ (open) => { if (!open) setInitialVegSeasonId(undefined); setEditFieldOpen(open); } }
          onSave={ (fieldId, name, geometry, vegetationData, groupId, areaHa) => {
            setSavingField(true);
            updateField.mutate(
              { fieldId, payload: { name, ...(geometry ? { geometry } : {}), ...(vegetationData ? { vegetationData } : {}), ...(groupId !== undefined ? { groupId } : {}), ...(areaHa !== undefined ? { areaHa } : {}) } },
              { onSuccess: () => { setSavingField(false); setEditFieldOpen(false); setInitialVegSeasonId(undefined); }, onError: () => setSavingField(false) },
            );
          } }
          saving={ savingField }
          onDelete={ (fieldId) => deleteField.mutateAsync(fieldId) }
          initialSeasonId={ initialVegSeasonId }
        />
      ) }

      <AlertDialogRoot open={ noFieldsOpen } onOpenChange={ setNoFieldsOpen }>
        <AlertDialogContent>
          <AlertDialogTitle>No fields in this season</AlertDialogTitle>
          <AlertDialogDescription>
            This season doesn't have any fields yet. Draw a field on the map to get started.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={ () => {
              setNoFieldsOpen(false);
              setGlobalViewOpen(true);
              setOverlaysVisible(false);
            } }>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={ () => {
                setNoFieldsOpen(false);
                navigate(`/monitoring/field-create?mode=draw&seasonId=${seasonId ?? ''}`);
              } }
            >
              Draw field
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>

    </div>
  );
}
