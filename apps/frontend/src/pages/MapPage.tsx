import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type maplibregl from 'maplibre-gl';
import { AlertTriangle, ChevronDown, ChevronUp, RefreshCw, Satellite, Search } from 'lucide-react';
import { ApiError, composeTileTemplate, getFieldIndexOverlayImage, getFieldIndexPoint, getFieldSarOverlayImage } from '@/lib/api';
import {
  useConfig,
  useCreateField,
  useDates,
  useBestObservations,
  useDefaultLayer,
  useDeleteField,
  useFields,
  useFieldMonitoringEvidence,
  useSources,
  useUpdateField,
} from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';
import { polygonAreaMeters } from '@/lib/measure';
import { radarSensorLabel } from '@/lib/radarEvidence';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import { selectEffectiveSourceId } from '@/lib/sourceSelection';
import type { SatelliteScene } from '@/lib/satelliteLayer';

import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { FIELD_BOUNDARY_FILL_LAYER_ID } from '@/components/fields/fieldBoundaryLayerHelpers';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { FieldOverlayLoadingIndicator } from '@/components/map/FieldOverlayLoadingIndicator';
import { MapLayerManager, type IndexOverlay } from '@/components/map/MapLayerManager';
import { MapControls } from '@/components/map/MapControls';
import { MeasureTool } from '@/components/map/MeasureTool';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { CommandPalette } from '@/components/map/CommandPalette';
import { CoordinateReadout } from '@/components/map/CoordinateReadout';
import { Legend } from '@/components/map/Legend';
import { LayerControlBar } from '@/components/layers/LayerControlBar';
import { TimelineBar } from '@/components/timeline/TimelineBar';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useMapView } from '@/state/useMapView';
import { useMapUrlState } from '@/hooks/useMapUrlState';
import type {
  CloudMaskOptions,
  Field,
  FieldUpdatePayload,
  GeoJsonPosition,
  ObservationCandidate,
  Plot,
  PlotGeometry,
  Source,
  FieldIndexPointResponse,
  ImageCorners,
} from '@/types/api';

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
      <div className="glass flex w-90 max-w-[90vw] flex-col items-start gap-3 p-6">
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

function toLngLat(position: GeoJsonPosition): [number, number] {
  return [position[0], position[1]];
}

function geometryCoordinates(geometry: PlotGeometry): [number, number][] {
  if (geometry.type === 'Polygon') {
    return geometry.coordinates.flat().map(toLngLat);
  }
  return geometry.coordinates.flat(2).map(toLngLat);
}

function focusPlot(map: maplibregl.Map | null, plot: Plot): void {
  const coordinates = geometryCoordinates(plot.geometry);
  if (!map || coordinates.length === 0) return;
  map.resize();
  const lngs = coordinates.map(([lng]) => lng);
  const lats = coordinates.map(([, lat]) => lat);
  map.fitBounds(
    [
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)],
    ],
    { padding: 64, maxZoom: 18, duration: 650 },
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

/** Recompute a field's area (hectares) from its outer ring — the Field API trusts
 *  the client-supplied area, so we derive it instead of sending a stale value. */
function fieldAreaHa(geometry: PlotGeometry): number {
  const ring =
    geometry.type === 'Polygon'
      ? geometry.coordinates[0] ?? []
      : geometry.coordinates[0]?.[0] ?? [];
  const meters = polygonAreaMeters(ring.map(([lng, lat]) => [lng, lat] as [number, number]));
  return meters / 10000;
}

interface ExportFeature {
  type: 'Feature';
  properties: { id: string; name: string; areaHa: number | null };
  geometry: PlotGeometry;
}

function fieldToFeature(field: Plot): ExportFeature {
  return {
    type: 'Feature',
    properties: { id: field.id, name: field.name, areaHa: field.areaHa ?? null },
    geometry: field.geometry,
  };
}

interface GeoJsonFeatureLike {
  type?: string;
  geometry?: PlotGeometry;
  properties?: { name?: string | null } | null;
  features?: GeoJsonFeatureLike[];
}

/** Pull polygon/multipolygon features out of a FeatureCollection, Feature, or raw
 *  geometry so an imported GeoJSON file can be turned into Field records. */
function extractImportFields(input: GeoJsonFeatureLike): { name: string; geometry: PlotGeometry }[] {
  const features: GeoJsonFeatureLike[] =
    input?.type === 'FeatureCollection'
      ? input.features ?? []
      : input?.type === 'Feature'
        ? [input]
        : [{ type: 'Feature', geometry: input as unknown as PlotGeometry, properties: null }];
  const result: { name: string; geometry: PlotGeometry }[] = [];
  features.forEach((feature, index) => {
    const geometry = feature?.geometry;
    if (geometry && (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon')) {
      const name = feature?.properties?.name?.trim() || `Imported field ${index + 1}`;
      result.push({ name, geometry });
    }
  });
  return result;
}

type LngLat = [number, number];

/** Lng/lat bounding-box corners (TL, TR, BR, BL) for a field's geometry —
 *  used to georeference the clipped index overlay image on the map. */
function geometryBboxCorners(geometry: Plot['geometry'] | undefined): ImageCorners | null {
  if (!geometry) return null;
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  const visit = (node: unknown): void => {
    if (Array.isArray(node) && typeof node[0] === 'number') {
      const [lng, lat] = node as LngLat;
      w = Math.min(w, lng);
      e = Math.max(e, lng);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    } else if (Array.isArray(node)) {
      node.forEach(visit);
    }
  };
  visit((geometry as { coordinates?: unknown }).coordinates);
  if (![w, s, e, n].every(Number.isFinite) || w === e || s === n) return null;
  return [
    [w, n],
    [e, n],
    [e, s],
    [w, s],
  ];
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

/** Derive a short sensor name from a source ID for provenance labels. */
function shortSensorName(sourceId: string): string {
  const id = sourceId.toLowerCase();
  if (id.includes('liss-4') || id.includes('liss4')) return 'LISS-4';
  if (id.includes('liss-3') || id.includes('liss3')) return 'LISS-3';
  if (id.includes('awifs')) return 'AWiFS';
  if (id.includes('sentinel-2') || id.includes('sentinel2')) return 'S2';
  if (id.includes('sentinel-1') || id.includes('sentinel1')) return 'S1';
  return sourceId;
}

/** Build a provenance label like `LISS-4 · 5.8 m` or `AWiFS · 56 m · coarse`. */
function provenanceLabelForCandidate(c: ObservationCandidate): string {
  const sensor = shortSensorName(c.sourceId);
  const res = c.resolutionMeters != null ? `${c.resolutionMeters} m` : null;
  const coarse = c.isCoarse ? 'coarse' : null;
  return [sensor, res, coarse].filter((x): x is string => x !== null).join(' · ');
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

function mapDisplayModesForSource(source: Source | null | undefined): string[] {
  const modes = source?.mapDisplayModes;
  if (modes && modes.length > 0) return modes;
  return source?.displayModes ?? [];
}

function defaultMapDisplayModeForSource(
  source: Source | null | undefined,
  fallback: string | null | undefined,
): string {
  return (
    source?.defaultMapDisplayMode ??
    source?.defaultDisplayMode ??
    mapDisplayModesForSource(source)[0] ??
    fallback ??
    'FCC'
  );
}

function resolveDisplayMode(
  requested: string | null | undefined,
  availableModes: string[],
  fallback: string,
): string {
  if (!requested) return fallback;
  const normalized = requested.trim().toUpperCase();
  return availableModes.find((mode) => mode.toUpperCase() === normalized) ?? fallback;
}

export default function MapPage({ hidePlotToolbar, simplifiedMapControls, topLeftCoords, showFullscreen }: { hidePlotToolbar?: boolean; simplifiedMapControls?: boolean; topLeftCoords?: boolean; showFullscreen?: boolean } = {}) {
  useMapUrlState();
  const configQ = useConfig();
  const sourcesQ = useSources();
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
    overlaysVisible,
    focusNonce,
    bestMode,
    radarEvidenceVisible,
  } = view;

  const effectiveSourceId = useMemo(
    () => selectEffectiveSourceId({
      activeSourceId,
      defaultSourceId: configQ.data?.defaultSourceId,
      sources: sourcesQ.data,
    }),
    [activeSourceId, configQ.data?.defaultSourceId, sourcesQ.data],
  );
  const defaultLayerQ = useDefaultLayer(effectiveSourceId);
  const selectedSource = useMemo(
    () => sourcesQ.data?.find((s) => s.id === effectiveSourceId),
    [sourcesQ.data, effectiveSourceId],
  );

  // Best-available observations query (only active in best mode).
  const bestObservationIndexType = displayModeOverride ?? configQ.data?.defaultIndex ?? undefined;
  const bestObsParams = useMemo(() => ({
    ...(periodFrom ? { startDate: periodFrom } : { lookbackDays: 92 }),
    ...(periodTo ? { endDate: periodTo } : {}),
    ...(bestObservationIndexType ? { indexType: bestObservationIndexType } : {}),
    useCase: 'field' as const,
    allowCoarse: false,
    maxCandidates: 30,
  }), [periodFrom, periodTo, bestObservationIndexType]);
  const bestObsQ = useBestObservations(bestObsParams, {
    enabled: bestMode && Boolean(selectedPlotId),
  });

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [basemapRuntimeError, setBasemapRuntimeError] = useState<Error | null>(null);
  const [preferHighRes] = useState(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [deleteFieldTarget, setDeleteFieldTarget] = useState<{
    id: string;
    name: string;
    onConfirm: () => Promise<void>;
  } | null>(null);

  const plotsQ = useFields();
  const createFieldMutation = useCreateField();
  const updateFieldMutation = useUpdateField();
  const deleteFieldMutation = useDeleteField();
  const navigate = useNavigate();

  const selectedPlot = useMemo(() => {
    if (!selectedPlotId) return null;
    return plotsQ.data?.find((plot) => plot.id === selectedPlotId) ?? null;
  }, [plotsQ.data, selectedPlotId]);
  const requestedTimelineIndex = resolveDisplayMode(
    displayModeOverride,
    selectedSource?.supportedIndices ?? [],
    selectedSource?.supportedIndices?.[0] ?? configQ.data?.defaultIndex ?? 'NDVI',
  );
  const datesQ = useDates(effectiveSourceId, {
    enabled: !bestMode && Boolean(selectedPlot),
    fieldId: selectedPlot?.id,
    indexType: requestedTimelineIndex,
  });
  useEffect(() => {
    if (!selectedPlotId || plotsQ.isLoading || !plotsQ.data) return;
    if (!plotsQ.data.some((plot) => plot.id === selectedPlotId)) {
      view.clearSelectedPlot();
    }
  }, [plotsQ.data, plotsQ.isLoading, selectedPlotId, view]);

  // Focus and select a field when the map loads or when the user navigates to a
  // specific field (e.g. from the season sheet Focus button). On initial load
  // the last-selected field (deep link / persisted state) wins; otherwise we fall
  // back to the first available field. FieldBoundaryLayer only draws the
  // *selected* field, so without this a fresh session lands on "No field selected"
  // and the drawn field is invisible even though it exists.
  const prevFocusedPlotId = useRef<string | null>(null);
  const prevFocusNonce = useRef(0);
  useEffect(() => {
    if (!map || plotsQ.isLoading || !plotsQ.data) return;
    if (!selectedPlotId) return;
    const focusTarget = selectedPlot;
    if (!focusTarget) return;
    const nonceBumped = focusNonce !== prevFocusNonce.current;
    if (!nonceBumped && prevFocusedPlotId.current === selectedPlotId) return;
    focusPlot(map, focusTarget);
    prevFocusedPlotId.current = selectedPlotId;
    prevFocusNonce.current = focusNonce;
  }, [map, plotsQ.isLoading, plotsQ.data, selectedPlot, selectedPlotId, focusNonce, view]);

  // Field boundary interactions on the map:
  //  - continuously reflect whether the pointer is over the field so the cursor is the
  //    EOS-style flat cursor (default arrow in analytics, pointer on the full map)
  //    instead of MapLibre's default grab hand.
  //  - clicking the field opens its analytics.
  // The cursor is driven from `mousemove` hit-testing rather than the layer's
  // `mouseenter`/`mouseleave` because those only fire on transitions: when the pointer
  // is already over the field as the boundary layer is (re)created — e.g. right after
  // navigating to or focusing a field — `mouseenter` never fires and the cursor would
  // stay a grab hand. Hit-testing every move keeps it correct with no lag.
  useEffect(() => {
    if (!map || !selectedPlotId) return;
    const canvas = map.getCanvas();
    const hoverCursor = simplifiedMapControls ? 'default' : 'pointer';

    const isOverField = (event: maplibregl.MapMouseEvent) => {
      if (!map.getLayer(FIELD_BOUNDARY_FILL_LAYER_ID)) return false;
      return (
        map.queryRenderedFeatures(event.point, {
          layers: [FIELD_BOUNDARY_FILL_LAYER_ID],
        }).length > 0
      );
    };

    const moveHandler = (e: maplibregl.MapMouseEvent) => {
      // While drawing/editing, let FieldDrawController own the cursor.
      if (fieldMode) return;
      canvas.style.cursor = isOverField(e) ? hoverCursor : '';
    };
    const leaveHandler = () => { canvas.style.cursor = ''; };
    const clickHandler = (e: maplibregl.MapMouseEvent) => {
      if (isOverField(e)) {
        navigate(`/monitoring/field-analytics/field/${selectedPlotId}`);
      }
    };
    map.on('mousemove', moveHandler);
    map.on('mouseout', leaveHandler);
    map.on('click', clickHandler);
    return () => {
      map.off('mousemove', moveHandler);
      map.off('mouseout', leaveHandler);
      map.off('click', clickHandler);
      canvas.style.cursor = '';
    };
  }, [map, selectedPlotId, navigate, simplifiedMapControls, fieldMode]);

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

  // Convert best-observation candidates to SceneDate objects with provenance labels.
  const bestTimelineDates = useMemo<import('@/types/api').SceneDate[] | undefined>(() => {
    if (!bestObsQ.data) return undefined;
    const byDate = new Map<string, import('@/types/api').SceneDate>();
    for (const c of bestObsQ.data.candidates) {
      if (byDate.has(c.acquisitionDate)) continue;
      byDate.set(c.acquisitionDate, {
        acquisitionDate: c.acquisitionDate,
        datetime: `${c.acquisitionDate}T00:00:00Z`,
        usablePixelPercent: c.usablePixelPercent,
        cloudMaskedPercent: c.cloudMaskedPercent,
        coveragePercent: c.coveragePercent,
        isLatestUsable: c.isLatestUsable,
        metricsProvisional: false,
        tileAvailable: c.tileAvailable,
        provenanceLabel: provenanceLabelForCandidate(c),
        resolvedSourceId: c.sourceId,
      });
    }
    return Array.from(byDate.values());
  }, [bestObsQ.data]);

  const activeTimelineDates = bestMode ? bestTimelineDates : datesQ.data;
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

  const monitoringEvidenceQ = useFieldMonitoringEvidence(selectedPlot?.id, {
    sourceId: effectiveSourceId,
    indexType: requestedTimelineIndex,
    targetDate: selectedDate,
    enabled: selectedSource?.productRole !== 'support',
  });

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
  const requestSourceId = bestMode && selectedDateMetadata?.resolvedSourceId
    ? selectedDateMetadata.resolvedSourceId
    : effectiveSourceId;
  const requestSource = useMemo(
    () => sourcesQ.data?.find((s) => s.id === requestSourceId),
    [sourcesQ.data, requestSourceId],
  );
  const displaySource = bestMode ? requestSource : selectedSource;

  const sourceDisplayModes = displaySource?.displayModes ?? ['FCC'];
  const sourceMapDisplayModes = mapDisplayModesForSource(displaySource);
  const defaultMapDisplayMode = defaultMapDisplayModeForSource(
    displaySource,
    defaultLayerQ.data && defaultLayerQ.data.sourceId === requestSourceId
      ? defaultLayerQ.data.defaultMapDisplayMode ?? defaultLayerQ.data.displayMode ?? null
      : null,
  );
  const selectedDisplayMode = resolveDisplayMode(
    displayModeOverride ?? displaySource?.displayMode ?? null,
    sourceMapDisplayModes.length > 0 ? sourceMapDisplayModes : sourceDisplayModes,
    defaultMapDisplayMode,
  );

  useEffect(() => {
    if (!selectedSource || !displayModeOverride) return;
    if (displayModeOverride !== selectedDisplayMode) {
      view.setDisplayMode(selectedDisplayMode);
    }
  }, [displayModeOverride, selectedDisplayMode, selectedSource, view]);

  // EOS-style: when an index layer is selected, hide the full-scene Akasha raster so
  // the basemap satellite imagery shows AROUND the field, and paint the colorized
  // index ONLY inside the field via a clipped overlay image.
  const isIndexLayer = (displaySource?.supportedIndices ?? []).includes(selectedDisplayMode);

  const scene = useMemo<SatelliteScene | null>(() => {
    if (!selectedDate || !requestSourceId) return null;
    // Index layers render via the field-clipped overlay, not a full-scene raster.
    if (isIndexLayer) return null;
    const dl = defaultLayerQ.data;
    const isDefault =
      dl &&
      dl.sourceId === requestSourceId &&
      dl.acquisitionDate === selectedDate &&
      (dl.displayMode ?? 'FCC') === selectedDisplayMode;
    const dateBounds = selectedDateMetadata?.bounds;
    if (isDefault && dl.tileUrlTemplate) {
      return {
        tileUrlTemplate: dl.tileUrlTemplate,
        bounds: dl.bounds ?? dateBounds,
        minzoom: dl.minzoom,
        maxzoom: dl.maxzoom,
        attribution: displaySource?.attribution ?? dl.attribution,
      };
    }
    return {
      tileUrlTemplate: composeTileTemplate(requestSourceId, selectedDate, selectedDisplayMode),
      bounds: dateBounds,
      minzoom: dl?.minzoom,
      maxzoom: dl?.maxzoom,
      attribution:
        displaySource?.attribution ??
        (dl?.sourceId === requestSourceId ? dl.attribution : undefined),
    };
  }, [
    selectedDate,
    requestSourceId,
    isIndexLayer,
    defaultLayerQ.data,
    selectedDateMetadata,
    selectedDisplayMode,
    displaySource?.attribution,
  ]);

  // Compare ("B") scene: same source + display mode, a different acquisition date.
  // Rendered beneath A; the opacity slider blends A over B.
  const sceneB = useMemo<SatelliteScene | null>(() => {
    if (!visible || !compareEnabled || !compareDate) return null;
    if (compareDate === selectedDate) return null;
    if (!requestSourceId) return null;
    if (isIndexLayer) return null;
    const meta = (bestMode ? activeTimelineDates : datesQ.data)?.find(
      (d) => d.acquisitionDate === compareDate,
    );
    if (!meta?.tileAvailable) return null;
    const compareSourceId = bestMode && meta.resolvedSourceId ? meta.resolvedSourceId : requestSourceId;
    const compareSource = sourcesQ.data?.find((s) => s.id === compareSourceId);
    return {
      tileUrlTemplate: composeTileTemplate(compareSourceId, compareDate, selectedDisplayMode),
      bounds: meta?.bounds,
      minzoom: defaultLayerQ.data?.minzoom,
      maxzoom: defaultLayerQ.data?.maxzoom,
      attribution: compareSource?.attribution ?? displaySource?.attribution,
    };
  }, [
    bestMode,
    activeTimelineDates,
    compareEnabled,
    compareDate,
    visible,
    requestSourceId,
    isIndexLayer,
    selectedDate,
    selectedDisplayMode,
    datesQ.data,
    defaultLayerQ.data,
    sourcesQ.data,
    displaySource?.attribution,
  ]);

  const requestedIndexOverlay = useMemo(() => {
    if (!isIndexLayer || !selectedPlot || !selectedDate || !requestSourceId) return null;
    const corners = geometryBboxCorners(selectedPlot.geometry);
    if (!corners) return null;
    return {
      plotId: selectedPlot.id,
      sourceId: requestSourceId,
      acquisitionDate: selectedDate,
      indexType: selectedDisplayMode,
      fallbackCoordinates: corners,
    };
  }, [isIndexLayer, selectedPlot, selectedDate, requestSourceId, selectedDisplayMode]);

  const [indexOverlay, setIndexOverlay] = useState<IndexOverlay | null>(null);
  const [indexOverlayRequestKey, setIndexOverlayRequestKey] = useState<string | null>(null);
  const [indexOverlayLoading, setIndexOverlayLoading] = useState(false);
  const requestedIndexOverlayKey = requestedIndexOverlay
    ? [
      requestedIndexOverlay.plotId,
      requestedIndexOverlay.sourceId,
      requestedIndexOverlay.acquisitionDate,
      requestedIndexOverlay.indexType,
    ].join('|')
    : null;
  const hasCurrentIndexOverlay = Boolean(
    indexOverlay && requestedIndexOverlayKey === indexOverlayRequestKey,
  );

  const [radarOverlay, setRadarOverlay] = useState<IndexOverlay | null>(null);
  const radarEvidence = monitoringEvidenceQ.data?.radar;
  useEffect(() => {
    let disposed = false;
    if (
      !radarEvidenceVisible ||
      radarEvidence?.status !== 'AVAILABLE' ||
      !selectedPlot ||
      !monitoringEvidenceQ.data?.targetDate
    ) {
      setRadarOverlay((current) => {
        if (current?.url.startsWith('blob:')) URL.revokeObjectURL(current.url);
        return null;
      });
      return;
    }
    const corners = geometryBboxCorners(selectedPlot.geometry);
    if (!corners) return;
    void getFieldSarOverlayImage(
      selectedPlot.id,
      monitoringEvidenceQ.data.targetDate,
      corners,
      radarEvidence.sourceId,
    ).then((overlay) => {
      if (disposed) {
        if (overlay.url.startsWith('blob:')) URL.revokeObjectURL(overlay.url);
        return;
      }
      setRadarOverlay((current) => {
        if (current?.url.startsWith('blob:')) URL.revokeObjectURL(current.url);
        return overlay;
      });
    }).catch(() => {
      if (!disposed) setRadarOverlay(null);
    });
    return () => { disposed = true; };
  }, [monitoringEvidenceQ.data?.targetDate, radarEvidence?.sourceId, radarEvidence?.status, radarEvidenceVisible, selectedPlot]);

  useEffect(() => {
    let disposed = false;
    if (!requestedIndexOverlay) {
      setIndexOverlayLoading(false);
      setIndexOverlayRequestKey(null);
      setIndexOverlay((current) => {
        if (current?.url.startsWith('blob:')) URL.revokeObjectURL(current.url);
        return null;
      });
      return;
    }
    setIndexOverlay((current) => {
      if (current?.url.startsWith('blob:')) URL.revokeObjectURL(current.url);
      return null;
    });
    setIndexOverlayRequestKey(null);
    setIndexOverlayLoading(true);
    void getFieldIndexOverlayImage(
      requestedIndexOverlay.plotId,
      {
        sourceId: requestedIndexOverlay.sourceId,
        acquisitionDate: requestedIndexOverlay.acquisitionDate,
        indexType: requestedIndexOverlay.indexType,
        preferHighRes,
      },
      requestedIndexOverlay.fallbackCoordinates,
    ).then((overlay) => {
      if (disposed) {
        if (overlay.url.startsWith('blob:')) URL.revokeObjectURL(overlay.url);
        return;
      }
      setIndexOverlayLoading(false);
      setIndexOverlayRequestKey(requestedIndexOverlayKey);
      setIndexOverlay((current) => {
        if (current?.url.startsWith('blob:')) URL.revokeObjectURL(current.url);
        return overlay;
      });
    }).catch(() => {
      if (!disposed) {
        setIndexOverlayLoading(false);
        setIndexOverlayRequestKey(null);
        setIndexOverlay(null);
      }
    });
    return () => {
      disposed = true;
    };
  }, [requestedIndexOverlay, requestedIndexOverlayKey, preferHighRes]);

  const indexLookup = useCallback(async ({ lng, lat }: { lng: number; lat: number }): Promise<FieldIndexPointResponse | null> => {
    if (!isIndexLayer || !hasCurrentIndexOverlay || !selectedPlot || !selectedDate || !requestSourceId) return null;
    return getFieldIndexPoint(selectedPlot.id, {
      sourceId: requestSourceId,
      acquisitionDate: selectedDate,
      indexType: selectedDisplayMode,
      lng,
      lat,
      preferHighRes,
    });
  }, [
    isIndexLayer,
    hasCurrentIndexOverlay,
    selectedPlot,
    selectedDate,
    requestSourceId,
    selectedDisplayMode,
    preferHighRes,
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
    if (
      monitoringEvidenceQ.data?.optical?.status !== 'usable' &&
      radarEvidence?.status === 'AVAILABLE' &&
      radarEvidence.acquisitionDate
    ) {
      const offset = radarEvidence.daysFromTarget == null
        ? ''
        : ` · ${Math.abs(radarEvidence.daysFromTarget)} day offset`;
      const sensor = radarSensorLabel(radarEvidence.sourceId);
      return `${sensor} support: ${radarEvidence.acquisitionDate}${offset} · radar evidence, not NDVI or direct soil moisture.`;
    }
    if (selectedSource?.kind !== 'sar') return null;
    if (!selectedDate) return null;
    return `Nearest radar pass: ${selectedDate}.`;
  }, [monitoringEvidenceQ.data?.optical?.status, radarEvidence, selectedSource?.kind, selectedDate]);

  const radarEventDates = useMemo(() => {
    if (radarEvidence?.status !== 'AVAILABLE') return [];
    return Array.from(new Set([
      ...(radarEvidence.acquisitionDate ? [radarEvidence.acquisitionDate] : []),
      ...(radarEvidence.history ?? []).map((observation) => observation.acquisitionDate),
    ])).sort((a, b) => b.localeCompare(a));
  }, [radarEvidence]);

  const requestMapTool = (owner: MapToolOwner): boolean => {
    setActiveMapTool(owner);
    return true;
  };

  // Activate draw mode when Global View "Add field" button sets pendingAction
  useEffect(() => {
    if (view.pendingAction === 'create-field') {
      view.setPendingAction(null);
      if (map) {
        requestMapTool('field-draw');
        setFieldMode('draw');
      }
    }
  }, [view, view.pendingAction, map]);

  const releaseMapTool = (owner: MapToolOwner) => {
    setActiveMapTool((current) => (current === owner ? null : current));
  };

  // In best mode, the backend-resolved source lives on the selected date metadata.
  // Do not mutate activeSourceId: it is the user's source-specific timeline choice.
  const handleBestDateSelect = useCallback((acquisitionDate: string) => {
    const candidate = bestObsQ.data?.candidates.find(
      (c) => c.acquisitionDate === acquisitionDate,
    );
    if (!candidate) return;
    view.setDate(candidate.acquisitionDate);
  }, [bestObsQ.data, view]);

  const importGeoJsonFile = async (file: File) => {
    const text = await file.text();
    const parsed = JSON.parse(text) as GeoJsonFeatureLike;
    const fields = extractImportFields(parsed);
    let firstCreated: Field | null = null;
    for (const field of fields) {
      const created = await createFieldMutation.mutateAsync({
        name: field.name,
        geometry: field.geometry,
        areaHa: fieldAreaHa(field.geometry),
        seasonIds: [],
      });
      firstCreated ??= created;
    }
    if (firstCreated) {
      view.setSelectedPlotId(firstCreated.id);
      focusPlot(map, firstCreated);
    }
  };

  const exportGeoJson = () => {
    const data = selectedPlot
      ? fieldToFeature(selectedPlot)
      : {
        type: 'FeatureCollection' as const,
        features: (plotsQ.data ?? []).map(fieldToFeature),
      };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/geo+json' });
    downloadBlob(blob, geoJsonFilename(selectedPlot));
  };

  const deleteSelectedField = () => {
    if (!selectedPlot) return;
    setDeleteFieldTarget({
      id: selectedPlot.id,
      name: selectedPlot.name,
      onConfirm: async () => {
        await deleteFieldMutation.mutateAsync(selectedPlot.id);
        view.clearSelectedPlot();
      },
    });
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
  const attribution =
    scene?.attribution ??
    (radarEvidenceVisible && radarOverlay
      ? `ISRO/NRSC Bhoonidhi · ${radarSensorLabel(radarEvidence?.sourceId)} field support`
      : indexOverlay
      ? sourceAttribution
      : basemapResolution.basemapConfig.provider === 'osm'
        ? basemapResolution.basemapConfig.attribution
        : basemapResolution.basemapConfig.provider === 'esri'
          ? 'ArcGIS basemap'
          : sourceAttribution ?? 'Satellite imagery');
  const sourceSupportedIndices = displaySource?.supportedIndices ?? config.supportedIndices;
  const analyticsSupportedIndices = sourceSupportedIndices;
  const sourceAnalysisLevel = displaySource?.analysisLevel ?? 'field';
  const analyticsEnabled =
    displaySource?.kind !== 'sar' &&
    sourceAnalysisLevel === 'field' &&
    sourceSupportedIndices.length > 0;
  const exportIndexType = analyticsSupportedIndices.includes(selectedDisplayMode)
    ? selectedDisplayMode
    : analyticsSupportedIndices[0] ?? config.defaultIndex ?? 'NDVI';
  return (
    <div className="relative h-full w-full overflow-hidden bg-background" data-testid="map-page">
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
        indexOverlay={ radarEvidenceVisible && radarOverlay ? radarOverlay : indexOverlay }
        opacity={ opacity / 100 }
        visible={ visible }
        onBasemapError={ setBasemapRuntimeError }
        onMapReady={ setMap }
      />
      <FieldOverlayLoadingIndicator
        loading={ overlaysVisible && ((isIndexLayer && indexOverlayLoading) || (radarEvidenceVisible && radarEvidence?.status === 'AVAILABLE' && !radarOverlay)) }
        map={ map }
        plot={ selectedPlot }
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
          const created = await createFieldMutation.mutateAsync({
            name: payload.name,
            geometry: payload.geometry,
            areaHa: fieldAreaHa(payload.geometry),
            seasonIds: [],
          });
          view.setSelectedPlotId(created.id);
          focusPlot(map, created);
          return created;
        } }
        onUpdateField={ async (plotId, payload) => {
          const fieldPayload: FieldUpdatePayload = {
            name: payload.name ?? null,
            geometry: payload.geometry ?? null,
            areaHa: payload.geometry ? fieldAreaHa(payload.geometry) : null,
          };
          const updated = await updateFieldMutation.mutateAsync({
            fieldId: plotId,
            payload: fieldPayload,
          });
          view.setSelectedPlotId(updated.id);
          focusPlot(map, updated);
          return updated;
        } }
        onRequestTool={ requestMapTool }
        onReleaseTool={ releaseMapTool }
        onPolygonComplete={ (geometry) => setDraftGeometry(geometry) }
        className="absolute right-4 top-70 z-popover max-[760px]:right-4 max-[760px]:top-150"
      />

      { !overlaysVisible && (
        <div className="pointer-events-auto absolute left-4 top-4 z-toolbar flex items-center gap-2">
          <div className="glass flex items-center justify-center rounded-md px-2 py-2 shadow-e2">
            <Satellite className="size-4 text-primary" strokeWidth={ 1.75 } aria-hidden="true" />
          </div>
          <button
            type="button"
            onClick={ () => setCommandOpen(true) }
            className="glass flex h-9 w-64 items-center gap-2 rounded-md px-3 text-left text-[13px] text-muted-foreground/70 shadow-e2 transition-colors duration-fast ease-standard hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Search className="size-3.5 shrink-0" strokeWidth={ 1.75 } />
            <span>Search location</span>
          </button>
        </div>
      ) }

      { overlaysVisible && <CommandPalette
        open={ commandOpen }
        onOpenChange={ setCommandOpen }
        sources={ sourcesQ.data }
        activeSourceId={ effectiveSourceId }
        dates={ datesQ.data }
        onSelectSource={ view.setSource }
        onSelectDate={ view.setDate }
        onToggleLayers={ view.toggleLayers }
      /> }

      { overlaysVisible && (
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
      ) }

      {/* Left: field tools */ }
      { overlaysVisible && (
        <div className="absolute left-4 top-17 z-toolbar flex flex-col gap-2">
          { !hidePlotToolbar && <PlotToolbar
            activeAction={ fieldMode === 'draw' ? 'draw' : null }
            hasSelectedField={ Boolean(selectedPlot) }
            isMapAvailable={ Boolean(map) }
            onDrawField={ () => {
              requestMapTool('field-draw');
              setFieldMode((current) => (current === 'draw' ? null : 'draw'));
            } }
            onEditSelectedField={ () => {
              requestMapTool('field-edit');
              setFieldMode((current) => (current === 'edit' ? null : 'edit'));
            } }
            onImportGeoJSON={ () => undefined }
            onExportGeoJSON={ () => void exportGeoJson() }
            onDeleteSelectedField={ () => void deleteSelectedField() }
            selectedFieldName={ selectedPlot?.name }
          /> }
        </div>) }

      { overlaysVisible && topLeftCoords && (
        <div className="pointer-events-none absolute inset-0 z-popover">
          <CoordinateReadout
            map={ map }
            interactiveLayerId={ FIELD_BOUNDARY_FILL_LAYER_ID }
            indexLookup={
              isIndexLayer && hasCurrentIndexOverlay && selectedPlot && selectedDate && requestSourceId
                ? indexLookup
                : undefined
            }
          />
        </div>
      ) }

      { overlaysVisible && <div className="absolute bottom-[calc(var(--timeline-height)+2.5rem)] right-4 z-toolbar flex flex-col items-end gap-2">
        <LayerControlBar
          sources={ sourcesQ.data }
          activeSourceId={ effectiveSourceId }
          onSelectSource={ view.setSource }
          displayModes={ sourceMapDisplayModes.length > 0 ? sourceMapDisplayModes : sourceDisplayModes }
          displayMode={ selectedDisplayMode }
          onDisplayModeChange={ view.setDisplayMode }
          cloudMask={ cloudMask }
          onCloudMaskChange={ view.setCloudMask }
          cloudMaskDisabled={ !analyticsEnabled || !selectedSource?.availableMaskOptions?.length }
          compareAvailable={ !isIndexLayer }
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
          exportSourceId={ requestSourceId }
          exportIndexType={ exportIndexType }
          exportCloudMask={ effectiveCloudMask }
          analyticsEnabled={ analyticsEnabled }
          collapsed={ view.layerBarCollapsed }
          onCollapsedChange={ view.setLayerBarCollapsed }
        />
      </div> }

      {/* Left: legend + navigation map controls (zoom / compass / locate / fullscreen),
        * stacked in a single bottom-left column so they never overlap each other.
        * Raised above the attribution line so the two never collide at any width. */ }
      <div className="absolute left-4 bottom-[calc(var(--timeline-height)+2.5rem)] z-toolbar flex flex-col items-start gap-2">
        { overlaysVisible && <MeasureTool
          activeTool={ activeMapTool }
          map={ map }
          onRequestTool={ requestMapTool }
          onReleaseTool={ releaseMapTool }
        /> }
        { overlaysVisible && !simplifiedMapControls && visible && legendOpen && (scene || indexOverlay) && (
          <Legend displayMode={ selectedDisplayMode } sourceKind={ activeSourceKind } resolvedResolutionMeters={ indexOverlay?.resolutionMeters } resolvedSourceId={ indexOverlay?.resolvedSourceId } />
        ) }
        <MapControls
          map={ map }
          hasSelectedField={ Boolean(selectedPlot) }
          legendOpen={ legendOpen }
          onFindSelectedField={ () => {
            if (selectedPlot) focusPlot(map, selectedPlot);
          } }
          onLegendOpenChange={ view.setLegendOpen }
          simplified={ simplifiedMapControls }
        />
      </div>

      { overlaysVisible && (
        <div
          className="pointer-events-none absolute bottom-[calc(var(--timeline-height)+0.5rem)] left-4 z-toolbar max-w-[calc(100vw-2rem)] truncate rounded-sm bg-[hsl(var(--panel)/0.55)] px-1.5 py-0.5 text-[11px] text-foreground/80 backdrop-blur-sm"
          data-testid="attribution"
        >
          { attribution }
        </div>
      ) }

      {/* Field-quality timeline appears only after a persisted field is selected. */ }
      { selectedPlot && (
      <div className="absolute inset-x-0 bottom-0 z-panel flex items-stretch gap-2 px-2 pb-2">
        <div id="timeline-bar" className="min-w-0 flex-1">
          <TimelineBar
            dates={ activeTimelineDates }
            selectedDate={ selectedDate }
            onSelect={ bestMode ? handleBestDateSelect : view.setDate }
            sourceKind={ bestMode ? undefined : activeSourceKind }
            sensorBadge={ bestMode ? null : sensorBadgeForSource(selectedSource) }
            nextExpectedAcquisitionDate={
              !bestMode && defaultLayerQ.data?.sourceId === effectiveSourceId
                ? (defaultLayerQ.data?.nextExpectedAcquisitionDate ?? null)
                : null
            }
            loading={ bestMode ? bestObsQ.isLoading : datesQ.isLoading }
            error={
              bestMode
                ? (bestObsQ.isError ? messageFor(bestObsQ.error) : null)
                : (datesQ.isError ? messageFor(datesQ.error) : null)
            }
            onRetry={ bestMode ? () => void bestObsQ.refetch() : () => void datesQ.refetch() }
            marginalNote={ bestMode ? null : marginalNote }
            nearestPassNote={ bestMode ? null : nearestPassNote }
            radarEventDates={ bestMode ? [] : radarEventDates }
            onPrefetchDate={ undefined }
            periodFrom={ periodFrom }
            periodTo={ periodTo }
            onPeriodChange={ view.setPeriod }
            bestMode={ bestMode }
            onBestModeChange={ view.setBestMode }
            compact
          />
        </div>

        { overlaysVisible && showFullscreen && (
          /* Analytics drawer toggle — same height as the timeline bar. When the drawer is
           * closed the map is fullscreen; opening it reveals the analytics panel below. */
          <div className="glass flex shrink-0 w-12 items-center justify-center rounded-md shadow-e2 min-h-[var(--timeline-height)]">
            <button
              type="button"
              aria-label={ view.mapFullscreen ? 'Show analytics' : 'Hide analytics' }
              aria-expanded={ !view.mapFullscreen }
              title={ view.mapFullscreen ? 'Show analytics' : 'Hide analytics' }
              data-testid="analytics-drawer-toggle"
              onClick={ () => view.setMapFullscreen(!view.mapFullscreen) }
              className="flex items-center justify-center text-foreground/80 transition-colors duration-fast hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring size-full"
            >
              { view.mapFullscreen ? (
                <ChevronUp className="size-4" strokeWidth={ 1.75 } />
              ) : (
                <ChevronDown className="size-4" strokeWidth={ 1.75 } />
              ) }
            </button>
          </div>
        ) }
      </div>
      ) }

      <AlertDialogRoot
        open={ !!deleteFieldTarget }
        onOpenChange={ (open) => { if (!open) setDeleteFieldTarget(null); } }
      >
        <AlertDialogContent>
          <AlertDialogTitle>Delete field?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete "{ deleteFieldTarget?.name }"? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ async () => {
              if (!deleteFieldTarget) return;
              try {
                await deleteFieldTarget.onConfirm();
              } catch {
                // error handled by query state
              }
              setDeleteFieldTarget(null);
            } }>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </div>
  );
}
