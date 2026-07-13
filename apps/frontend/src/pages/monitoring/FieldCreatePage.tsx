import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { ArrowLeft, Circle, Loader2, Minus, Pencil, Plus, Scissors, Square, Trash2, Undo2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldDrawController, type DrawShapeMode, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { FieldThumbnail } from '@/components/fields/GlobalViewPanel';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { polygonAreaMeters } from '@/lib/measure';
import { useConfig, useCreateField, useFields, useSeasons, queryKeys } from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';
import lineIntersect from '@turf/line-intersect';
import type maplibregl from 'maplibre-gl';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import type { Field, GeoJsonPosition, PlotGeometry } from '@/types/api';
import type { TerraDraw, GeoJSONStoreGeometries } from 'terra-draw';
import CreateSeasonDialog from '@/components/seasons/CreateSeasonDialog';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';

interface PendingField {
  id: string;
  geometry: PlotGeometry;
  name: string;
}

let tempIdCounter = 0;
function nextTempId(): string {
  tempIdCounter += 1;
  return `pending-${tempIdCounter}`;
}

function toLngLatRing(ring: GeoJsonPosition[]): [number, number][] {
  return ring.map(([lng, lat]) => [lng, lat]);
}

function findEdgeIndex(p: [number, number], ring: GeoJsonPosition[]): number {
  let bestEdge = -1;
  let bestDist = 1e-6;
  for (let i = 0; i < ring.length - 1; i++) {
    const ax = ring[i][0], ay = ring[i][1];
    const bx = ring[i + 1][0], by = ring[i + 1][1];
    const dx = bx - ax, dy = by - ay;
    const len2 = dx * dx + dy * dy;
    if (len2 < 1e-12) continue;
    const t = Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / len2));
    const px = ax + t * dx, py = ay + t * dy;
    const dist = Math.hypot(p[0] - px, p[1] - py);
    if (dist < bestDist) { bestDist = dist; bestEdge = i; }
  }
  return bestEdge;
}

function splitPolygonByLine(
  polygonCoords: GeoJsonPosition[][],
  lineCoords: [number, number][],
): { ring1: GeoJsonPosition[][]; ring2: GeoJsonPosition[][] } | null {
  const intersections = lineIntersect(
    { type: 'LineString', coordinates: polygonCoords[0] },
    { type: 'LineString', coordinates: lineCoords },
  );
  console.log('[splitPolygonByLine] intersections found:', intersections.features.length);
  if (intersections.features.length < 2) {
    return null;
  }

  const pts: [number, number][] = [];
  for (const f of intersections.features) {
    const c = f.geometry.coordinates as [number, number];
    if (!pts.some((p) => Math.abs(p[0] - c[0]) < 1e-8 && Math.abs(p[1] - c[1]) < 1e-8)) {
      pts.push(c);
    }
    if (pts.length === 2) break;
  }
  if (pts.length < 2) return null;

  const [A, B] = pts;
  const ring = polygonCoords[0];
  const edgeA = findEdgeIndex(A, ring);
  const edgeB = findEdgeIndex(B, ring);
  if (edgeA < 0 || edgeB < 0 || edgeA === edgeB) return null;

  const advance = (i: number) => (i + 1) % (ring.length - 1);

  // Ring 1: walk from edgeA to edgeB, including ring[edgeB]
  const ring1Coords: GeoJsonPosition[] = [A];
  let idx = advance(edgeA);
  for (; ;) {
    ring1Coords.push(ring[idx]);
    if (idx === edgeB) break;
    idx = advance(idx);
  }
  ring1Coords.push(B);
  ring1Coords.push(A);

  // Ring 2: walk from edgeB to edgeA, including ring[edgeA]
  const ring2Coords: GeoJsonPosition[] = [B];
  idx = advance(edgeB);
  for (; ;) {
    ring2Coords.push(ring[idx]);
    if (idx === edgeA) break;
    idx = advance(idx);
  }
  ring2Coords.push(A);
  ring2Coords.push(B);

  return {
    ring1: [ring1Coords],
    ring2: [ring2Coords],
  };
}

const DRAW_ZOOM = 18;
const IMAGERY_RETURN_PARAMS = ['source', 'scene', 'from', 'to', 'layer'] as const;

function returnImagerySearch(searchParams: URLSearchParams): string {
  const params = new URLSearchParams();
  for (const key of IMAGERY_RETURN_PARAMS) {
    const value = searchParams.get(key);
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

export default function FieldCreatePage() {
  const navigate = useNavigate();
  const configQ = useConfig();
  const seasonsQ = useSeasons();
  const createFieldMutation = useCreateField();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const initialShapeMode: DrawShapeMode = searchParams.get('mode') === 'circle' ? 'circle' : 'polygon';
  const [shapeMode, setShapeMode] = useState<DrawShapeMode>(initialShapeMode);
  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [draftGeometry] = useState<PlotGeometry | null>(null);
  const preselectedSeasonId = searchParams.get('seasonId');
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | null>(preselectedSeasonId);
  const [createSeasonOpen, setCreateSeasonOpen] = useState(false);

  const [pendingFields, setPendingFields] = useState<PendingField[]>([]);
  const [isBatchSaving, setIsBatchSaving] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [leaveAlertOpen, setLeaveAlertOpen] = useState(false);
  const [deleteAlertField, setDeleteAlertField] = useState<PendingField | null>(null);
  const [editingPendingField, setEditingPendingField] = useState<PendingField | null>(null);
  const nextFieldNumRef = useRef(0);
  const [cutMode, setCutMode] = useState(false);
  const drawInstanceRef = useRef<TerraDraw | null>(null);
  const featureToPendingRef = useRef(new Map<string, string>());
  const pendingFieldsRef = useRef<PendingField[]>([]);

  const fieldsQ = useFields();
  const allSeasons = useMemo(() => seasonsQ.data ?? [], [seasonsQ.data]);

  const requestMapTool = useCallback((owner: MapToolOwner): boolean => {
    setActiveMapTool((current) => {
      if (!current || current === owner) return owner;
      return current;
    });
    return true;
  }, []);

  const releaseMapTool = useCallback((owner: MapToolOwner) => {
    setActiveMapTool((current) => (current === owner ? null : current));
  }, []);

  const handleDrawReady = useCallback((draw: TerraDraw) => {
    drawInstanceRef.current = draw;
  }, []);

  const handleGeometryChange = useCallback((geometry: PlotGeometry, featureId?: string) => {
    if (!featureId) return;
    const pendingId = featureToPendingRef.current.get(featureId);
    if (!pendingId) return;
    setPendingFields((prev) => prev.map((pf) =>
      pf.id === pendingId ? { ...pf, geometry } : pf
    ));
  }, []);

  const handlePolygonComplete = useCallback((geometry: PlotGeometry | null, featureId?: string) => {
    if (!geometry) return;
    const num = nextFieldNumRef.current;
    nextFieldNumRef.current += 1;
    const name = num === 0 ? 'Field' : `Field ${num}`;
    const pendingId = nextTempId();
    const newField = { id: pendingId, geometry, name };
    setPendingFields((prev) => [...prev, newField]);
    if (featureId) {
      featureToPendingRef.current.set(featureId, pendingId);
    }
    setEditingPendingField(newField);
  }, []);

  const handleTrimComplete = useCallback((lineCoords: [number, number][]) => {
    console.log('[trim] handleTrimComplete called, lineCoords count:', lineCoords.length);
    console.log('[trim] featureToPendingRef entries:', [...featureToPendingRef.current.entries()]);
    console.log('[trim] pendingFieldsRef.current:', pendingFieldsRef.current);

    const draw = drawInstanceRef.current;
    if (!draw) {
      console.log('[trim] draw not available');
      return;
    }

    // Find which pending field the cut line intersects
    const oldFeatureEntry = [...featureToPendingRef.current.entries()]
      .find(([, pendingId]) => pendingFieldsRef.current.some((f) => f.id === pendingId));

    if (!oldFeatureEntry) {
      console.log('[trim] no matching feature in featureToPendingRef');
      return;
    }

    const [oldFeatureId, oldPendingId] = oldFeatureEntry;
    console.log('[trim] found target featureId:', oldFeatureId, 'pendingId:', oldPendingId);

    const target = pendingFieldsRef.current.find((f) => f.id === oldPendingId);
    if (!target || target.geometry.type !== 'Polygon') {
      console.log('[trim] target not found or not a polygon');
      return;
    }

    console.log('[trim] target geometry coords count:', target.geometry.coordinates[0]?.length);

    const result = splitPolygonByLine(target.geometry.coordinates, lineCoords);
    if (!result) {
      console.log('[trim] splitPolygonByLine returned null — no valid split');
      return;
    }
    console.log('[trim] split succeeded, ring1 coords:', result.ring1[0]?.length, 'ring2 coords:', result.ring2[0]?.length);

    // Compare areas, keep the larger half as the trimmed field
    const area1 = polygonAreaMeters(toLngLatRing(result.ring1[0] ?? []));
    const area2 = polygonAreaMeters(toLngLatRing(result.ring2[0] ?? []));
    const trimmedGeo: PlotGeometry = area1 >= area2
      ? { type: 'Polygon', coordinates: result.ring1 }
      : { type: 'Polygon', coordinates: result.ring2 };

    // Remove old TerraDraw feature
    try { draw.removeFeatures([oldFeatureId]); } catch { /* ignore */ }
    featureToPendingRef.current.delete(oldFeatureId);

    // Add trimmed feature (reuses the same pending field ID)
    const results = draw.addFeatures([{
      type: 'Feature',
      geometry: trimmedGeo as GeoJSONStoreGeometries,
      properties: { mode: 'polygon' },
    }]);
    const newId = results[0]?.id;
    if (newId) {
      featureToPendingRef.current.set(String(newId), oldPendingId);
    }

    // Update pending field geometry in-place (same name, trimmed shape)
    setPendingFields((prev) => prev.map((f) =>
      f.id === oldPendingId ? { ...f, geometry: trimmedGeo } : f
    ));

    setCutMode(false);
  }, []);

  const removePendingField = useCallback((id: string) => {
    setPendingFields((prev) => prev.filter((f) => f.id !== id));
    const draw = drawInstanceRef.current;
    if (draw) {
      const entry = [...featureToPendingRef.current.entries()]
        .find(([, pid]) => pid === id);
      if (entry) {
        const [featureId] = entry;
        try { draw.removeFeatures([featureId]); } catch { /* ignore */ }
        featureToPendingRef.current.delete(featureId);
      }
    }
  }, []);

  const saveAll = async () => {
    if (pendingFields.length === 0) return;
    if (!selectedSeasonId) {
      setBatchError('Please select a season');
      return;
    }
    setIsBatchSaving(true);
    setBatchError(null);

    const existingNames = new Set(
      (fieldsQ.data ?? []).map((f) => f.name.toLowerCase()),
    );
    for (const pf of pendingFields) {
      const lower = pf.name.trim().toLowerCase();
      if (existingNames.has(lower)) {
        setBatchError(`A field named "${pf.name}" already exists. Please use a different name.`);
        setIsBatchSaving(false);
        return;
      }
      existingNames.add(lower);
    }

    try {
      const createdFields: Field[] = [];
      for (const pf of pendingFields) {
        if (pf.geometry.type !== 'Polygon') continue;
        const areaMeters = polygonAreaMeters(toLngLatRing(pf.geometry.coordinates[0] ?? []));
        const created = await createFieldMutation.mutateAsync({
          name: pf.name,
          geometry: { type: 'Polygon', coordinates: pf.geometry.coordinates },
          areaHa: areaMeters / 10000,
          seasonIds: [selectedSeasonId],
        });
        createdFields.push(created);
      }

      queryClient.setQueryData<Field[]>(queryKeys.fields, (old) => [...(old ?? []), ...createdFields]);
      navigate(`/monitoring/field-analytics/field/${createdFields[0].id}${returnImagerySearch(searchParams)}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to save fields';
      setBatchError(message);
      setIsBatchSaving(false);
    }
  };

  useEffect(() => {
    if (!map || fieldMode) return;
    const handleClick = () => {
      requestMapTool('field-draw');
      setFieldMode('draw');
    };
    map.on('click', handleClick);
    return () => { map.off('click', handleClick); };
  }, [map, fieldMode, requestMapTool]);

  // Keep ref in sync with state for use inside callbacks
  useEffect(() => {
    pendingFieldsRef.current = pendingFields;
  }, [pendingFields]);

  // Auto-name new fields based on existing season fields
  useEffect(() => {
    const seasonFields = (fieldsQ.data ?? []).filter(
      (f) => f.seasonIds?.includes(selectedSeasonId ?? ''),
    );
    let maxNum = -1;
    for (const f of seasonFields) {
      if (f.name === 'Field') { maxNum = Math.max(maxNum, 0); continue; }
      const m = f.name.match(/^Field (\d+)$/);
      if (m) maxNum = Math.max(maxNum, parseInt(m[1]));
    }
    nextFieldNumRef.current = maxNum + 1;
  }, [selectedSeasonId, fieldsQ.data]);

  const basemapResolution = useMemo(() => {
    if (!configQ.data) return { basemapConfig: null, basemapError: null };
    try {
      return { basemapConfig: resolveBasemapConfig(configQ.data), basemapError: null };
    } catch (error) {
      return { basemapConfig: null, basemapError: error as Error };
    }
  }, [configQ.data]);

  if (configQ.isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass p-4">Loading map…</div>
      </div>
    );
  }

  if (configQ.isError || !configQ.data) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass p-4">Unable to load map configuration.</div>
      </div>
    );
  }

  if (basemapResolution.basemapError instanceof BasemapConfigurationError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass p-4">{ basemapResolution.basemapError.message }</div>
      </div>
    );
  }

  const handleClose = () => {
    if (pendingFields.length > 0) {
      setLeaveAlertOpen(true);
    } else {
      navigate(`/monitoring/field-analytics${returnImagerySearch(searchParams)}`);
    }
  };

  const confirmLeave = () => navigate(`/monitoring/field-analytics${returnImagerySearch(searchParams)}`);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-transparent">
      <CreateSeasonDialog open={ createSeasonOpen } onOpenChange={ setCreateSeasonOpen } />

      {/* Top bar */ }
      <div className="glass z-50 flex items-center justify-center px-4 py-3 relative">
        <button
          aria-label="Back"
          onClick={ handleClose }
          className="absolute left-4 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-5" strokeWidth={ 1.75 } />
        </button>
        <h2 className="font-display text-lg font-semibold">Add field</h2>
      </div>

      {/* Season selector bar */ }
      { !preselectedSeasonId && (
        <div className="z-50 flex flex-col border-b border-border/60 bg-background/95">
          <div className="flex items-center gap-3 px-4 py-2">
            <label className="text-sm font-medium text-foreground shrink-0">Season</label>
            { allSeasons.length === 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={ () => setCreateSeasonOpen(true) }
              >
                Create season
              </Button>
            ) }
          </div>
          { allSeasons.length > 0 && (
            <ScrollArea className="max-h-32 border-t border-border/40">
              <div className="flex flex-col gap-0.5 px-3 py-2">
                { allSeasons.map((s) => (
                  <button
                    key={ s.id }
                    type="button"
                    onClick={ () => setSelectedSeasonId(selectedSeasonId === s.id ? null : s.id) }
                    className={ cn(
                      'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors duration-fast',
                      selectedSeasonId === s.id
                        ? 'bg-primary/15 text-foreground font-medium'
                        : 'text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                    ) }
                  >
                    <div className={ cn(
                      'size-3 shrink-0 rounded-full border-2',
                      selectedSeasonId === s.id
                        ? 'border-primary bg-primary'
                        : 'border-muted-foreground/40',
                    ) } />
                    <span className="truncate">{ s.name }</span>
                  </button>
                )) }
              </div>
            </ScrollArea>
          ) }
        </div>
      ) }

      {/* Map + side panel */ }
      <div className="relative flex flex-1 min-h-0">
        {/* Map area */ }
        <div className="relative flex-1">
          <MapLayerManager
            basemap={ basemapResolution.basemapConfig! }
            center={ configQ.data.aoi.center }
            zoom={ Math.max(configQ.data.aoi.zoom, DRAW_ZOOM) }
            scene={ null }
            opacity={ 1 }
            visible={ true }
            onBasemapError={ () => undefined }
            onMapReady={ setMap }
          />

          { draftGeometry && (
            <FieldBoundaryLayer
              map={ map }
              plot={ null }
              geometry={ draftGeometry }
              featureId="draft-field"
              name="Draft field"
            />
          ) }

          <FieldDrawController
            activeTool={ activeMapTool }
            map={ map }
            mode={ fieldMode }
            onCancel={ () => setFieldMode(null) }
            onUpdateField={ () => Promise.resolve() }
            onRequestTool={ requestMapTool }
            onReleaseTool={ releaseMapTool }
            selectedPlot={ null }
            onPolygonComplete={ handlePolygonComplete }
            drawMode={ shapeMode }
            multiDraw={ true }
            hideCard={ true }
            enableVertexDrag={ true }
            onDrawReady={ handleDrawReady }
            onGeometryChange={ handleGeometryChange }
            cutMode={ cutMode }
            onCutLineComplete={ handleTrimComplete }
          />

          {/* Left controls — vertically centered */ }
          <div className="absolute left-4 top-1/2 z-toolbar flex -translate-y-1/2 flex-col items-start gap-3">
            {/* Zoom card */ }
            <div className="glass flex flex-col overflow-hidden rounded-md p-0" role="group" aria-label="Zoom">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Zoom in"
                    onClick={ () => map?.zoomIn() }
                    className="flex h-11 w-11 items-center justify-center text-foreground/80 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground active:bg-primary/15"
                  >
                    <Plus className="size-6" strokeWidth={ 1.75 } />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Zoom in</TooltipContent>
              </Tooltip>
              <div className="h-px w-full bg-border" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Zoom out"
                    onClick={ () => map?.zoomOut() }
                    className="flex h-11 w-11 items-center justify-center text-foreground/80 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground active:bg-primary/15"
                  >
                    <Minus className="size-6" strokeWidth={ 1.75 } />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Zoom out</TooltipContent>
              </Tooltip>
            </div>

            {/* Shape toggle card — expands on hover */ }
            <div className="group glass flex w-11 flex-col overflow-hidden rounded-md p-0 transition-all duration-fast hover:w-22.25" role="group" aria-label="Shape">
              <div className="flex">
                <Tooltip delayDuration={ 600 }>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={ () => {
                        if (cutMode) { setCutMode(false); }
                        setShapeMode('polygon');
                        if (map && typeof map.getCanvas === 'function') {
                          map.getCanvas().style.cursor = 'crosshair';
                        }
                      } }
                      className={ cn(
                        'flex h-11 w-11 shrink-0 items-center justify-center transition-colors duration-fast',
                        !cutMode && shapeMode === 'polygon'
                          ? 'bg-primary/15 text-primary'
                          : 'text-foreground/80 hover:bg-accent hover:text-accent-foreground',
                      ) }
                    >
                      <Square className="size-6" strokeWidth={ 1.75 } />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">{ cutMode ? 'Exit cut mode' : 'Draw polygon' }</TooltipContent>
                </Tooltip>
                <div className="h-full w-px shrink-0 bg-border opacity-0 transition-opacity duration-fast group-hover:opacity-100" />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={ () => {
                        if (cutMode) { setCutMode(false); }
                        setShapeMode('circle');
                        if (map && typeof map.getCanvas === 'function') {
                          map.getCanvas().style.cursor = 'crosshair';
                        }
                      } }
                      className={ cn(
                        'flex h-11 w-11 shrink-0 items-center justify-center transition-colors duration-fast',
                        !cutMode && shapeMode === 'circle'
                          ? 'bg-primary/15 text-primary'
                          : 'text-foreground/80 opacity-0 transition-opacity duration-fast group-hover:opacity-100',
                      ) }
                    >
                      <Circle className="size-6" strokeWidth={ 1.75 } />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">{ cutMode ? 'Exit cut mode' : 'Draw circle' }</TooltipContent>
                </Tooltip>
              </div>
            </div>

            {/* Action card: cut + remove last + undo */ }
            <div className="glass flex flex-col overflow-hidden rounded-md p-0" role="group" aria-label="Actions">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Trim field (disabled)"
                    onClick={ () => {} }
                    className="flex h-11 w-11 items-center justify-center opacity-30 cursor-not-allowed text-foreground/80"
                    disabled={ true }
                  >
                    <Scissors className="size-6" strokeWidth={ 1.75 } />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  Trim field (disabled)
                </TooltipContent>
              </Tooltip>
              <div className="h-px w-full bg-border" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Remove last field"
                    onClick={ () => {
                      if (pendingFields.length > 0) {
                        removePendingField(pendingFields[pendingFields.length - 1].id);
                      }
                    } }
                    className="flex h-11 w-11 items-center justify-center text-foreground/80 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground active:bg-primary/15 disabled:opacity-30"
                    disabled={ pendingFields.length === 0 }
                  >
                    <Trash2 className="size-6" strokeWidth={ 1.75 } />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Remove last field</TooltipContent>
              </Tooltip>
              <div className="h-px w-full bg-border" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Undo vertex"
                    onClick={ () => {
                      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
                    } }
                    className="flex h-11 w-11 items-center justify-center text-foreground/80 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground active:bg-primary/15"
                  >
                    <Undo2 className="size-6" strokeWidth={ 1.75 } />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Undo last vertex</TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* Bottom center hint */ }
          { !draftGeometry && pendingFields.length === 0 && (
            <div className="absolute left-1/2 bottom-24 z-40 -translate-x-1/2">
              <div className="glass rounded-full px-4 py-2 text-sm">
                { shapeMode === 'circle'
                  ? 'Click on the map to place the circle center'
                  : 'Put a dot on the map to start drawing' }
              </div>
            </div>
          ) }

          {/* Error toast */ }
          { batchError && (
            <div className="absolute left-1/2 bottom-20 z-50 w-max max-w-[90vw] -translate-x-1/2 rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground shadow-lg">
              { batchError }
            </div>
          ) }
        </div>

        {/* Side panel — always visible in multi-draw mode */ }
        <div className="w-80 shrink-0 border-l border-border bg-background/95 flex flex-col">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60">
            <h3 className="font-display text-sm font-semibold text-foreground">Fields to add</h3>
            { pendingFields.length > 0 && (
              <span className="flex size-5 items-center justify-center rounded-full bg-primary/15 text-[11px] font-medium text-primary">
                { pendingFields.length }
              </span>
            ) }
          </div>

          <ScrollArea className="flex-1">
            { pendingFields.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                <p className="text-sm text-muted-foreground">Draw a field on the map to add it here.</p>
                <p className="text-xs text-muted-foreground/60">You can add multiple fields before saving.</p>
              </div>
            ) : (
              <div className="p-3 space-y-2">
                { pendingFields.map((pf) => {
                  const area = pf.geometry.type === 'Polygon'
                    ? polygonAreaMeters(toLngLatRing(pf.geometry.coordinates[0] ?? [])) / 10000
                    : 0;
                  return (
                    <div
                      key={ pf.id }
                      className="grid grid-cols-[52px_1fr_auto] gap-x-3 rounded-lg border border-border/70 bg-card/35 px-4 py-4 transition-colors duration-fast"
                    >
                      <div className="row-span-2 self-center">
                        <FieldThumbnail geometry={ pf.geometry } size={ 52 } />
                      </div>
                      <p className="min-w-0 self-center truncate text-base font-semibold text-foreground">
                        { pf.name }
                      </p>
                      <div className="flex items-center gap-1 self-center justify-self-end">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={ (e) => { e.stopPropagation(); setEditingPendingField(pf); } }
                              className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-colors duration-fast"
                              aria-label={ `Edit ${pf.name}` }
                            >
                              <Pencil className="size-4" strokeWidth={ 1.75 } />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="left">Edit</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              onClick={ (e) => { e.stopPropagation(); setDeleteAlertField(pf); } }
                              className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors duration-fast"
                              aria-label={ `Delete ${pf.name}` }
                            >
                              <Trash2 className="size-4" strokeWidth={ 1.75 } />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="left">Delete</TooltipContent>
                        </Tooltip>
                      </div>
                      <span className="self-center truncate text-xs text-muted-foreground">{ area.toFixed(1) } ha</span>
                      <span />
                    </div>
                  );
                }) }
              </div>
            ) }
          </ScrollArea>

          <div className="shrink-0 border-t border-border/60 px-4 py-3 space-y-2">
            { selectedSeasonId && (
              <p className="text-[12px] text-muted-foreground">
                Season: <span className="font-medium text-foreground">
                  { allSeasons.find((s) => s.id === selectedSeasonId)?.name ?? 'Unknown' }
                </span>
              </p>
            ) }
            <Button
              type="button"
              variant="primary"
              size="lg"
              className="w-full"
              onClick={ () => void saveAll() }
              disabled={ pendingFields.length === 0 || !selectedSeasonId || isBatchSaving }
            >
              { isBatchSaving ? (
                <>
                  <Loader2 className="size-4 animate-spin mr-1.5" />
                  Saving…
                </>
              ) : (
                `Save ${pendingFields.length > 0 ? `${pendingFields.length} field${pendingFields.length > 1 ? 's' : ''}` : 'all'}`
              ) }
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="lg"
              className="w-full"
              onClick={ () => { if (pendingFields.length > 0) setLeaveAlertOpen(true); else handleClose(); } }
              disabled={ isBatchSaving }
            >
              <X className="size-4 mr-1.5" strokeWidth={ 1.75 } />
              Cancel drawing
            </Button>
          </div>
        </div>
      </div>

      {/* Leave confirmation dialog */ }
      <AlertDialogRoot open={ leaveAlertOpen } onOpenChange={ setLeaveAlertOpen }>
        <AlertDialogContent>
          <AlertDialogTitle>Leave this page?</AlertDialogTitle>
          <AlertDialogDescription>
            You have { pendingFields.length } unsaved field{ pendingFields.length !== 1 ? 's' : '' }.
            Are you sure you want to go back?
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Continue drawing</AlertDialogCancel>
            <AlertDialogAction onClick={ confirmLeave }>Discard & leave</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>

      {/* Delete pending field confirmation */ }
      <AlertDialogRoot
        open={ !!deleteAlertField }
        onOpenChange={ (open) => { if (!open) setDeleteAlertField(null); } }
      >
        <AlertDialogContent>
          <AlertDialogTitle>Remove this field?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to remove "{ deleteAlertField?.name }"? It will not be saved.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ () => {
              if (deleteAlertField) removePendingField(deleteAlertField.id);
              setDeleteAlertField(null);
            } }>
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>

      {/* Edit pending field dialog */ }
      { editingPendingField && (
        <EditFieldDialog
          key={ editingPendingField.id }
          field={ {
            id: editingPendingField.id,
            name: editingPendingField.name,
            geometry: editingPendingField.geometry,
            seasonIds: selectedSeasonId ? [selectedSeasonId] : [],
            vegetationData: [],
            areaHa: editingPendingField.geometry.type === 'Polygon'
              ? polygonAreaMeters(toLngLatRing(editingPendingField.geometry.coordinates[0] ?? [])) / 10000
              : 0,
          } as unknown as Field }
          open={ !!editingPendingField }
          onOpenChange={ (open) => { if (!open) setEditingPendingField(null); } }
          onSave={ (fieldId, name, geometry) => {
            setPendingFields((prev) => prev.map((pf) =>
              pf.id === fieldId
                ? { ...pf, name: name ?? pf.name, geometry: geometry ?? pf.geometry }
                : pf
            ));
            setEditingPendingField(null);

            if (geometry) {
              const draw = drawInstanceRef.current;
              if (draw) {
                const entry = [...featureToPendingRef.current.entries()]
                  .find(([, pid]) => pid === fieldId);
                if (entry) {
                  const [oldId] = entry;
                  try { draw.removeFeatures([oldId]); } catch { /* ignore */ }
                  featureToPendingRef.current.delete(oldId);
                }
                const results = draw.addFeatures([{
                  type: 'Feature',
                  geometry: geometry as GeoJSONStoreGeometries,
                  properties: { mode: 'polygon' },
                }]);
                const newId = results[0]?.id;
                if (newId) {
                  featureToPendingRef.current.set(String(newId), fieldId);
                  try { draw.setMode('select'); draw.selectFeature(newId); } catch { /* ignore */ }
                }
              }
            }
          } }
          saving={ false }
          onDelete={ async () => {
            // no-op: pending fields use removePendingField
          } }
        />
      ) }
    </div>
  );
}
