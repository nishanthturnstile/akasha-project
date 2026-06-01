import { useMemo, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { AlertTriangle, RefreshCw, Satellite } from 'lucide-react';
import { ApiError, composeTileTemplate } from '@/lib/api';
import { useConfig, useDates, useDefaultLayer, useSources } from '@/lib/queries';
import { basemapAttribution, resolveBasemapStyle } from '@/map/basemap';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import type { SatelliteScene } from '@/lib/satelliteLayer';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { MapControls } from '@/components/map/MapControls';
import { LayerPanel } from '@/components/layers/LayerPanel';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { IndexPanel } from '@/components/scaffold/IndexPanel';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

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

  const [sourceOverride, setSourceOverride] = useState<string | undefined>(undefined);
  const effectiveSourceId = sourceOverride ?? sourcesQ.data?.[0]?.id;
  const datesQ = useDates(effectiveSourceId);

  const [dateOverride, setDateOverride] = useState<string | null>(null);
  const [visible, setVisible] = useState(true);
  const [opacity, setOpacity] = useState(100); // percent
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  // Effective acquisition date: keep a still-valid user choice, otherwise the
  // computed default (latest usable -> threshold -> newest). Derived, not stored,
  // so we never call setState inside an effect.
  const selectedDate = useMemo<string | null>(() => {
    if (!datesQ.data || !configQ.data) return null;
    if (dateOverride && datesQ.data.some((d) => d.acquisitionDate === dateOverride)) {
      return dateOverride;
    }
    const def = selectDefaultDate(datesQ.data, configQ.data.usablePixelThresholdPercent);
    return def ? def.acquisitionDate : null;
  }, [datesQ.data, configQ.data, dateOverride]);

  const handleSourceChange = (id: string) => {
    setSourceOverride(id);
    setDateOverride(null); // let the new source recompute its default date
  };

  const basemapStyle = useMemo(() => resolveBasemapStyle(configQ.data), [configQ.data]);

  const selectedDateMetadata = useMemo(
    () => datesQ.data?.find((d) => d.acquisitionDate === selectedDate) ?? null,
    [datesQ.data, selectedDate],
  );

  const scene = useMemo<SatelliteScene | null>(() => {
    if (!selectedDate || !effectiveSourceId) return null;
    const dl = defaultLayerQ.data;
    const isDefault =
      dl && dl.sourceId === effectiveSourceId && dl.acquisitionDate === selectedDate;
    const dateBounds = selectedDateMetadata?.bounds;
    if (isDefault) {
      return {
        tileUrlTemplate: dl.tileUrlTemplate,
        bounds: dl.bounds ?? dateBounds,
        minzoom: dl.minzoom,
        maxzoom: dl.maxzoom,
        attribution: dl.attribution,
      };
    }
    return {
      tileUrlTemplate: composeTileTemplate(effectiveSourceId, selectedDate),
      bounds: dateBounds,
      minzoom: dl?.minzoom,
      maxzoom: dl?.maxzoom,
      attribution: dl?.attribution,
    };
  }, [selectedDate, effectiveSourceId, defaultLayerQ.data, selectedDateMetadata]);

  // Marginal/empty signal: no date meets the usability threshold.
  const marginalNote = useMemo<string | null>(() => {
    if (!datesQ.data || datesQ.data.length === 0 || !configQ.data) return null;
    const threshold = configQ.data.usablePixelThresholdPercent;
    const qualifies = datesQ.data.some(
      (d) => d.isLatestUsable || (d.usablePixelPercent != null && d.usablePixelPercent >= threshold),
    );
    if (qualifies) return null;
    return `No usable optical scene in range. Showing the most recent attempt (${datesQ.data[0].acquisitionDate}).`;
  }, [datesQ.data, configQ.data]);

  if (configQ.isLoading) return <FullScreenLoading />;
  if (configQ.isError || !configQ.data) {
    return <FullScreenError message={ messageFor(configQ.error) } onRetry={ () => configQ.refetch() } />;
  }

  const config = configQ.data;
  const attribution = scene?.attribution ?? 'Copernicus Sentinel-2';
  const basemapCredit = basemapAttribution(configQ.data);

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-background" data-testid="map-page">
      <MapLayerManager
        basemapStyle={ basemapStyle }
        center={ config.aoi.center }
        zoom={ config.aoi.zoom }
        scene={ scene }
        opacity={ opacity / 100 }
        visible={ visible }
        onMapReady={ setMap }
      />

      {/* Top-left: plot tools (Phase 5 placeholder) */ }
      <div className="absolute left-4 top-4 z-20">
        <PlotToolbar />
      </div>

      {/* Top-center: brand wordmark */ }
      <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2">
        <div
          className="glass flex items-center gap-2 rounded-pill px-3.5 py-1.5"
          data-testid="brand-mark"
        >
          <Satellite className="size-4 text-primary" strokeWidth={ 1.75 } />
          <span className="font-display text-[15px] font-semibold tracking-[-0.01em]">
            { config.appName }
          </span>
          <span className="hidden text-[12px] text-muted-foreground sm:inline">
            · { config.aoi.name }
          </span>
        </div>
      </div>

      {/* Top-right: theme toggle */ }
      <div className="absolute right-4 top-4 z-20">
        <ThemeToggle />
      </div>

      {/* Left: layer panel */ }
      <div className="absolute left-4 top-[76px] z-20">
        <LayerPanel
          sources={ sourcesQ.data }
          selectedSourceId={ effectiveSourceId }
          onSourceChange={ handleSourceChange }
          dates={ datesQ.data }
          datesLoading={ datesQ.isLoading }
          datesError={ datesQ.isError ? messageFor(datesQ.error) : null }
          onDatesRetry={ () => datesQ.refetch() }
          selectedDate={ selectedDate }
          onDateSelect={ setDateOverride }
          visible={ visible }
          onVisibleChange={ setVisible }
          opacity={ opacity }
          onOpacityChange={ setOpacity }
          marginalNote={ marginalNote }
        />
      </div>

      {/* Right: index panel (Phase 5 placeholder) */ }
      <div className="absolute right-4 top-[76px] z-10 hidden xl:block">
        <IndexPanel />
      </div>

      {/* Bottom-right: map controls */ }
      <div className="absolute bottom-8 right-4 z-20">
        <MapControls map={ map } />
      </div>

      {/* Bottom-left: attribution (muted, on-map) */ }
      <div
        className="pointer-events-none absolute bottom-7 left-3 z-20 max-w-[60vw] truncate text-[11px] text-foreground/70 on-map-text"
        data-testid="attribution"
      >
        { attribution } · { basemapCredit }
      </div>
    </div>
  );
}
