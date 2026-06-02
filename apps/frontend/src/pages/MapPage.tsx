import { useEffect, useMemo, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { AlertTriangle, RefreshCw, Satellite } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, composeTileTemplate, getDates } from '@/lib/api';
import { queryKeys, useConfig, useDates, useDefaultLayer, useSources } from '@/lib/queries';
import { basemapAttribution, resolveBasemapStyle } from '@/map/basemap';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import type { SatelliteScene } from '@/lib/satelliteLayer';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { MapControls } from '@/components/map/MapControls';
import { MeasureTool } from '@/components/map/MeasureTool';
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
  } = view;

  const effectiveSourceId = activeSourceId ?? sourcesQ.data?.[0]?.id;
  const datesQ = useDates(effectiveSourceId);
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((s) => s.id === effectiveSourceId),
    [sourcesQ.data, effectiveSourceId],
  );

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);

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

  // Effective acquisition date: keep a still-valid user choice, otherwise the
  // computed default (latest usable -> threshold -> newest). Derived, not stored,
  // so we never call setState inside an effect.
  const selectedDate = useMemo<string | null>(() => {
    if (!datesQ.data || !configQ.data) return null;
    if (dateOverride && datesQ.data.some((d) => d.acquisitionDate === dateOverride)) {
      return dateOverride;
    }
    const def = selectDefaultDate(datesQ.data, configQ.data.usablePixelThresholdPercent, {
      sourceKind: selectedSource?.kind,
    });
    return def ? def.acquisitionDate : null;
  }, [datesQ.data, configQ.data, dateOverride, selectedSource?.kind]);

  const basemapStyle = useMemo(() => resolveBasemapStyle(configQ.data), [configQ.data]);

  const selectedDateMetadata = useMemo(
    () => datesQ.data?.find((d) => d.acquisitionDate === selectedDate) ?? null,
    [datesQ.data, selectedDate],
  );

  const selectedDisplayMode =
    displayModeOverride ??
    selectedSource?.displayMode ??
    selectedSource?.defaultDisplayMode ??
    selectedSource?.displayModes?.[0] ??
    (defaultLayerQ.data && defaultLayerQ.data.sourceId === effectiveSourceId
      ? defaultLayerQ.data.displayMode
      : undefined) ??
    'RGB';

  const scene = useMemo<SatelliteScene | null>(() => {
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
    defaultLayerQ.data,
    selectedDateMetadata,
    selectedDisplayMode,
    selectedSource?.attribution,
  ]);

  // Compare ("B") scene: same source + display mode, a different acquisition date.
  // Rendered beneath A; the opacity slider blends A over B.
  const sceneB = useMemo<SatelliteScene | null>(() => {
    if (!visible || !compareEnabled || !compareDate || !effectiveSourceId) return null;
    if (compareDate === selectedDate) return null;
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
      (datesQ.data ?? [])
        .filter((d) => d.tileAvailable)
        .sort((a, b) => a.acquisitionDate.localeCompare(b.acquisitionDate)),
    [datesQ.data],
  );

  // Marginal/empty signal: no date meets the usability threshold.
  const marginalNote = useMemo<string | null>(() => {
    if (!datesQ.data || datesQ.data.length === 0 || !configQ.data) return null;
    if (selectedSource?.kind === 'sar') return null;
    const threshold = configQ.data.usablePixelThresholdPercent;
    const qualifies = datesQ.data.some(
      (d) => d.isLatestUsable || (d.usablePixelPercent != null && d.usablePixelPercent >= threshold),
    );
    if (qualifies) return null;
    const newest = [...datesQ.data].sort((a, b) =>
      b.acquisitionDate.localeCompare(a.acquisitionDate),
    )[0];
    return `No usable optical scene in range. Showing the most recent attempt (${newest.acquisitionDate}).`;
  }, [datesQ.data, configQ.data, selectedSource?.kind]);

  // Nearest radar pass note (SAR), shown when the active pass isn't the canonical one.
  const nearestPassNote = useMemo<string | null>(() => {
    if (selectedSource?.kind !== 'sar') return null;
    if (effectiveSourceId !== 'sentinel-1-grd') return null;
    if (!selectedDate || selectedDate === '2026-04-27') return null;
    return `Nearest radar pass: ${selectedDate}.`;
  }, [selectedSource?.kind, effectiveSourceId, selectedDate]);

  const prefetchDates = (sourceId: string) => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.dates(sourceId),
      queryFn: () => getDates(sourceId),
    });
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
  const showIndexPanel = selectedSource?.kind !== 'sar' && sourceSupportedIndices.length > 0;

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-background" data-testid="map-page">
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

      {/* Top chrome: layers toggle · brand · theme */ }
      <TopBar
        appName={ config.appName }
        aoiName={ config.aoi.name }
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

      {/* Left: plot tools (Phase 5 placeholder) */ }
      <div className="absolute left-4 top-[68px] z-toolbar">
        <PlotToolbar />
      </div>

      {/* Layers surface — left drawer (≥md) / bottom sheet (<md) */ }
      <div className="absolute left-4 top-[112px]">
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

      {/* Right: index panel (Phase 5 placeholder) */ }
      <div className="absolute right-4 top-[68px] z-toolbar hidden xl:block">
        { showIndexPanel && <IndexPanel /> }
      </div>

      {/* Right: coordinate readout + map controls (lifted above the timeline) */ }
      <div className="absolute bottom-[7.75rem] right-4 z-toolbar flex flex-col items-end gap-2">
        <CoordinateReadout map={ map } />
        <MeasureTool map={ map } />
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
        <MapControls map={ map } />
      </div>

      {/* Bottom-left: legend (per display mode) + attribution, above the timeline */ }
      <div className="absolute bottom-[7.75rem] left-4 z-toolbar flex flex-col items-start gap-2">
        { visible && (
          <Legend displayMode={ selectedDisplayMode } sourceKind={ selectedSource?.kind } />
        ) }
        <div
          className="pointer-events-none max-w-[60vw] truncate text-[11px] text-foreground/70 on-map-text"
          data-testid="attribution"
        >
          { attribution } · { basemapCredit }
        </div>
      </div>

      {/* Bottom: temporal filmstrip */ }
      <div id="timeline-bar" className="absolute inset-x-0 bottom-0 z-panel px-3 pb-3">
        <TimelineBar
          dates={ datesQ.data }
          selectedDate={ selectedDate }
          onSelect={ view.setDate }
          sourceKind={ selectedSource?.kind }
          loading={ datesQ.isLoading }
          error={ datesQ.isError ? messageFor(datesQ.error) : null }
          onRetry={ () => datesQ.refetch() }
          marginalNote={ marginalNote }
          nearestPassNote={ nearestPassNote }
          onPrefetchDate={ undefined }
        />
      </div>
    </div>
  );
}
