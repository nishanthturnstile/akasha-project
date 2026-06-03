import { useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { AlertTriangle, RefreshCw, Satellite } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  composeTileTemplate,
  exportAllPlotsGeoJson,
  exportPlotGeoJson,
  getDates,
  withCloudMaskParams,
  type PlotGeoJsonImportPayload,
} from '@/lib/api';
import {
  queryKeys,
  useConfig,
  useCreatePlot,
  useDates,
  useDefaultLayer,
  useDeletePlot,
  useFieldScenes,
  useImportPlotsGeoJson,
  usePlots,
  useSources,
  useSyncFieldProvider,
  useUpdatePlot,
} from '@/lib/queries';
import { basemapAttribution, resolveBasemapStyle } from '@/map/basemap';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import type { SatelliteScene } from '@/lib/satelliteLayer';
import { AllFieldsPanel } from '@/components/fields/AllFieldsPanel';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { MapControls } from '@/components/map/MapControls';
import { CloudMaskControl } from '@/components/monitoring/CloudMaskControl';
import { DownloadMenu } from '@/components/monitoring/DownloadMenu';
import { FieldSceneStatusPanel } from '@/components/monitoring/FieldSceneStatusPanel';
import { MeasureTool } from '@/components/map/MeasureTool';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { CompareControl } from '@/components/map/CompareControl';
import { CommandPalette } from '@/components/map/CommandPalette';
import { CoordinateReadout } from '@/components/map/CoordinateReadout';
import { Legend } from '@/components/map/Legend';
import { TopBar } from '@/components/map/TopBar';
import { LayersSurface } from '@/components/layers/LayersSurface';
import { SourceList } from '@/components/layers/SourceList';
import { TimelineBar } from '@/components/timeline/TimelineBar';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { IndexPanel } from '@/components/scaffold/IndexPanel';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useMapView } from '@/state/mapViewContext';
import type { FieldScene, Plot, PlotGeometry, SceneDate } from '@/types/api';

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

function sceneDateFromFieldScene(scene: FieldScene, latest: boolean): SceneDate {
  return {
    acquisitionDate: scene.acquisitionDate,
    datetime: scene.datetime ?? `${scene.acquisitionDate}T00:00:00Z`,
    usablePixelPercent: scene.usablePixelPercent,
    cloudMaskedPercent: scene.cloudMaskedPercent ?? scene.cloudPercent ?? null,
    coveragePercent: scene.coveragePercent ?? null,
    isLatestUsable: latest,
    metricsProvisional: scene.metricsProvisional,
    tileAvailable: scene.tileAvailable,
    sceneCount: scene.sceneCount ?? undefined,
    bounds: scene.bounds,
  };
}

function fieldLayerFor(scene: FieldScene | null | undefined, displayMode: string) {
  if (!scene) return null;
  return (
    scene.layers.find((layer) => layer.displayMode === displayMode && layer.available) ??
    scene.layers.find((layer) => layer.displayMode === 'RGB' && layer.available) ??
    null
  );
}

export default function MapPage() {
  const configQ = useConfig();
  const sourcesQ = useSources();
  const defaultLayerQ = useDefaultLayer();
  const queryClient = useQueryClient();

  const view = useMapView();
  const {
    activeSourceId,
    selectedDate: dateOverride,
    displayMode: displayModeOverride,
    opacity,
    visible,
    layersOpen,
    compareEnabled,
    compareDate,
    selectedPlotId,
    cloudMask,
    legendOpen,
  } = view;

  const effectiveSourceId = activeSourceId ?? sourcesQ.data?.[0]?.id;
  const datesQ = useDates(effectiveSourceId);
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((s) => s.id === effectiveSourceId),
    [sourcesQ.data, effectiveSourceId],
  );

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const plotsQ = usePlots();
  const createPlotMutation = useCreatePlot();
  const updatePlotMutation = useUpdatePlot();
  const importPlotsMutation = useImportPlotsGeoJson();
  const syncFieldMutation = useSyncFieldProvider();
  const deletePlotMutation = useDeletePlot({
    onDeleted: (plotId) => {
      if (plotId === selectedPlotId) view.clearSelectedPlot();
    },
  });

  const selectedPlot = useMemo(() => {
    if (!selectedPlotId) return null;
    return plotsQ.data?.find((plot) => plot.id === selectedPlotId) ?? null;
  }, [plotsQ.data, selectedPlotId]);
  const fieldScenesQ = useFieldScenes(selectedPlot?.id);

  useEffect(() => {
    if (!selectedPlotId || plotsQ.isLoading || !plotsQ.data) return;
    if (!plotsQ.data.some((plot) => plot.id === selectedPlotId)) {
      view.clearSelectedPlot();
    }
  }, [plotsQ.data, plotsQ.isLoading, selectedPlotId, view]);

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

  const fieldSceneMode =
    Boolean(selectedPlot) &&
    fieldScenesQ.data?.scope === 'field' &&
    fieldScenesQ.data.scenes.length > 0;

  const fieldTimelineDates = useMemo<SceneDate[]>(() => {
    if (!fieldSceneMode || !fieldScenesQ.data) return [];
    const ordered = [...fieldScenesQ.data.scenes].sort((a, b) =>
      b.acquisitionDate.localeCompare(a.acquisitionDate),
    );
    return ordered.map((fieldScene, index) => sceneDateFromFieldScene(fieldScene, index === 0));
  }, [fieldSceneMode, fieldScenesQ.data]);

  const activeTimelineDates = fieldSceneMode ? fieldTimelineDates : datesQ.data;
  const activeSourceKind = fieldSceneMode ? 'optical' : selectedSource?.kind;

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

  const basemapStyle = useMemo(() => resolveBasemapStyle(configQ.data), [configQ.data]);

  const selectedDateMetadata = useMemo(
    () => activeTimelineDates?.find((d) => d.acquisitionDate === selectedDate) ?? null,
    [activeTimelineDates, selectedDate],
  );

  const selectedFieldScene = useMemo(
    () =>
      fieldSceneMode
        ? fieldScenesQ.data?.scenes.find((s) => s.acquisitionDate === selectedDate) ?? null
        : null,
    [fieldSceneMode, fieldScenesQ.data, selectedDate],
  );

  const fieldDisplayModes = fieldScenesQ.data?.displayModes ?? ['RGB'];
  const selectedDisplayMode = fieldSceneMode
    ? fieldDisplayModes.includes(displayModeOverride ?? '')
      ? (displayModeOverride as string)
      : 'RGB'
    : displayModeOverride ??
      selectedSource?.displayMode ??
      selectedSource?.defaultDisplayMode ??
      selectedSource?.displayModes?.[0] ??
      (defaultLayerQ.data && defaultLayerQ.data.sourceId === effectiveSourceId
        ? defaultLayerQ.data.displayMode
        : undefined) ??
      'RGB';

  const scene = useMemo<SatelliteScene | null>(() => {
    if (fieldSceneMode) {
      const layer = fieldLayerFor(selectedFieldScene, selectedDisplayMode);
      if (!layer) return null;
      return {
        tileUrlTemplate: withCloudMaskParams(layer.tileUrlTemplate, cloudMask),
        bounds: selectedFieldScene?.bounds,
        minzoom: defaultLayerQ.data?.minzoom,
        maxzoom: defaultLayerQ.data?.maxzoom,
        attribution: layer.attribution,
      };
    }
    if (!selectedDate || !effectiveSourceId) return null;
    const dl = defaultLayerQ.data;
    const isDefault =
      dl &&
      dl.sourceId === effectiveSourceId &&
      dl.acquisitionDate === selectedDate &&
      (dl.displayMode ?? 'RGB') === selectedDisplayMode;
    const dateBounds = selectedDateMetadata?.bounds;
    if (isDefault) {
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
    fieldSceneMode,
    selectedFieldScene,
    cloudMask,
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
    if (fieldSceneMode) {
      const fieldScene = fieldScenesQ.data?.scenes.find((s) => s.acquisitionDate === compareDate);
      const layer = fieldLayerFor(fieldScene, selectedDisplayMode);
      if (!fieldScene?.tileAvailable || !layer) return null;
      return {
        tileUrlTemplate: withCloudMaskParams(layer.tileUrlTemplate, cloudMask),
        bounds: fieldScene.bounds,
        minzoom: defaultLayerQ.data?.minzoom,
        maxzoom: defaultLayerQ.data?.maxzoom,
        attribution: layer.attribution,
      };
    }
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
    fieldSceneMode,
    fieldScenesQ.data,
    cloudMask,
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
    if (fieldSceneMode) return null;
    if (selectedSource?.kind !== 'sar') return null;
    if (effectiveSourceId !== 'sentinel-1-grd') return null;
    if (!selectedDate || selectedDate === '2026-04-27') return null;
    return `Nearest radar pass: ${selectedDate}.`;
  }, [fieldSceneMode, selectedSource?.kind, effectiveSourceId, selectedDate]);

  const prefetchDates = (sourceId: string) => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.dates(sourceId),
      queryFn: () => getDates(sourceId),
    });
  };

  const requestMapTool = (owner: MapToolOwner): boolean => {
    setActiveMapTool(owner);
    return true;
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

  const syncSelectedField = async () => {
    if (!selectedPlot) return;
    await syncFieldMutation.mutateAsync(selectedPlot.id);
  };

  if (configQ.isLoading) return <FullScreenLoading />;
  if (configQ.isError || !configQ.data) {
    return <FullScreenError message={ messageFor(configQ.error) } onRetry={ () => configQ.refetch() } />;
  }

  const config = configQ.data;
  const sourceAttribution = selectedSource?.attribution ?? selectedSource?.provider;
  const attribution = scene?.attribution ?? sourceAttribution ?? 'Satellite imagery';
  const basemapCredit = basemapAttribution(configQ.data);
  const sourceSupportedIndices = selectedSource?.supportedIndices ?? config.supportedIndices;
  const analyticsSupportedIndices = fieldSceneMode
    ? fieldDisplayModes.filter((mode) => !['RGB', 'FALSE_COLOR'].includes(mode))
    : sourceSupportedIndices;
  const showIndexPanel =
    fieldSceneMode || (selectedSource?.kind !== 'sar' && sourceSupportedIndices.length > 0);

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
        basemapStyle={ basemapStyle }
        center={ config.aoi.center }
        zoom={ config.aoi.zoom }
        scene={ scene }
        sceneB={ sceneB }
        opacity={ opacity / 100 }
        visible={ visible }
        onMapReady={ setMap }
      />
      <FieldBoundaryLayer map={ map } plot={ selectedPlot } />
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
        className="absolute left-4 top-[68px] z-popover translate-y-12"
      />

      {/* Top chrome: layers toggle · search · theme */ }
      <TopBar
        layersOpen={ layersOpen }
        onToggleLayers={ view.toggleLayers }
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
          activeAction={ fieldMode }
          disabledActions={ {
            draw: !map ? 'The map must finish loading before drawing a field.' : undefined,
            edit:
              selectedPlot && selectedPlot.geometry.type !== 'Polygon'
                ? 'Multi-part field editing is not available in this first field workflow.'
                : undefined,
          } }
          hasSelectedField={ Boolean(selectedPlot) }
          isMapAvailable={ Boolean(map) }
          selectedFieldName={ selectedPlot?.name }
          onDrawField={ () => setFieldMode((current) => (current === 'draw' ? null : 'draw')) }
          onEditSelectedField={ () => setFieldMode((current) => (current === 'edit' ? null : 'edit')) }
          onImportGeoJSON={ () => fileInputRef.current?.click() }
          onExportGeoJSON={ () => void exportGeoJson() }
          onDeleteSelectedField={ () => void deleteSelectedField() }
        />
      </div>

      {/* Layers surface — left drawer (≥md) / bottom sheet (<md) */ }
      <div className="absolute left-4 top-[112px] z-panel">
        <AllFieldsPanel
          plots={ plotsQ.data }
          isLoading={ plotsQ.isLoading }
          error={ plotsQ.isError ? messageFor(plotsQ.error) : null }
          onRetry={ () => void plotsQ.refetch() }
          selectedPlotId={ selectedPlotId }
          onSelect={ (plot) => view.setSelectedPlotId(plot.id) }
          onFocus={ selectAndFocusPlot }
          onAdd={ () => setFieldMode('draw') }
          onImport={ () => fileInputRef.current?.click() }
        />
      </div>

      <div className="absolute left-[392px] top-[112px]">
        <LayersSurface open={ layersOpen } onClose={ () => view.setLayersOpen(false) }>
          <SourceList
            sources={ sourcesQ.data }
            activeSourceId={ effectiveSourceId }
            selectedDate={ selectedDate }
            displayMode={ selectedDisplayMode }
            visible={ visible }
            opacity={ opacity }
            onSelectSource={ view.setSource }
            onDisplayModeChange={ view.setDisplayMode }
            onVisibleChange={ view.setVisible }
            onOpacityChange={ view.setOpacity }
            onPrefetchSource={ prefetchDates }
          />
        </LayersSurface>
      </div>

      {/* Right: field scene status + index panel (Phase 5 placeholder) */ }
      <div className="absolute right-4 top-[68px] z-toolbar hidden max-w-[300px] flex-col gap-2 xl:flex">
        <FieldSceneStatusPanel
          selectedPlot={ selectedPlot }
          response={ fieldScenesQ.data }
          loading={ Boolean(selectedPlot) && fieldScenesQ.isLoading }
          error={ fieldScenesQ.isError ? messageFor(fieldScenesQ.error) : null }
          onRetry={ () => void fieldScenesQ.refetch() }
          onSync={ () => void syncSelectedField() }
          syncing={ syncFieldMutation.isPending }
          displayModes={ fieldDisplayModes }
          displayMode={ selectedDisplayMode }
          onDisplayModeChange={ view.setDisplayMode }
        />
        { showIndexPanel && (
          <IndexPanel
            selectedPlot={ selectedPlot }
            selectedDate={ selectedDate }
            sourceId={ fieldSceneMode ? fieldScenesQ.data?.sourceId : effectiveSourceId }
            displayMode={ selectedDisplayMode }
            supportedIndices={ analyticsSupportedIndices }
            cloudMask={ cloudMask }
            selectedScene={ selectedFieldScene }
          />
        ) }
      </div>

      {/* Right: coordinate readout + map controls (lifted above the timeline) */ }
      <div className="absolute bottom-[calc(var(--timeline-height)+1.125rem)] right-4 z-toolbar flex flex-col items-end gap-2">
        <CoordinateReadout map={ map } />
        <MeasureTool
          activeTool={ activeMapTool }
          map={ map }
          onRequestTool={ requestMapTool }
          onReleaseTool={ releaseMapTool }
        />
        <CompareControl
          enabled={ compareEnabled }
          onEnabledChange={ view.setCompareEnabled }
          dates={ comparableDates }
          activeDate={ selectedDate }
          compareDate={ compareDate }
          onCompareDateChange={ view.setCompareDate }
          blend={ opacity }
          onBlendChange={ view.setOpacity }
        />
        <CloudMaskControl
          value={ cloudMask }
          onChange={ view.setCloudMask }
          disabled={ !fieldSceneMode }
        />
        <DownloadMenu
          hasSelectedField={ Boolean(selectedPlot) }
          selectedDate={ selectedDate }
          displayMode={ selectedDisplayMode }
        />
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

      {/* Bottom-left: legend (per display mode) + attribution, above the timeline */ }
      <div className="absolute bottom-[calc(var(--timeline-height)+1.125rem)] left-4 z-toolbar flex flex-col items-start gap-2">
        { visible && legendOpen && (
          <Legend displayMode={ selectedDisplayMode } sourceKind={ activeSourceKind } />
        ) }
        <div
          className="pointer-events-none max-w-[60vw] truncate text-[11px] text-foreground/70 on-map-text"
          data-testid="attribution"
        >
          { attribution } · { basemapCredit }
        </div>
      </div>

      {/* Bottom: temporal filmstrip */ }
      <div id="timeline-bar" className="absolute inset-x-0 bottom-0 z-panel px-2 pb-2">
        <TimelineBar
          dates={ activeTimelineDates }
          selectedDate={ selectedDate }
          onSelect={ view.setDate }
          sourceKind={ activeSourceKind }
          loading={ fieldSceneMode ? fieldScenesQ.isLoading : datesQ.isLoading }
          error={
            fieldSceneMode
              ? fieldScenesQ.isError ? messageFor(fieldScenesQ.error) : null
              : datesQ.isError ? messageFor(datesQ.error) : null
          }
          onRetry={ () => (fieldSceneMode ? fieldScenesQ.refetch() : datesQ.refetch()) }
          marginalNote={ marginalNote }
          nearestPassNote={ nearestPassNote }
          onPrefetchDate={ undefined }
        />
      </div>
    </div>
  );
}
