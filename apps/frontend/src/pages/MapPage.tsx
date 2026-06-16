import { useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { AlertTriangle, RefreshCw, Satellite } from 'lucide-react';
import {
  ApiError,
  composeTileTemplate,
  exportAllPlotsGeoJson,
  exportPlotGeoJson,
  type PlotGeoJsonImportPayload,
} from '@/lib/api';
import {
  useConfig,
  useCreatePlot,
  useDates,
  useDefaultLayer,
  useDeletePlot,
  useImportPlotsGeoJson,
  usePlots,
  useSources,
  useUpdatePlot,
} from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import type { SatelliteScene } from '@/lib/satelliteLayer';
import { AllFieldsPanel } from '@/components/fields/AllFieldsPanel';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { MapControls } from '@/components/map/MapControls';
import { MeasureTool } from '@/components/map/MeasureTool';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { CommandPalette } from '@/components/map/CommandPalette';
import { CoordinateReadout } from '@/components/map/CoordinateReadout';
import { Legend } from '@/components/map/Legend';
import { FieldContextHeader } from '@/components/map/FieldContextHeader';
import { LayerControlBar } from '@/components/layers/LayerControlBar';
import { TimelineBar } from '@/components/timeline/TimelineBar';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { IndexPanel } from '@/components/scaffold/IndexPanel';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useMapView } from '@/state/mapViewContext';
import { useMapUrlState } from '@/hooks/useMapUrlState';
import type { CloudMaskOptions, Plot, PlotGeometry, Source } from '@/types/api';

function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong while loading Akasha.';
}

function FullScreenLoading() {
  return (
    <div
      className="flex h-screen w-screen flex-col items-center justify-center gap-4 bg-background"
      data-testid="app-loading"
    >
      <div className="glass w-[320px] p-6">
        <div className="mb-4 flex items-center gap-2 text-primary">
          <Satellite className="size-5" strokeWidth={ 1.75 } />
          <span className="font-display text-lg font-semibold tracking-[-0.01em] text-foreground">
            Akasha
          </span>
        </div>
        <div className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-11 w-full" />
        </div>
        <p className="mt-4 text-[12px] text-muted-foreground">Acquiring orbital instrument…</p>
      </div>
    </div>
  );
}

function FullScreenError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      className="flex h-screen w-screen items-center justify-center bg-background"
      data-testid="app-error"
    >
      <div className="glass flex w-[360px] max-w-[90vw] flex-col items-start gap-3 p-6">
        <div className="flex items-center gap-2 text-destructive">
          <AlertTriangle className="size-5" strokeWidth={ 1.75 } />
          <h1 className="font-display text-lg font-semibold tracking-[-0.01em]">
            Unable to load
          </h1>
        </div>
        <p className="text-[13px] leading-5 text-muted-foreground">{ message }</p>
        <Button variant="primary" size="sm" onClick={ onRetry } data-testid="app-error-retry">
          <RefreshCw className="size-4" strokeWidth={ 1.75 } /> Try again
        </Button>
      </div>
    </div>
  );
}

function geometryCoordinates(geometry: PlotGeometry): [number, number][] {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates.flat() as [number, number][];
  }
  return geometry.coordinates.flat(2) as [number, number][];
}

function focusPlot(map: maplibregl.Map | null, plot: Plot): void {
  const coordinates = geometryCoordinates(plot.geometry);
  if (!map || coordinates.length === 0) return;
  const lngs = coordinates.map(([lng]) => lng);
  const lats = coordinates.map(([, lat]) => lat);
  map.fitBounds(
    [
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)],
    ],
    { padding: 96, maxZoom: 16, duration: 650 },
  );
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function geoJsonFilename(plot: Plot | null): string {
  if (!plot) return 'fields.geojson';
  const safeName = plot.name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return `${safeName || 'field'}.geojson`;
}

/** Map an Akasha {@link Source} to a short sensor badge (for example `S2`, `S1`). */
function sensorBadgeForSource(source: Source | null | undefined): string | null {
  if (!source) return null;
  const haystack = `${source.id} ${source.label}`.toLowerCase();
  if (haystack.includes('resourcesat-2a')) return 'RS2A';
  if (haystack.includes('sentinel-2') || haystack.includes('sentinel 2')) return 'S2';
  if (haystack.includes('sentinel-1') || haystack.includes('sentinel 1')) return 'S1';
  return null;
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

export default function MapPage() {
  useMapUrlState();
  const configQ = useConfig();
  const sourcesQ = useSources();
  const defaultLayerQ = useDefaultLayer();
  const view = useMapView();
  const {
    activeSourceId,
    selectedDate: dateOverride,
    displayMode: displayModeOverride,
    opacity,
    visible,
    compareEnabled,
    compareDate,
    selectedPlotId,
    cloudMask,
    legendOpen,
    periodFrom,
    periodTo,
  } = view;

  const effectiveSourceId = activeSourceId ?? sourcesQ.data?.[0]?.id;
  const datesQ = useDates(effectiveSourceId);
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((s) => s.id === effectiveSourceId),
    [sourcesQ.data, effectiveSourceId],
  );

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [allFieldsOpen, setAllFieldsOpen] = useState(false);
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [basemapRuntimeError, setBasemapRuntimeError] = useState<Error | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const plotsQ = usePlots();
  const createPlotMutation = useCreatePlot();
  const updatePlotMutation = useUpdatePlot();
  const importPlotsMutation = useImportPlotsGeoJson();
  const deletePlotMutation = useDeletePlot({
    onDeleted: (plotId) => {
      if (plotId === selectedPlotId) view.clearSelectedPlot();
    },
  });

  const selectedPlot = useMemo(() => {
    if (!selectedPlotId) return null;
    return plotsQ.data?.find((plot) => plot.id === selectedPlotId) ?? null;
  }, [plotsQ.data, selectedPlotId]);

  useEffect(() => {
    if (!selectedPlotId || plotsQ.isLoading || !plotsQ.data) return;
    if (!plotsQ.data.some((plot) => plot.id === selectedPlotId)) {
      view.clearSelectedPlot();
    }
  }, [plotsQ.data, plotsQ.isLoading, selectedPlotId, view]);

  // Focus the last-selected field on first load so a refresh keeps the map
  // centred on the user's context instead of the default AOI.
  const initialFocusDone = useRef(false);
  useEffect(() => {
    if (initialFocusDone.current) return;
    if (!map || plotsQ.isLoading) return;
    if (selectedPlot) {
      focusPlot(map, selectedPlot);
      initialFocusDone.current = true;
    }
  }, [map, plotsQ.isLoading, selectedPlot]);

  // ⌘K / Ctrl-K toggles the command palette from anywhere.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const activeTimelineDates = datesQ.data;
  const activeSourceKind = selectedSource?.kind;
  const effectiveCloudMask = useMemo(
    () => sanitizeCloudMaskForSource(cloudMask, selectedSource),
    [cloudMask, selectedSource],
  );

  // Effective acquisition date: keep a still-valid user choice, otherwise the
  // computed default (latest usable -> threshold -> newest). Derived, not stored,
  // so we never call setState inside an effect.
  const selectedDate = useMemo<string | null>(() => {
    if (!activeTimelineDates || !configQ.data) return null;
    if (dateOverride && activeTimelineDates.some((d) => d.acquisitionDate === dateOverride)) {
      return dateOverride;
    }
    const def = selectDefaultDate(activeTimelineDates, configQ.data.usablePixelThresholdPercent, {
      sourceKind: activeSourceKind,
    });
    return def ? def.acquisitionDate : null;
  }, [activeTimelineDates, configQ.data, dateOverride, activeSourceKind]);

  const basemapResolution = useMemo(() => {
    if (!configQ.data) return { basemapConfig: null, basemapError: null };
    try {
      return { basemapConfig: resolveBasemapConfig(configQ.data), basemapError: null };
    } catch (error) {
      return { basemapConfig: null, basemapError: error };
    }
  }, [configQ.data]);

  const selectedDateMetadata = useMemo(
    () => activeTimelineDates?.find((d) => d.acquisitionDate === selectedDate) ?? null,
    [activeTimelineDates, selectedDate],
  );

  const sourceDisplayModes = selectedSource?.displayModes ?? ['FCC'];
  const selectedDisplayMode =
    displayModeOverride ??
    selectedSource?.displayMode ??
    selectedSource?.defaultDisplayMode ??
    sourceDisplayModes[0] ??
    (defaultLayerQ.data && defaultLayerQ.data.sourceId === effectiveSourceId
      ? defaultLayerQ.data.displayMode
      : undefined) ??
    'FCC';

  const scene = useMemo<SatelliteScene | null>(() => {
    if (!selectedDate || !effectiveSourceId) return null;
    const dl = defaultLayerQ.data;
    const isDefault =
      dl &&
      dl.sourceId === effectiveSourceId &&
      dl.acquisitionDate === selectedDate &&
      (dl.displayMode ?? 'FCC') === selectedDisplayMode;
    const dateBounds = selectedDateMetadata?.bounds;
    if (isDefault && dl.tileUrlTemplate) {
      return {
        tileUrlTemplate: dl.tileUrlTemplate,
        bounds: dl.bounds ?? dateBounds,
        minzoom: dl.minzoom,
        maxzoom: dl.maxzoom,
        attribution: selectedSource?.attribution ?? dl.attribution,
      };
    }
    return {
      tileUrlTemplate: composeTileTemplate(effectiveSourceId, selectedDate, selectedDisplayMode),
      bounds: dateBounds,
      minzoom: dl?.minzoom,
      maxzoom: dl?.maxzoom,
      attribution:
        selectedSource?.attribution ??
        (dl?.sourceId === effectiveSourceId ? dl.attribution : undefined),
    };
  }, [
    selectedDate,
    effectiveSourceId,
    defaultLayerQ.data,
    selectedDateMetadata,
    selectedDisplayMode,
    selectedSource?.attribution,
  ]);

  // Compare ("B") scene: same source + display mode, a different acquisition date.
  // Rendered beneath A; the opacity slider blends A over B.
  const sceneB = useMemo<SatelliteScene | null>(() => {
    if (!visible || !compareEnabled || !compareDate) return null;
    if (compareDate === selectedDate) return null;
    if (!effectiveSourceId) return null;
    const meta = datesQ.data?.find((d) => d.acquisitionDate === compareDate);
    if (!meta?.tileAvailable) return null;
    return {
      tileUrlTemplate: composeTileTemplate(effectiveSourceId, compareDate, selectedDisplayMode),
      bounds: meta?.bounds,
      minzoom: defaultLayerQ.data?.minzoom,
      maxzoom: defaultLayerQ.data?.maxzoom,
      attribution: selectedSource?.attribution,
    };
  }, [
    compareEnabled,
    compareDate,
    visible,
    effectiveSourceId,
    selectedDate,
    selectedDisplayMode,
    datesQ.data,
    defaultLayerQ.data,
    selectedSource?.attribution,
  ]);

  // Chronological, tile-available dates for the compare B-scene picker.
  const comparableDates = useMemo(
    () =>
      (activeTimelineDates ?? [])
        .filter((d) => d.tileAvailable)
        .sort((a, b) => a.acquisitionDate.localeCompare(b.acquisitionDate)),
    [activeTimelineDates],
  );

  // Marginal/empty signal: no date meets the usability threshold.
  const marginalNote = useMemo<string | null>(() => {
    if (!activeTimelineDates || activeTimelineDates.length === 0 || !configQ.data) return null;
    if (activeSourceKind === 'sar') return null;
    const threshold = configQ.data.usablePixelThresholdPercent;
    const qualifies = activeTimelineDates.some(
      (d) => d.isLatestUsable || (d.usablePixelPercent != null && d.usablePixelPercent >= threshold),
    );
    if (qualifies) return null;
    const newest = [...activeTimelineDates].sort((a, b) =>
      b.acquisitionDate.localeCompare(a.acquisitionDate),
    )[0];
    return `No usable optical scene in range. Showing the most recent attempt (${newest.acquisitionDate}).`;
  }, [activeTimelineDates, configQ.data, activeSourceKind]);

  // Nearest radar pass note (SAR), shown when the active pass isn't the canonical one.
  const nearestPassNote = useMemo<string | null>(() => {
    if (selectedSource?.kind !== 'sar') return null;
    if (!selectedDate) return null;
    return `Nearest radar pass: ${selectedDate}.`;
  }, [selectedSource?.kind, selectedDate]);

  const requestMapTool = (owner: MapToolOwner): boolean => {
    setActiveMapTool(owner);
    return true;
  };

  // Wrapper to request tool ownership and start drawing a field
  const handleAddField = () => {
    if (!map) {
      // Map not ready – do nothing or could show a warning
      return;
    }
    // Ensure we have ownership of the field-draw tool before activating draw mode
    requestMapTool('field-draw');
    setFieldMode('draw');
  };

  const releaseMapTool = (owner: MapToolOwner) => {
    setActiveMapTool((current) => (current === owner ? null : current));
  };

  const selectAndFocusPlot = (plot: Plot) => {
    view.setSelectedPlotId(plot.id);
    focusPlot(map, plot);
  };

  const importGeoJsonFile = async (file: File) => {
    const text = await file.text();
    const payload = JSON.parse(text) as PlotGeoJsonImportPayload;
    const result = await importPlotsMutation.mutateAsync(payload);
    const first = result.imported[0];
    if (first) {
      view.setSelectedPlotId(first.id);
      focusPlot(map, first);
    }
  };

  const exportGeoJson = async () => {
    const blob = selectedPlot
      ? await exportPlotGeoJson(selectedPlot.id)
      : await exportAllPlotsGeoJson();
    downloadBlob(blob, geoJsonFilename(selectedPlot));
  };

  const deleteSelectedField = async () => {
    if (!selectedPlot) return;
    const confirmed = window.confirm(`Delete field "${selectedPlot.name}"?`);
    if (!confirmed) return;
    await deletePlotMutation.mutateAsync(selectedPlot.id);
  };

  if (configQ.isLoading) return <FullScreenLoading />;
  if (configQ.isError || !configQ.data) {
    return <FullScreenError message={ messageFor(configQ.error) } onRetry={ () => configQ.refetch() } />;
  }
  if (basemapResolution.basemapError instanceof BasemapConfigurationError) {
    return (
      <FullScreenError
        message={ basemapResolution.basemapError.message }
        onRetry={ () => configQ.refetch() }
      />
    );
  }
  if (basemapResolution.basemapError) {
    return (
      <FullScreenError
        message={ messageFor(basemapResolution.basemapError) }
        onRetry={ () => configQ.refetch() }
      />
    );
  }
  if (!basemapResolution.basemapConfig) {
    return (
      <FullScreenError
        message="Esri basemap configuration is missing."
        onRetry={ () => configQ.refetch() }
      />
    );
  }
  if (basemapRuntimeError) {
    return (
      <FullScreenError
        message={ `Unable to load Esri basemap: ${basemapRuntimeError.message}` }
        onRetry={ () => {
          setBasemapRuntimeError(null);
          void configQ.refetch();
        } }
      />
    );
  }

  const config = configQ.data;
  const sourceAttribution = selectedSource?.attribution ?? selectedSource?.provider;
  const attribution = scene?.attribution ?? sourceAttribution ?? 'Satellite imagery';
  const sourceSupportedIndices = selectedSource?.supportedIndices ?? config.supportedIndices;
  const analyticsSupportedIndices = sourceSupportedIndices;
  const sourceAnalysisLevel = selectedSource?.analysisLevel ?? 'field';
  const analyticsEnabled =
    selectedSource?.kind !== 'sar' &&
    sourceAnalysisLevel === 'field' &&
    sourceSupportedIndices.length > 0;
  const exportIndexType = analyticsSupportedIndices.includes(selectedDisplayMode)
    ? selectedDisplayMode
    : analyticsSupportedIndices[0] ?? config.defaultIndex ?? 'NDVI';
  const showIndexPanel = analyticsEnabled;

  return (
    <div className="relative h-full min-h-[640px] w-full overflow-hidden bg-background" data-testid="map-page">
      {/* Accessibility: bypass the map canvas (WCAG 2.4.1). */ }
      <a
        href="#timeline-bar"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-popover focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-[13px] focus:font-medium focus:text-primary-foreground"
      >
        Skip the map
      </a>

      <MapLayerManager
        basemap={ basemapResolution.basemapConfig }
        center={ config.aoi.center }
        zoom={ config.aoi.zoom }
        scene={ scene }
        sceneB={ sceneB }
        opacity={ opacity / 100 }
        visible={ visible }
        onBasemapError={ setBasemapRuntimeError }
        onMapReady={ setMap }
      />
      <FieldBoundaryLayer
        map={ map }
        plot={ selectedPlot }
        geometry={ draftGeometry }
        featureId="draft-field"
        name="Draft field"
      />
      <FieldDrawController
        activeTool={ activeMapTool }
        map={ map }
        mode={ fieldMode }
        selectedPlot={ selectedPlot }
        onCancel={ () => setFieldMode(null) }
        onCreateField={ async (payload) => {
          const created = await createPlotMutation.mutateAsync(payload);
          view.setSelectedPlotId(created.id);
          focusPlot(map, created);
          return created;
        } }
        onUpdateField={ async (plotId, payload) => {
          const updated = await updatePlotMutation.mutateAsync({ plotId, payload });
          view.setSelectedPlotId(updated.id);
          focusPlot(map, updated);
          return updated;
        } }
        onRequestTool={ requestMapTool }
        onReleaseTool={ releaseMapTool }
        onPolygonComplete={ (geometry) => setDraftGeometry(geometry) }
        className="absolute right-4 top-[280px] z-popover max-[760px]:right-4 max-[760px]:top-[37.5rem]"
      />

      {/* Top chrome: field context · layers · search · theme · all-fields trigger */ }
      <FieldContextHeader
        selectedPlot={ selectedPlot }
        fieldCount={ plotsQ.data?.length ?? 0 }
        allFieldsOpen={ allFieldsOpen }
        onToggleAllFields={ () => setAllFieldsOpen((open) => !open) }
        onBack={ () => {
          view.clearSelectedPlot();
          setAllFieldsOpen(true);
        } }
        onEditGeometry={ () =>
          selectedPlot ? setFieldMode((current) => (current === 'edit' ? null : 'edit')) : undefined
        }
        onOpenCommand={ () => setCommandOpen(true) }
      />

      <CommandPalette
        open={ commandOpen }
        onOpenChange={ setCommandOpen }
        sources={ sourcesQ.data }
        activeSourceId={ effectiveSourceId }
        dates={ datesQ.data }
        onSelectSource={ view.setSource }
        onSelectDate={ view.setDate }
        onToggleLayers={ view.toggleLayers }
      />

      <input
        ref={ fileInputRef }
        type="file"
        accept=".geojson,application/geo+json,application/json"
        className="hidden"
        data-testid="field-import-input"
        onChange={ (event) => {
          const file = event.target.files?.[0];
          event.currentTarget.value = '';
          if (file) void importGeoJsonFile(file);
        } }
      />

      {/* Left: field tools */ }
      <div className="absolute left-4 top-[68px] z-toolbar">
        <PlotToolbar
          activeAction={ fieldMode === 'draw' ? 'draw' : null }
          isMapAvailable={ Boolean(map) }
          // Request ownership of the field-draw tool before toggling draw mode
          onDrawField={ () => {
            requestMapTool('field-draw');
            setFieldMode((current) => (current === 'draw' ? null : 'draw'));
          } }
          // Request ownership of the field-edit tool before toggling edit mode
          onEditSelectedField={ () => {
            requestMapTool('field-edit');
            setFieldMode((current) => (current === 'edit' ? null : 'edit'));
          } }
          onImportGeoJSON={ () => undefined }
          onExportGeoJSON={ () => void exportGeoJson() }
          onDeleteSelectedField={ () => void deleteSelectedField() }
        />
      </div>

      {/* Right: stacked panels — All Fields dropdown above, field details below */ }
      <div className="absolute right-4 top-[68px] z-panel flex max-w-[360px] flex-col gap-3">
        { allFieldsOpen && (
          <AllFieldsPanel
            plots={ plotsQ.data }
            isLoading={ plotsQ.isLoading }
            error={ plotsQ.isError ? messageFor(plotsQ.error) : null }
            onRetry={ () => void plotsQ.refetch() }
            selectedPlotId={ selectedPlotId }
            onSelect={ (plot) => {
              view.setSelectedPlotId(plot.id);
              selectAndFocusPlot(plot);
              setAllFieldsOpen(false);
            } }
            onEdit={ (plot) => {
              view.setSelectedPlotId(plot.id);
              setFieldMode('edit');
              setAllFieldsOpen(false);
            } }
            onDelete={ (plot) => {
              const confirmed = window.confirm(`Delete field "${plot.name}"?`);
              if (!confirmed) return;
              deletePlotMutation.mutateAsync(plot.id).then(() => {
                view.clearSelectedPlot();
                if (map && config) {
                  map.flyTo({
                    center: config.aoi.center,
                    zoom: config.aoi.zoom,
                    duration: 800,
                  });
                }
              });
            } }
            onAdd={ map ? handleAddField : undefined }
            onImport={ () => fileInputRef.current?.click() }
          />
        ) }
        { showIndexPanel && (
          <div className="hidden xl:block">
            <IndexPanel
              selectedPlot={ selectedPlot }
              selectedDate={ selectedDate }
              sourceId={ effectiveSourceId }
              displayMode={ selectedDisplayMode }
              supportedIndices={ analyticsSupportedIndices }
              cloudMask={ effectiveCloudMask }
              sourceMaskMethod={ selectedSource?.maskMethod ?? null }
              sourceMetricsProvisional={ Boolean(selectedSource?.metricsProvisional) }
              periodFrom={ periodFrom }
              periodTo={ periodTo }
            />
          </div>
        ) }
      </div>

      {/* Right: coordinate readout, measure, and consolidated layer-control bar (above timeline). */ }
      <div className="absolute bottom-[calc(var(--timeline-height)+2.5rem)] right-4 z-toolbar flex flex-col items-end gap-2">
        <CoordinateReadout map={ map } />
        <MeasureTool
          activeTool={ activeMapTool }
          map={ map }
          onRequestTool={ requestMapTool }
          onReleaseTool={ releaseMapTool }
        />
        <LayerControlBar
          sources={ sourcesQ.data }
          activeSourceId={ effectiveSourceId }
          onSelectSource={ view.setSource }
          displayModes={ sourceDisplayModes }
          displayMode={ selectedDisplayMode }
          onDisplayModeChange={ view.setDisplayMode }
          cloudMask={ cloudMask }
          onCloudMaskChange={ view.setCloudMask }
          cloudMaskDisabled={ !analyticsEnabled || !selectedSource?.availableMaskOptions?.length }
          compareEnabled={ compareEnabled }
          onCompareEnabledChange={ view.setCompareEnabled }
          comparableDates={ comparableDates }
          activeDate={ selectedDate }
          compareDate={ compareDate }
          onCompareDateChange={ view.setCompareDate }
          blend={ opacity }
          onBlendChange={ view.setOpacity }
          selectedPlot={ selectedPlot }
          selectedDate={ selectedDate }
          exportSourceId={ effectiveSourceId }
          exportIndexType={ exportIndexType }
          exportCloudMask={ effectiveCloudMask }
          analyticsEnabled={ analyticsEnabled }
          collapsed={ view.layerBarCollapsed }
          onCollapsedChange={ view.setLayerBarCollapsed }
        />
      </div>

      {/* Left: legend + navigation map controls (zoom / compass / locate / fullscreen),
        * stacked in a single bottom-left column so they never overlap each other.
        * Raised above the attribution line so the two never collide at any width. */ }
      <div className="absolute left-4 bottom-[calc(var(--timeline-height)+2.5rem)] z-toolbar flex flex-col items-start gap-2">
        { visible && legendOpen && (
          <Legend displayMode={ selectedDisplayMode } sourceKind={ activeSourceKind } />
        ) }
        <MapControls
          map={ map }
          hasSelectedField={ Boolean(selectedPlot) }
          legendOpen={ legendOpen }
          onFindSelectedField={ () => {
            if (selectedPlot) focusPlot(map, selectedPlot);
          } }
          onLegendOpenChange={ view.setLegendOpen }
        />
      </div>

      {/* Map attribution — its own thin line pinned just above the timeline so it
        * never overlaps the floating control clusters on any screen size. */ }
      <div
        className="pointer-events-none absolute bottom-[calc(var(--timeline-height)+0.5rem)] left-4 z-toolbar max-w-[calc(100vw-2rem)] truncate rounded-sm bg-[hsl(var(--panel)/0.55)] px-1.5 py-0.5 text-[11px] text-foreground/80 backdrop-blur-sm"
        data-testid="attribution"
      >
        { attribution }
      </div>

      {/* Bottom: temporal filmstrip */ }
      <div id="timeline-bar" className="absolute inset-x-0 bottom-0 z-panel px-2 pb-2">
        <TimelineBar
          dates={ activeTimelineDates }
          selectedDate={ selectedDate }
          onSelect={ view.setDate }
          sourceKind={ activeSourceKind }
          sensorBadge={ sensorBadgeForSource(selectedSource) }
          loading={ datesQ.isLoading }
          error={
            datesQ.isError ? messageFor(datesQ.error) : null
          }
          onRetry={ () => void datesQ.refetch() }
          marginalNote={ marginalNote }
          nearestPassNote={ nearestPassNote }
          onPrefetchDate={ undefined }
          periodFrom={ periodFrom }
          periodTo={ periodTo }
          onPeriodChange={ view.setPeriod }
        />
      </div>
    </div>
  );
}
