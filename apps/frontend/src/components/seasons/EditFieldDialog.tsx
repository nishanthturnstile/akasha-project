import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { ChevronDown, ChevronRight, Loader2, Plus, Sprout, Scissors, Timer, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { DatePicker } from '@/components/ui/date-picker';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogFooter,
} from '@/components/ui/alert-dialog';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { useConfig, useCrops, useFieldGroups, useFields, useIrrigationTypes, useSeasons, useTillageTypes, useVarieties, queryKeys } from '@/lib/queries';
import { useVegetationCycles, type VegetationCycleForm } from '@/hooks/useVegetationCycles';
import { resolveBasemapConfig } from '@/map/basemap';
import { MAP_UI_COLORS } from '@/map/colors';
import { polygonAreaMeters } from '@/lib/measure';
import type { DateRange } from '@/components/ui/date-picker';
import type maplibregl from 'maplibre-gl';
import type { TerraDraw } from 'terra-draw';
import type { Crop, Field, GeoJsonPosition, IrrigationType, PlotGeometry, TillageType, VegetationCycleCreate } from '@/types/api';
import { deriveCircleFromRing, sanitizeRingPrecision } from '@/components/fields/circleGeometry';

interface Props {
  field: Field;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (fieldId: string, name: string, geometry?: PlotGeometry, vegetationData?: VegetationCycleCreate[], groupId?: string | null, areaHa?: number | null) => void;
  onDelete?: (fieldId: string) => void;
  saving?: boolean;
  initialSeasonId?: string;
}

function polygonBounds(geometry: Field['geometry']): [[number, number], [number, number]] | null {
  if (!geometry) return null;
  const ring = geometry.type === 'Polygon'
    ? geometry.coordinates[0]
    : geometry.coordinates[0][0];
  if (!ring || ring.length === 0) return null;
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  for (const [lng, lat] of ring) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [[minLng, minLat], [maxLng, maxLat]];
}

function polygonCenter(geometry: Field['geometry']): [number, number] {
  const bounds = polygonBounds(geometry);
  if (!bounds) return [78, 12];
  return [
    (bounds[0][0] + bounds[1][0]) / 2,
    (bounds[0][1] + bounds[1][1]) / 2,
  ];
}

function computeGeometryArea(geometry: PlotGeometry): number | null {
  if (geometry.type !== 'Polygon') return null;
  const ring = geometry.coordinates[0]?.map(([lng, lat]) => [lng, lat] as [number, number]);
  if (!ring || ring.length < 3) return null;
  return polygonAreaMeters(ring) / 10000;
}

function latestPolygon(draw: TerraDraw): PlotGeometry | null {
  const features = draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon');
  const feature = features[features.length - 1];
  return feature?.geometry.type === 'Polygon' ? (feature.geometry as PlotGeometry) : null;
}

function isPolygonGeometry(geometry: PlotGeometry | undefined): geometry is PlotGeometry & { type: 'Polygon' } {
  return geometry?.type === 'Polygon';
}

function rangesOverlap(aStart: string, aEnd: string, bStart: string, bEnd: string): boolean {
  return aStart <= bEnd && bStart <= aEnd;
}

function getOverlapRanges(
  currentCycleId: string,
  allCycles: VegetationCycleForm[],
): DateRange[] {
  const ranges: DateRange[] = [];
  for (const other of allCycles) {
    if (other.id === currentCycleId) continue;
    const oStart = other.plantingDate;
    if (!oStart) continue;
    const oEnd = other.harvestingDate || oStart;
    ranges.push({ start: oStart, end: oEnd });
  }
  return ranges;
}

function getBlockedRanges(
  currentCycleId: string,
  allCycles: VegetationCycleForm[],
  seasonStartDate?: string,
  seasonEndDate?: string,
): DateRange[] {
  const idx = allCycles.findIndex((c) => c.id === currentCycleId);
  if (idx === -1) return [];
  const ranges: DateRange[] = [];

  // Block from next cycle's end+1 to season end (for earlier cycles)
  if (idx < allCycles.length - 1 && seasonEndDate) {
    const next = allCycles[idx + 1];
    const end = next.harvestingDate || next.plantingDate;
    if (end) {
      const [y, m, d] = end.split('-').map(Number);
      const dt = new Date(y, m - 1, d);
      dt.setDate(dt.getDate() + 1);
      const yy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      const start = `${yy}-${mm}-${dd}`;
      if (start <= seasonEndDate) {
        ranges.push({ start, end: seasonEndDate });
      }
    }
  }

  // Block from season start to previous cycle's end (for later cycles)
  if (idx > 0 && seasonStartDate) {
    const prev = allCycles[idx - 1];
    const end = prev.harvestingDate || prev.plantingDate;
    if (end && end >= seasonStartDate) {
      ranges.push({ start: seasonStartDate, end });
    }
  }

  return ranges;
}

export default function EditFieldDialog({
  field,
  open,
  onOpenChange,
  onSave,
  onDelete,
  saving = false,
  initialSeasonId,
}: Props) {
  const [name, setName] = useState(field.name);
  const [groupId, setGroupId] = useState(field.groupId ?? '');
  const [error, setError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [confirmDeleteField, setConfirmDeleteField] = useState(false);
  const [confirmClearSeasonId, setConfirmClearSeasonId] = useState<string | null>(null);
  const forceCloseRef = useRef(false);
  const [miniMap, setMiniMap] = useState<maplibregl.Map | null>(null);
  const [editedGeometry, setEditedGeometry] = useState<PlotGeometry | null>(null);
  const [basemapRuntimeError, setBasemapRuntimeError] = useState<Error | null>(null);

  const drawRef = useRef<TerraDraw | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const initialVegCyclesRef = useRef<string>('');

  const seasonsQ = useSeasons();
  const cropsQ = useCrops();
  const fieldGroupsQ = useFieldGroups();
  const irrigationTypesQ = useIrrigationTypes();
  const tillageTypesQ = useTillageTypes();
  const [expandedSeasons, setExpandedSeasons] = useState<Set<string>>(new Set());
  const { cycles: vegetationCycles, setFieldCycles, addCycle, removeCycle, updateCycle, clearSeasonCycles } = useVegetationCycles(field.id);

  const queryClient = useQueryClient();
  const configQ = useConfig();
  const fieldsQ = useFields();

  // Seed store from field.vegetationData when dialog opens
  const seededRef = useRef(false);
  useEffect(() => {
    if (!open) { seededRef.current = false; return; }
    const data = field.vegetationData;
    if (!data) return;
    if (data.length === 0) { seededRef.current = true; return; }
    if (!cropsQ.data || !irrigationTypesQ.data || !tillageTypesQ.data) return;
    if (seededRef.current) return;
    seededRef.current = true;
    const bySeason: Record<string, VegetationCycleForm[]> = {};
    for (const vc of data) {
      const sid = vc.seasonId;
      if (!bySeason[sid]) bySeason[sid] = [];
      const crop = cropsQ.data.find((c) => c.id === vc.cropType);
      const varietyName = vc.varietyName ?? '';
      const irr = irrigationTypesQ.data?.find((t) => t.id === vc.irrigationType);
      const till = tillageTypesQ.data?.find((t) => t.id === vc.tillageType);
      bySeason[sid].push({
        id: vc.id,
        cropName: crop?.name ?? String(vc.cropType),
        variety: varietyName,
        maturity: vc.maturity ?? '',
        year: vc.year ?? null,
        plantingDate: vc.sowingDate ?? `${new Date().getFullYear()}-01-01`,
        irrigationType: irr?.name ?? '',
        targetYield: vc.targetYield ?? null,
        harvestingDate: vc.harvestingDate ?? '',
        tillageType: till?.name ?? '',
        actualYield: vc.actualYield ?? null,
        isCutOff: vc.isCutOff ?? false,
        notes: vc.notes ?? '',
      });
    }
    setFieldCycles(bySeason);
  }, [open, field.vegetationData, cropsQ.data, irrigationTypesQ.data, tillageTypesQ.data, setFieldCycles]);

  // Snapshot initial veg cycles for dirty checking
  const vegPayload = useMemo(() => {
    const payload: VegetationCycleCreate[] = [];
    for (const [seasonId, cycles] of Object.entries(vegetationCycles)) {
      for (const cycle of cycles) {
        const crop = cropsQ.data?.find((c) => c.name === cycle.cropName);
        let varietyId: number | null = null;
        if (cycle.variety && crop) {
          const cached = queryClient.getQueryData<{ items: Array<{ id: number; name: string }> }>(queryKeys.varieties(crop.id));
          if (cached) {
            const v = cached.items.find((vi) => vi.name === cycle.variety);
            if (v) varietyId = v.id;
          }
        }
        const irr = irrigationTypesQ.data?.find((t) => t.name === cycle.irrigationType);
        const till = tillageTypesQ.data?.find((t) => t.name === cycle.tillageType);
        payload.push({
          seasonId,
          year: cycle.year ?? new Date().getFullYear(),
          cropType: crop?.id ?? 0,
          cropVariety: varietyId,
          sowingDate: cycle.plantingDate || null,
          harvestingDate: cycle.harvestingDate || null,
          targetYield: cycle.targetYield,
          actualYield: cycle.actualYield,
          irrigationType: irr?.id ?? null,
          tillageType: till?.id ?? null,
          maturity: cycle.maturity || null,
          notes: cycle.notes || null,
          isCutOff: cycle.isCutOff || null,
        });
      }
    }
    return payload;
  }, [vegetationCycles, cropsQ.data, irrigationTypesQ.data, tillageTypesQ.data, queryClient]);

  // Save first payload as the "clean" snapshot for dirty detection
  useEffect(() => {
    if (open && seededRef.current && !initialVegCyclesRef.current) {
      initialVegCyclesRef.current = JSON.stringify(vegPayload);
    }
    if (!open) {
      initialVegCyclesRef.current = '';
    }
  }, [open, vegPayload, seededRef]);

  const dirty = useMemo(() => {
    if (!open) return false;
    const nameChanged = name !== field.name;
    const groupChanged = (groupId || null) !== (field.groupId || null);
    const geomChanged = editedGeometry !== null;
    const vegChanged = initialVegCyclesRef.current && JSON.stringify(vegPayload) !== initialVegCyclesRef.current;
    return nameChanged || groupChanged || geomChanged || (vegChanged ?? false);
  }, [open, name, field.name, groupId, field.groupId, editedGeometry, vegPayload]);

  const basemapResolution = useMemo(() => {
    if (!configQ.data) return { config: null, error: null };
    try {
      return { config: resolveBasemapConfig(configQ.data), error: null };
    } catch (error) {
      return { config: null, error: error as Error };
    }
  }, [configQ.data]);

  useEffect(() => {
    if (!open) setBasemapRuntimeError(null);
  }, [open]);

  const center = useMemo(() => polygonCenter(field.geometry), [field.geometry]);

  const isMultiPart = useMemo(() => !isPolygonGeometry(field.geometry), [field.geometry]);

  const displayGeometry = editedGeometry ?? field.geometry;

  const currentArea = useMemo(() => {
    if (isMultiPart) return field.areaHa ?? null;
    return computeGeometryArea(displayGeometry);
  }, [isMultiPart, field.areaHa, displayGeometry]);

  const geometryChanged = useMemo(() => {
    if (!editedGeometry) return false;
    return JSON.stringify(editedGeometry) !== JSON.stringify(field.geometry);
  }, [editedGeometry, field.geometry]);

  const handleMapReady = useCallback((map: maplibregl.Map) => {
    setMiniMap(map);
    void import('maplibre-gl').then(({ default: maplibregl }) => {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-left');
    }).catch((exc: unknown) => {
      setError(exc instanceof Error ? exc.message : 'Failed to initialise map controls.');
    });
    const bounds = polygonBounds(field.geometry);
    if (bounds) {
      map.fitBounds(bounds, { padding: 24, maxZoom: 20 });
    }
  }, [field.geometry]);

  const stopDraw = useCallback(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    drawRef.current = null;
  }, []);

  // TerraDraw SelectMode — click polygon to select, then drag vertices to edit
  useEffect(() => {
    if (!open || !miniMap || isMultiPart) return;

    let cancelled = false;

    void (async () => {
      try {
        const [
          { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode },
          { TerraDrawMapLibreGLAdapter },
          { TerraDrawCircleEditMode },
        ] = await Promise.all([
          import('terra-draw'),
          import('terra-draw-maplibre-gl-adapter'),
          import('@/components/fields/circleEditMode'),
        ]);

        if (cancelled) return;

        const draw = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map: miniMap, prefixId: 'edit-dialog-draw' }),
          modes: [
            new TerraDrawPolygonMode({
              styles: {
                fillColor: MAP_UI_COLORS.selection,
                fillOpacity: 0.25,
                outlineColor: MAP_UI_COLORS.selectionOutline,
                outlineWidth: 3,
              },
            }),
            new TerraDrawSelectMode({
              // See the matching comment in FieldDrawController.tsx: TerraDraw's
              // default 40px vertex/midpoint hit-tolerance covers most of a
              // modest-sized field's interior, making whole-shape dragging hard
              // to trigger reliably. Tightened here to match.
              pointerDistance: 20,
              styles: {
                selectedPolygonColor: MAP_UI_COLORS.selection,
                selectedPolygonFillOpacity: 0.25,
                selectedPolygonOutlineColor: MAP_UI_COLORS.selectionOutline,
                selectedPolygonOutlineWidth: 3,
              },
              flags: {
                polygon: {
                  feature: {
                    draggable: true,
                    coordinates: {
                      draggable: true,
                      midpoints: { draggable: true },
                      deletable: true,
                    },
                  },
                },
              },
            }),
            // Only ever used to EDIT an already-loaded field's geometry (this dialog
            // never draws a brand-new circle), so no TerraDrawCircleMode is registered.
            new TerraDrawCircleEditMode({
              styles: {
                handleColor: MAP_UI_COLORS.handle,
                handleOutlineColor: MAP_UI_COLORS.white,
                handleWidth: 6 as const,
              },
              pointerDistance: 20,
            }),
          ],
        });

        draw.start();
        draw.setMode('select');
        drawRef.current = draw;

        if (field.geometry.type === 'Polygon') {
          // Rounds excessive-precision coordinates that may already be sitting in the
          // database from before this was fixed (or from any other source) -- without
          // this, a field saved with a bad ring would keep failing to load forever,
          // since sanitizing only new writes doesn't touch data that's already saved.
          const sanitizedRing = sanitizeRingPrecision(field.geometry.coordinates[0]) as GeoJsonPosition[];
          const circleParams = deriveCircleFromRing(sanitizedRing);
          const results = draw.addFeatures([
            {
              type: 'Feature',
              geometry: { type: 'Polygon', coordinates: [sanitizedRing] },
              // Always tagged 'polygon' (never 'circle') so TerraDrawPolygonMode's
              // styleFeature renders it -- no mode named 'circle' is registered in this
              // dialog (it only ever edits an existing geometry, never draws a new one),
              // so tagging 'circle' here resolves to no style function and the feature
              // silently fails to render at all. circle-edit mode targets features by id,
              // not by this tag, so the tag is purely a display concern.
              properties: { mode: 'polygon' },
            },
          ]);
          const result = results[0];
          // addFeatures always returns an id, even for a REJECTED feature (e.g. TerraDraw's
          // own "excessive coordinate precision" check) -- checking `id` truthiness alone
          // would proceed to target a feature that was never actually added to the store,
          // silently rendering nothing. Must check `valid` too.
          if (result?.valid === false) {
            console.error('[EditFieldDialog] field geometry rejected by TerraDraw, cannot edit', {
              fieldId: field.id,
              reason: result.reason,
            });
            setError('This field’s boundary could not be loaded for editing.');
          } else if (result?.id) {
            if (circleParams) {
              draw.setMode('circle-edit');
              draw.updateModeOptions('circle-edit', { targetFeatureId: result.id });
            } else {
              draw.selectFeature(result.id);
            }
          }
        }

        draw.on('change', () => {
          const geometry = latestPolygon(draw);
          if (geometry) {
            setEditedGeometry(geometry);
            setError(null);
          }
        });

        cleanupRef.current = () => {
          cancelled = true;
          try { draw.clear(); } catch { /* ignore */ }
          try { draw.stop(); } catch { /* ignore */ }
          drawRef.current = null;
        };
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : 'Failed to initialise the geometry editor.');
      }
    })();

    return () => {
      cancelled = true;
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
      drawRef.current = null;
    };
  }, [open, miniMap, isMultiPart, stopDraw, field.geometry, field.id]);

  // Auto-expand seasons when dialog opens
  useEffect(() => {
    if (!open) return;
    if (initialSeasonId && field.seasonIds.includes(initialSeasonId)) {
      setExpandedSeasons(new Set([initialSeasonId]));
      return;
    }
    const data = field.vegetationData;
    if (data && data.length > 0) {
      const sorted = [...data].sort((a, b) => {
        if (b.year !== a.year) return b.year - a.year;
        if (a.sowingDate && b.sowingDate) return b.sowingDate.localeCompare(a.sowingDate);
        if (a.sowingDate) return -1;
        if (b.sowingDate) return 1;
        return 0;
      });
      const sid = sorted[0].seasonId;
      if (field.seasonIds.includes(sid)) {
        setExpandedSeasons(new Set([sid]));
        return;
      }
    }
    setExpandedSeasons(new Set(field.seasonIds));
  }, [open, field.seasonIds, initialSeasonId, field.vegetationData]);

  const toggleSeason = useCallback((seasonId: string) => {
    setExpandedSeasons((prev) => {
      const next = new Set(prev);
      if (next.has(seasonId)) next.delete(seasonId);
      else next.add(seasonId);
      return next;
    });
  }, []);

  const hasAnyOverlap = useMemo(() => {
    for (const cycles of Object.values(vegetationCycles)) {
      for (let i = 0; i < cycles.length; i++) {
        for (let j = i + 1; j < cycles.length; j++) {
          const a = cycles[i];
          const b = cycles[j];
          const aStart = a.plantingDate;
          const bStart = b.plantingDate;
          if (!aStart || !bStart) continue;
          const aEnd = a.harvestingDate || aStart;
          const bEnd = b.harvestingDate || bStart;
          if (rangesOverlap(aStart, aEnd, bStart, bEnd)) return true;
        }
      }
    }
    return false;
  }, [vegetationCycles]);

  const handleClearSeason = useCallback((seasonId: string) => {
    setConfirmClearSeasonId(seasonId);
  }, []);

  const handleConfirmClearSeason = useCallback(() => {
    if (!confirmClearSeasonId) return;
    clearSeasonCycles(confirmClearSeasonId);
    setExpandedSeasons((prev) => {
      const next = new Set(prev);
      next.delete(confirmClearSeasonId);
      return next;
    });
    setConfirmClearSeasonId(null);
  }, [confirmClearSeasonId, clearSeasonCycles]);

  const handleSave = () => {
    if (!name.trim()) {
      setError('Field name is required');
      return;
    }
    const trimmedName = name.trim();
    if (trimmedName.toLowerCase() !== field.name.trim().toLowerCase()) {
      const duplicateName = (fieldsQ.data ?? []).find(
        (f) => f.name.toLowerCase() === trimmedName.toLowerCase() && f.id !== field.id,
      );
      if (duplicateName) {
        setError(`A field named "${trimmedName}" already exists.`);
        return;
      }
    }
    setError(null);

    onSave?.(
      field.id,
      trimmedName,
      geometryChanged ? (editedGeometry as PlotGeometry) : undefined,
      vegPayload.length > 0 ? vegPayload : undefined,
      groupId || null,
      // Recomputed from the actual edited geometry -- without this, resizing/moving
      // a field (especially a dragged circle, where the area can change drastically)
      // saves the new boundary but leaves the old area displayed everywhere else
      // until the field happens to be re-saved for an unrelated reason.
      geometryChanged ? currentArea : undefined,
    );
  };

  const handleDelete = () => {
    setConfirmDeleteField(true);
  };

  const handleConfirmDelete = async () => {
    try {
      setConfirmDeleteField(false);
      await onDelete?.(field.id);
      onOpenChange(false);
    } catch {
      setError('Failed to delete field');
    }
  };

  const handleCancel = useCallback(() => {
    setConfirmClose(true);
  }, []);

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen && !forceCloseRef.current) {
      if (confirmDeleteField || confirmClearSeasonId) return;
      setConfirmClose(true);
    } else {
      forceCloseRef.current = false;
      onOpenChange(nextOpen);
    }
  }, [onOpenChange, confirmDeleteField, confirmClearSeasonId]);

  useEffect(() => {
    if (!confirmClose && forceCloseRef.current) {
      forceCloseRef.current = false;
      onOpenChange(false);
    }
  }, [confirmClose, onOpenChange]);

  return (
    <Dialog.Root open={ open } onOpenChange={ handleOpenChange }>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-modal bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit field"
          className="glass fixed left-1/2 top-1/2 z-modal max-h-[90vh] w-[calc(100vw-1.5rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl p-0 sm:w-[calc(100vw-2rem)] lg:w-[min(72rem,calc(100vw-3rem))]"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit field</Dialog.Title>
            <Dialog.Description>Edit field name and adjust its boundary on the map.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between border-b-2 border-border/60 px-4 py-3 sm:px-6 sm:py-4">
            <h3 className="text-lg font-display font-semibold">Edit field</h3>
            <button aria-label="Close" onClick={ handleCancel } className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/40">
              <X className="size-5" />
            </button>
          </div>

          <div className="p-4 space-y-6 sm:p-6">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* Left column: mini-map with polygon edit */ }
              <div className="h-64 min-h-[200px] lg:h-auto">
                { basemapResolution.error ? (
                  <div
                    className="flex min-h-50 items-center justify-center rounded-xl border-2 border-destructive/60 bg-destructive/10 p-4 text-center text-sm text-destructive"
                    data-testid="basemap-configuration-error"
                  >
                    { basemapResolution.error.message }
                  </div>
                ) : basemapResolution.config ? (
                  <div className="relative h-full min-h-[200px] w-full rounded-xl overflow-hidden border-2 border-border/60">
                    <MapLayerManager
                      basemap={ basemapResolution.config }
                      center={ center }
                      zoom={ 15 }
                      scene={ null }
                      opacity={ 1 }
                      visible={ true }
                      onBasemapError={ setBasemapRuntimeError }
                      onMapReady={ handleMapReady }
                    />
                    { basemapRuntimeError && (
                      <div
                        className="absolute inset-x-3 top-3 z-popover rounded-md bg-destructive px-3 py-2 text-sm text-destructive-foreground shadow-e2"
                        data-testid="basemap-runtime-error"
                      >
                        Unable to load Esri basemap: { basemapRuntimeError.message }
                      </div>
                    ) }
                    { miniMap && isMultiPart && (
                      <FieldBoundaryLayer
                        map={ miniMap }
                        plot={ null }
                        geometry={ field.geometry }
                        featureId={ `edit-field-${field.id}` }
                        name={ field.name }
                      />
                    ) }
                    { isMultiPart && (
                      <div className="absolute inset-0 flex items-center justify-center bg-background/60 text-sm text-muted-foreground">
                        Multi-part field editing is not available in this dialog.
                      </div>
                    ) }
                  </div>
                ) : (
                  <div className="flex min-h-[200px] items-center justify-center rounded-xl border-2 border-border/60 bg-muted/30 text-sm text-muted-foreground">
                    Loading map…
                  </div>
                ) }
              </div>

              {/* Right column: field details */ }
              <div className="space-y-5">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">Field name</label>
                    <input
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm h-10 focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                      value={ name }
                      onChange={ (e) => setName(e.target.value) }
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">Group name</label>
                    <Select
                      value={ groupId }
                      onValueChange={ (v) => setGroupId(v === '__none__' ? '' : v) }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select group" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">No group</SelectItem>
                        { (fieldGroupsQ.data ?? []).map((g) => (
                          <SelectItem key={ g.id } value={ g.id }>{ g.name }</SelectItem>
                        )) }
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="rounded-lg border-2 border-border/60 bg-muted/10 px-4 py-3">
                  <span className="text-sm text-muted-foreground">Area: </span>
                  <span className="text-sm font-semibold text-foreground">
                    { currentArea != null ? `${currentArea.toFixed(2)} ha` : '—' }
                  </span>
                </div>

                { seasonsQ.data && (
                  <div className="border-2 border-border/60 rounded-xl">
                    <div className="px-4 py-3 border-b-2 border-border/60">
                      <h4 className="text-sm font-semibold text-foreground">Vegetation cycles</h4>
                    </div>
                    <div className="max-h-75 overflow-y-auto p-4 space-y-3">
                      { seasonsQ.data
                        .filter((s) => field.seasonIds.includes(s.id))
                        .sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime())
                        .map((season) => {
                          const isExpanded = expandedSeasons.has(season.id);
                          const cycles = vegetationCycles[season.id] ?? [];
                          return (
                            <div key={ season.id } className="border-2 border-border/60 rounded-lg overflow-hidden">
                              <div className={ cn(
                                'flex w-full items-center justify-between px-4 py-3 text-sm font-medium',
                                isExpanded
                                  ? 'bg-accent/80 text-accent-foreground border-l-2 border-primary'
                                  : 'bg-muted/50 hover:bg-accent/40 text-muted-foreground',
                              ) }>
                                <button
                                  type="button"
                                  onClick={ () => toggleSeason(season.id) }
                                  className="flex items-center gap-2 flex-1 text-left"
                                >
                                  { isExpanded
                                    ?                                   <ChevronDown className="size-4 text-muted-foreground shrink-0" />
                                    : <ChevronRight className="size-4 text-muted-foreground shrink-0" /> }
                                  <span>{ season.name }</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={ () => handleClearSeason(season.id) }
                                  className="rounded-md p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                                  title="Remove all vegetation cycles"
                                >
                                  <Trash2 className="size-4" />
                                </button>
                              </div>
                              { isExpanded && (
                                <div className="border-t-2 border-border/60 p-4 space-y-4">
                                  <button
                                    type="button"
                                    onClick={ () => {
                                    const existing = vegetationCycles[season.id] ?? [];
                                    const last = existing[existing.length - 1];
                                    let defaultDate = season.startDate ?? '';
                                    if (last?.harvestingDate) {
                                      const [y, m, d] = last.harvestingDate.split('-').map(Number);
                                      const dt = new Date(y, m - 1, d);
                                      dt.setDate(dt.getDate() + 1);
                                      const yy = dt.getFullYear();
                                      const mm = String(dt.getMonth() + 1).padStart(2, '0');
                                      const dd = String(dt.getDate()).padStart(2, '0');
                                      defaultDate = `${yy}-${mm}-${dd}`;
                                    }
                                    addCycle(season.id, defaultDate || undefined);
                                  } }
                                    className="flex w-full items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-border/60 px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
                                  >
                                    <Plus className="size-4" strokeWidth={ 1.75 } />
                                    Add vegetation cycle
                                  </button>
                                  { cycles.length === 0 && (
                                    <p className="text-sm text-muted-foreground">No vegetation cycles added yet.</p>
                                  ) }
                                  { cycles.slice().sort((a, b) => {
                                      const yearDiff = (b.year ?? 0) - (a.year ?? 0);
                                      if (yearDiff !== 0) return yearDiff;
                                      const aDate = a.plantingDate || '9999-12-31';
                                      const bDate = b.plantingDate || '9999-12-31';
                                      return bDate.localeCompare(aDate);
                                    }).map((cycle) => (
                                    <CycleCard
                                      key={ `${cycle.id}-${cycle.cropName}` }
                                      cycle={ cycle }
                                      allCycles={ cycles }
                                      seasonId={ season.id }
                                      seasonStartDate={ season.startDate ?? undefined }
                                      seasonEndDate={ season.endDate ?? undefined }
                                      cropsData={ cropsQ.data }
                                      irrigationTypesData={ irrigationTypesQ.data }
                                      tillageTypesData={ tillageTypesQ.data }
                                      onUpdateCycle={ updateCycle }
                                      onRemoveCycle={ removeCycle }
                                    />
                                  )) }
                                </div>
                              ) }
                            </div>
                          );
                        }) }
                    </div>
                  </div>
                ) }
              </div>
            </div>

            { error && <p className="text-sm text-destructive">{ error }</p> }

            <div className="rounded-lg border-2 border-border/60 bg-muted/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Button
                  variant="outline"
                  size="lg"
                  onClick={ handleDelete }
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                >
                  <Trash2 className="size-4 mr-1.5" />
                  Delete field
                </Button>
                <div className="flex w-full items-center justify-end gap-3 sm:w-auto">
                  <Button variant="outline" size="lg" className="min-w-[120px] flex-1 sm:flex-none" onClick={ handleCancel }>
                    Cancel
                  </Button>
                  <Button variant="primary" size="lg" onClick={ handleSave } disabled={ saving || hasAnyOverlap } className="min-w-[120px] flex-1 sm:flex-none">
                    { saving ? <Loader2 className="size-4 animate-spin mr-1.5" /> : null }
                    { saving ? 'Saving…' : 'Save' }
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>

      <AlertDialogRoot open={ confirmClose } onOpenChange={ setConfirmClose }>
        <AlertDialogContent>
          <AlertDialogTitle>{ dirty ? 'Unsaved changes' : 'Cancel editing?' }</AlertDialogTitle>
          <AlertDialogDescription>
            { dirty
              ? 'You have unsaved changes. Are you sure you want to discard them?'
              : 'Are you sure you want to cancel editing? All unsaved changes will be lost.' }
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={ () => setConfirmClose(false) }>{ dirty ? 'Keep editing' : 'No, keep editing' }</AlertDialogCancel>
            <AlertDialogAction onClick={ () => { forceCloseRef.current = true; setConfirmClose(false); } }>
              { dirty ? 'Discard' : 'Yes, cancel' }
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>

      <AlertDialogRoot open={ confirmDeleteField } onOpenChange={ setConfirmDeleteField }>
        <AlertDialogContent>
          <AlertDialogTitle>Delete this field?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete &ldquo;{ field.name }&rdquo;? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={ () => setConfirmDeleteField(false) }>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ handleConfirmDelete }>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>

      { seasonsQ.data && (
        <AlertDialogRoot
          open={ confirmClearSeasonId !== null }
          onOpenChange={ (open) => { if (!open) setConfirmClearSeasonId(null); } }
        >
          <AlertDialogContent>
            <AlertDialogTitle>Remove all vegetation cycles?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to remove all vegetation cycles for &ldquo;
              { seasonsQ.data.find((s) => s.id === confirmClearSeasonId)?.name ?? '' }
              &rdquo;? This action cannot be undone.
            </AlertDialogDescription>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={ () => setConfirmClearSeasonId(null) }>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={ handleConfirmClearSeason }>
                Remove all
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogRoot>
      ) }
    </Dialog.Root>
  );
}

function sowingDateLabel(seedingTypeId: number | null | undefined, isCutOff: boolean): string {
  switch (seedingTypeId) {
    case 1: return 'Sowing date';
    case 2: return 'Planting date';
    case 3: return isCutOff ? 'Cut-off (start) date' : 'Planting date';
    case 4: return 'Bud swelling start date';
    case 5: return 'Bud sprouting start date';
    default: return 'Sowing date';
  }
}

function CycleCard({
  cycle,
  allCycles,
  seasonId,
  seasonStartDate,
  seasonEndDate,
  cropsData,
  irrigationTypesData,
  tillageTypesData,
  onUpdateCycle,
  onRemoveCycle,
}: {
  cycle: VegetationCycleForm;
  allCycles: VegetationCycleForm[];
  seasonId: string;
  seasonStartDate?: string;
  seasonEndDate?: string;
  cropsData: Crop[] | undefined;
  irrigationTypesData: IrrigationType[] | undefined;
  tillageTypesData: TillageType[] | undefined;
  onUpdateCycle: (seasonId: string, cycleId: string, key: keyof VegetationCycleForm, value: string | number | boolean | null) => void;
  onRemoveCycle: (seasonId: string, cycleId: string) => void;
}) {
  const selectedCrop = cropsData?.find((c) => c.name === cycle.cropName) ?? null;
  const varietiesQ = useVarieties(selectedCrop?.id);
  const allVarieties = useMemo(() => varietiesQ.data?.items ?? [], [varietiesQ.data?.items]);
  const PAGE_SIZE = 20;
  const [varietyCount, setVarietyCount] = useState(PAGE_SIZE);
  const [varietyOpen, setVarietyOpen] = useState(false);
  const [confirmRemoveCycle, setConfirmRemoveCycle] = useState(false);
  const [varietySearch, setVarietySearch] = useState('');
  const varietyRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const filteredVarieties = varietySearch
    ? allVarieties.filter((v) => v.name.toLowerCase().includes(varietySearch.toLowerCase()))
    : allVarieties;
  const visibleVarieties = filteredVarieties.slice(0, varietyCount);
  const hasMore = filteredVarieties.length > varietyCount;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      if (!hasMore) return;
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 1) {
        setVarietyCount((v) => Math.min(v + PAGE_SIZE, filteredVarieties.length));
      }
    };
    el.addEventListener('scroll', onScroll);
    // Also check on mount (in case content fits without scrolling)
    requestAnimationFrame(() => {
      if (el.scrollHeight <= el.clientHeight && hasMore) {
        setVarietyCount(filteredVarieties.length);
      }
    });
    return () => el.removeEventListener('scroll', onScroll);
  }, [hasMore, filteredVarieties.length, varietySearch, varietyOpen]);

  useEffect(() => {
    if (varietyOpen) searchRef.current?.focus();
  }, [varietyOpen]);

  useEffect(() => {
    if (!varietyOpen) return;
    const handler = (e: MouseEvent) => {
      if (varietyRef.current && !varietyRef.current.contains(e.target as Node)) {
        setVarietyOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [varietyOpen]);

  const varietyDisabled = !selectedCrop || !selectedCrop.hasVariety;

  const maturityOpts = useMemo(() => {
    const opts: string[] = [];
    if (cycle.variety && selectedCrop) {
      const v = allVarieties.find((v) => v.name === cycle.variety);
      if (v?.maturityOptions) opts.push(...v.maturityOptions);
    }
    if (opts.length === 0 && selectedCrop?.maturityOptions) {
      opts.push(...selectedCrop.maturityOptions);
    }
    return opts;
  }, [cycle.variety, selectedCrop, allVarieties]);
  const maturityDisabled = maturityOpts.length === 0;
  const maturitySingle = maturityOpts.length === 1;
  const dateLabel = sowingDateLabel(selectedCrop?.seedingTypeId, cycle.isCutOff);
  const isPlantingCutting = selectedCrop?.seedingTypeId === 3;

  const overlapRanges = useMemo(() => getOverlapRanges(cycle.id, allCycles), [cycle.id, allCycles]);
  const blockedRanges = useMemo(
    () => getBlockedRanges(cycle.id, allCycles, seasonStartDate, seasonEndDate),
    [cycle.id, allCycles, seasonStartDate, seasonEndDate],
  );

  useEffect(() => {
    if (maturitySingle && cycle.maturity !== maturityOpts[0]) {
      onUpdateCycle(seasonId, cycle.id, 'maturity', maturityOpts[0]);
    }
  }, [maturitySingle, maturityOpts, cycle.maturity, seasonId, cycle.id, onUpdateCycle]);

  return (
    <div className="relative border-2 border-border/60 rounded-lg p-4 space-y-4">
      <button
        type="button"
        onClick={ () => setConfirmRemoveCycle(true) }
        className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
      >
        <Trash2 className="size-4" />
      </button>

      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Crop name</label>
        <Select
          value={ cycle.cropName }
          onValueChange={ (v) => {
            onUpdateCycle(seasonId, cycle.id, 'cropName', v);
            onUpdateCycle(seasonId, cycle.id, 'variety', '');
            onUpdateCycle(seasonId, cycle.id, 'maturity', '');
          } }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select crop" />
            { (() => {
              if (!cycle.cropName || !cropsData) return null;
              const sel = cropsData.find((c) => c.name === cycle.cropName);
              if (!sel) return null;
              const badges: React.ReactNode[] = [];
              const ENABLE = false;
              if (ENABLE && sel.hasVariety) badges.push(<Sprout key="v" className="size-3.5 text-success" />);
              if (ENABLE && sel.maturityOptions && sel.maturityOptions.length > 0) badges.push(<Timer key="m" className="size-3.5 text-warning" />);
              if (ENABLE && sel.seedingTypeId === 3) badges.push(<Scissors key="c" className="size-3.5 text-rose-500" />);
              return badges.length > 0 ? (
                <span className="ml-auto flex items-center gap-1">
                  { badges }
                </span>
              ) : null;
            })() }
          </SelectTrigger>
          <SelectContent>
            { (cropsData ?? []).map((crop) => {
              const badges: React.ReactNode[] = [];
              const ENABLE = false;
              if (ENABLE && crop.hasVariety) badges.push(<Sprout key="v" className="size-3.5 text-success" />);
              if (ENABLE && crop.maturityOptions && crop.maturityOptions.length > 0) badges.push(<Timer key="m" className="size-3.5 text-warning" />);
              if (ENABLE && crop.seedingTypeId === 3) badges.push(<Scissors key="c" className="size-3.5 text-rose-500" />);
              return (
                <SelectItem key={ crop.id } value={ crop.name }>
                  <span className="flex items-center gap-2">
                    <span>{ crop.name }</span>
                    { badges.length > 0 && (
                      <span className="flex items-center gap-1">
                        { badges }
                      </span>
                    ) }
                  </span>
                </SelectItem>
              );
            }) }
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        <div ref={ varietyRef } className="relative">
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Variety</label>
          <button
            type="button"
            disabled={ varietyDisabled }
            onClick={ () => { setVarietyOpen(!varietyOpen); setVarietySearch(''); setVarietyCount(PAGE_SIZE); } }
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-left focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
          >
            { cycle.variety || <span className="text-muted-foreground">{ varietyDisabled ? 'Not available' : 'Search variety…' }</span> }
          </button>
          { varietyOpen && !varietyDisabled && (
            <div className="absolute z-picker mt-1 w-full rounded-md border border-border bg-popover text-popover-foreground shadow-e2">
              <div className="p-1">
                <input
                  ref={ searchRef }
                  type="text"
                  value={ varietySearch }
                  onChange={ (e) => { setVarietySearch(e.target.value); setVarietyCount(PAGE_SIZE); } }
                  placeholder="Type to search…"
                  className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm focus:border-primary focus:outline-none"
                />
              </div>
              <div ref={ scrollRef } className="max-h-48 overflow-y-auto p-1">
                { visibleVarieties.length === 0 && (
                  <div className="px-2 py-3 text-xs text-muted-foreground text-center">No varieties found</div>
                ) }
                { visibleVarieties.map((v) => (
                  <div
                    key={ v.id }
                    role="option"
                    aria-selected={ cycle.variety === v.name }
                    onClick={ () => { onUpdateCycle(seasonId, cycle.id, 'variety', v.name); setVarietyOpen(false); } }
                    className={ cn(
                      'flex cursor-default items-center rounded-sm px-2 py-1.5 text-sm',
                      cycle.variety === v.name ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
                    ) }
                  >
                    { v.name }
                  </div>
                )) }
              </div>
            </div>
          ) }
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Maturity</label>
          <Select
            value={ cycle.maturity }
            onValueChange={ (v) => onUpdateCycle(seasonId, cycle.id, 'maturity', v) }
            disabled={ maturityDisabled || maturitySingle }
          >
            <SelectTrigger>
              <SelectValue placeholder={ maturityDisabled ? 'Not available' : 'Select maturity' } />
            </SelectTrigger>
            <SelectContent>
              { maturityOpts.map((opt) => (
                <SelectItem key={ opt } value={ opt }>{ opt }</SelectItem>
              )) }
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{ dateLabel }</label>
          <DatePicker
            value={ cycle.plantingDate }
            onChange={ (v) => onUpdateCycle(seasonId, cycle.id, 'plantingDate', v) }
            minDate={ seasonStartDate }
            maxDate={ seasonEndDate }
            overlapRanges={ overlapRanges }
            blockedRanges={ blockedRanges }
            showLegend
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Harvesting date</label>
          <DatePicker
            value={ cycle.harvestingDate }
            onChange={ (v) => onUpdateCycle(seasonId, cycle.id, 'harvestingDate', v) }
            disabled={ !cycle.plantingDate }
            minDate={ cycle.plantingDate ? (() => {
              const [y, m, d] = cycle.plantingDate.split('-').map(Number);
              const dt = new Date(y, m - 1, d);
              dt.setDate(dt.getDate() + 1);
              const yy = dt.getFullYear();
              const mm = String(dt.getMonth() + 1).padStart(2, '0');
              const dd = String(dt.getDate()).padStart(2, '0');
              const min = `${yy}-${mm}-${dd}`;
              return seasonStartDate && min < seasonStartDate ? seasonStartDate : min;
            })() : seasonStartDate }
            maxDate={ seasonEndDate }
            overlapRanges={ overlapRanges }
            blockedRanges={ blockedRanges }
            showLegend
          />
        </div>

        { isPlantingCutting ? (
          <div className="col-span-2 -mt-1">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ cycle.isCutOff }
                onChange={ (e) => onUpdateCycle(seasonId, cycle.id, 'isCutOff', e.target.checked) }
                className="size-4 rounded border-border accent-primary"
              />
              <span className="text-xs text-muted-foreground">Cut-off (start) date</span>
            </label>
          </div>
        ) : (
          <div className="col-span-2 h-5" />
        ) }

        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Irrigation type</label>
          <Select
            value={ cycle.irrigationType }
            onValueChange={ (v) => onUpdateCycle(seasonId, cycle.id, 'irrigationType', v) }
          >
            <SelectTrigger>
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              { (irrigationTypesData ?? []).map((opt) => (
                <SelectItem key={ opt.id } value={ opt.name }>{ opt.name }</SelectItem>
              )) }
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Tillage type</label>
          <Select
            value={ cycle.tillageType }
            onValueChange={ (v) => onUpdateCycle(seasonId, cycle.id, 'tillageType', v) }
          >
            <SelectTrigger>
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              { (tillageTypesData ?? []).map((opt) => (
                <SelectItem key={ opt.id } value={ opt.name }>{ opt.name }</SelectItem>
              )) }
            </SelectContent>
          </Select>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Target yield (t/ha)</label>
          <input
            type="number"
            min={ 0 }
            step={ 0.01 }
            value={ cycle.targetYield ?? '' }
            onChange={ (e) => onUpdateCycle(seasonId, cycle.id, 'targetYield', e.target.value ? Number(e.target.value) : null) }
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Actual yield (t/ha)</label>
          <input
            type="number"
            min={ 0 }
            step={ 0.01 }
            value={ cycle.actualYield ?? '' }
            onChange={ (e) => onUpdateCycle(seasonId, cycle.id, 'actualYield', e.target.value ? Number(e.target.value) : null) }
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>

      <div>
        <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Notes</label>
        <input
          value={ cycle.notes }
          onChange={ (e) => onUpdateCycle(seasonId, cycle.id, 'notes', e.target.value) }
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      <AlertDialogRoot open={ confirmRemoveCycle } onOpenChange={ setConfirmRemoveCycle }>
        <AlertDialogContent>
          <AlertDialogTitle>Remove vegetation cycle?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to remove this vegetation cycle? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={ () => setConfirmRemoveCycle(false) }>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ () => { setConfirmRemoveCycle(false); onRemoveCycle(seasonId, cycle.id); } }>
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </div>
  );
}
