import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { ChevronDown, ChevronRight, Plus, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { useConfig, useSeasons } from '@/lib/queries';
import { resolveBasemapConfig } from '@/map/basemap';
import { polygonAreaMeters } from '@/lib/measure';
import type maplibregl from 'maplibre-gl';
import type { TerraDraw } from 'terra-draw';
import type { Field, PlotGeometry } from '@/types/api';

interface Props {
  field: Field;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (fieldId: string, name: string, geometry?: PlotGeometry) => void;
  onDelete?: (fieldId: string) => void;
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

const CROP_OPTIONS = [
  'Wheat', 'Rice', 'Corn', 'Soybean', 'Barley', 'Cotton', 'Sugarcane',
  'Potato', 'Tomato', 'Sunflower', 'Mustard', 'Groundnut', 'Pulses', 'Other',
];

const IRRIGATION_OPTIONS = [
  'Drip', 'Sprinkler', 'Flood', 'Furrow', 'Center pivot', 'Rainfed', 'Other',
];

const TILLAGE_OPTIONS = [
  'Conventional', 'Reduced', 'No-till', 'Strip-till', 'Conservation', 'Other',
];

interface VegetationCycleForm {
  id: string;
  cropName: string;
  plantingDate: string;
  irrigationType: string;
  targetYield: number | null;
  harvestingDate: string;
  tillageType: string;
  actualYield: number | null;
  notes: string;
}

export default function EditFieldDialog({
  field,
  open,
  onOpenChange,
  onSave,
  onDelete,
}: Props) {
  const [name, setName] = useState(field.name);
  const [error, setError] = useState<string | null>(null);
  const [miniMap, setMiniMap] = useState<maplibregl.Map | null>(null);
  const [editedGeometry, setEditedGeometry] = useState<PlotGeometry | null>(null);

  const drawRef = useRef<TerraDraw | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  const seasonsQ = useSeasons();
  const [expandedSeasons, setExpandedSeasons] = useState<Set<string>>(new Set());
  const [vegetationCycles, setVegetationCycles] = useState<Record<string, VegetationCycleForm[]>>({});

  const configQ = useConfig();

  const basemapResolution = useMemo(() => {
    if (!configQ.data) return null;
    try { return resolveBasemapConfig(configQ.data); }
    catch { return null; }
  }, [configQ.data]);

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
        const [{ TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode }, { TerraDrawMapLibreGLAdapter }] =
          await Promise.all([import('terra-draw'), import('terra-draw-maplibre-gl-adapter')]);

        if (cancelled) return;

        const draw = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map: miniMap, prefixId: 'edit-dialog-draw' }),
          modes: [
            new TerraDrawPolygonMode({
              styles: {
                fillColor: '#3b82f6',
                fillOpacity: 0.25,
                outlineColor: '#2563eb',
                outlineWidth: 3,
              },
            }),
            new TerraDrawSelectMode({
              styles: {
                selectedPolygonColor: '#3b82f6',
                selectedPolygonFillOpacity: 0.25,
                selectedPolygonOutlineColor: '#2563eb',
                selectedPolygonOutlineWidth: 3,
              },
              flags: {
                polygon: {
                  feature: {
                    coordinates: {
                      draggable: true,
                      midpoints: { draggable: true },
                      deletable: true,
                    },
                  },
                },
              },
            }),
          ],
        });

        draw.start();
        draw.setMode('select');
        drawRef.current = draw;

        if (field.geometry.type === 'Polygon') {
          const results = draw.addFeatures([
            {
              type: 'Feature',
              geometry: field.geometry,
              properties: { mode: 'polygon' },
            },
          ]);
          const id = results[0]?.id;
          if (id) draw.selectFeature(id);
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
  }, [open, miniMap, isMultiPart, stopDraw, field.geometry]);

  const toggleSeason = useCallback((seasonId: string) => {
    setExpandedSeasons((prev) => {
      const next = new Set(prev);
      if (next.has(seasonId)) next.delete(seasonId);
      else next.add(seasonId);
      return next;
    });
  }, []);

  const addCycle = useCallback((seasonId: string) => {
    const newCycle: VegetationCycleForm = {
      id: crypto.randomUUID(),
      cropName: '',
      plantingDate: '',
      irrigationType: '',
      targetYield: null,
      harvestingDate: '',
      tillageType: '',
      actualYield: null,
      notes: '',
    };
    setVegetationCycles((prev) => ({
      ...prev,
      [seasonId]: [...(prev[seasonId] ?? []), newCycle],
    }));
  }, []);

  const removeCycle = useCallback((seasonId: string, cycleId: string) => {
    setVegetationCycles((prev) => ({
      ...prev,
      [seasonId]: (prev[seasonId] ?? []).filter((c) => c.id !== cycleId),
    }));
  }, []);

  const clearSeasonCycles = useCallback((seasonId: string) => {
    setVegetationCycles((prev) => ({
      ...prev,
      [seasonId]: [],
    }));
    setExpandedSeasons((prev) => {
      const next = new Set(prev);
      next.delete(seasonId);
      return next;
    });
  }, []);

  const updateCycle = useCallback(
    (seasonId: string, cycleId: string, field: keyof VegetationCycleForm, value: string | number | null) => {
      setVegetationCycles((prev) => ({
        ...prev,
        [seasonId]: (prev[seasonId] ?? []).map((c) =>
          c.id === cycleId ? { ...c, [field]: value } : c,
        ),
      }));
    },
    [],
  );

  const handleSave = () => {
    if (!name.trim()) {
      setError('Field name is required');
      return;
    }
    setError(null);
    onSave?.(
      field.id,
      name.trim(),
      geometryChanged ? (editedGeometry as PlotGeometry) : undefined,
    );
    if (!geometryChanged && !editedGeometry) {
      // Name-only save - just close
    }
    onOpenChange(false);
  };

  const handleDelete = () => {
    onDelete?.(field.id);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={ open } onOpenChange={ onOpenChange }>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit field"
          onInteractOutside={ (e) => e.preventDefault() }
          onEscapeKeyDown={ (e) => e.preventDefault() }
          className="glass fixed left-1/2 top-[8vh] z-popover w-[min(56rem,calc(100vw-3rem))] -translate-x-1/2 overflow-y-auto max-h-[88vh] rounded-xl p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit field</Dialog.Title>
            <Dialog.Description>Edit field name and adjust its boundary on the map.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
            <h3 className="text-lg font-display font-semibold">Edit field</h3>
            <Dialog.Close asChild>
              <button aria-label="Close" className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/40">
                <X className="size-5" />
              </button>
            </Dialog.Close>
          </div>

          <div className="p-6 space-y-6">
            <div className="grid grid-cols-2 gap-6">
              {/* Left column: mini-map with polygon edit */ }
              <div>
                { basemapResolution ? (
                  <div className="relative h-80 w-full rounded-xl overflow-hidden border border-border">
                    <MapLayerManager
                      basemap={ basemapResolution }
                      center={ center }
                      zoom={ 15 }
                      scene={ null }
                      opacity={ 1 }
                      visible={ true }
                      onBasemapError={ () => {} }
                      onMapReady={ handleMapReady }
                    />
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
                  <div className="flex h-80 items-center justify-center rounded-xl border border-border bg-muted/30 text-sm text-muted-foreground">
                    Loading map…
                  </div>
                ) }
              </div>

              {/* Right column: field details */ }
              <div className="space-y-5">
                <div className="grid grid-cols-1 gap-2">
                  <label className="text-sm font-medium text-foreground">Field name</label>
                  <input
                    className="rounded-lg border border-border bg-background px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                    value={ name }
                    onChange={ (e) => setName(e.target.value) }
                  />
                </div>

                <div className="rounded-lg border border-border/60 bg-muted/10 px-4 py-3">
                  <span className="text-sm text-muted-foreground">Area: </span>
                  <span className="text-sm font-semibold text-foreground">
                    { currentArea != null ? `${currentArea.toFixed(2)} ha` : '—' }
                  </span>
                </div>

                { seasonsQ.data && (
                  <div className="border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-border/60">
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
                            <div key={ season.id } className="border border-border/60 rounded-lg overflow-hidden">
                              <div className={ cn(
                                'flex w-full items-center justify-between px-4 py-3 text-sm font-medium bg-gray-200/70 text-gray-800',
                                isExpanded ? 'bg-gray-300/70 text-gray-900' : 'hover:bg-gray-100',
                              ) }>
                                <button
                                  type="button"
                                  onClick={ () => toggleSeason(season.id) }
                                  className="flex items-center gap-2 flex-1 text-left"
                                >
                                  { isExpanded
                                    ? <ChevronDown className="size-4 text-gray-600 shrink-0" />
                                    : <ChevronRight className="size-4 text-gray-600 shrink-0" /> }
                                  <span>{ season.name }</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={ () => clearSeasonCycles(season.id) }
                                  className="rounded-md p-1 text-black hover:text-destructive hover:bg-destructive/10 transition-colors"
                                  title="Remove all vegetation cycles"
                                >
                                  <Trash2 className="size-4" />
                                </button>
                              </div>
                              { isExpanded && (
                                <div className="border-t border-border/60 p-4 space-y-4">
                                  { cycles.length === 0 && (
                                    <p className="text-sm text-muted-foreground">No vegetation cycles added yet.</p>
                                  ) }
                                  { cycles.map((cycle) => (
                                    <div key={ cycle.id } className="relative border border-border/50 rounded-lg p-4 space-y-4">
                                      <button
                                        type="button"
                                        onClick={ () => removeCycle(season.id, cycle.id) }
                                        className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                                      >
                                        <Trash2 className="size-4" />
                                      </button>
                                      <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Crop name</label>
                                        <Select
                                          value={ cycle.cropName }
                                          onValueChange={ (v) => updateCycle(season.id, cycle.id, 'cropName', v) }
                                        >
                                          <SelectTrigger>
                                            <SelectValue placeholder="Select crop" />
                                          </SelectTrigger>
                                          <SelectContent>
                                            { CROP_OPTIONS.map((crop) => (
                                              <SelectItem key={ crop } value={ crop }>{ crop }</SelectItem>
                                            )) }
                                          </SelectContent>
                                        </Select>
                                      </div>

                                      <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-4">
                                          <div>
                                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Planting date</label>
                                            <DatePicker
                                              value={ cycle.plantingDate }
                                              onChange={ (v) => updateCycle(season.id, cycle.id, 'plantingDate', v) }
                                            />
                                          </div>
                                          <div>
                                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Irrigation type</label>
                                            <Select
                                              value={ cycle.irrigationType }
                                              onValueChange={ (v) => updateCycle(season.id, cycle.id, 'irrigationType', v) }
                                            >
                                              <SelectTrigger>
                                                <SelectValue placeholder="Select" />
                                              </SelectTrigger>
                                              <SelectContent>
                                                { IRRIGATION_OPTIONS.map((opt) => (
                                                  <SelectItem key={ opt } value={ opt }>{ opt }</SelectItem>
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
                                              onChange={ (e) => updateCycle(season.id, cycle.id, 'targetYield', e.target.value ? Number(e.target.value) : null) }
                                              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                                            />
                                          </div>
                                        </div>

                                        <div className="space-y-4">
                                          <div>
                                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Harvesting date</label>
                                            <DatePicker
                                              value={ cycle.harvestingDate }
                                              onChange={ (v) => updateCycle(season.id, cycle.id, 'harvestingDate', v) }
                                            />
                                          </div>
                                          <div>
                                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Tillage type</label>
                                            <Select
                                              value={ cycle.tillageType }
                                              onValueChange={ (v) => updateCycle(season.id, cycle.id, 'tillageType', v) }
                                            >
                                              <SelectTrigger>
                                                <SelectValue placeholder="Select" />
                                              </SelectTrigger>
                                              <SelectContent>
                                                { TILLAGE_OPTIONS.map((opt) => (
                                                  <SelectItem key={ opt } value={ opt }>{ opt }</SelectItem>
                                                )) }
                                              </SelectContent>
                                            </Select>
                                          </div>
                                          <div>
                                            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Actual yield (t/ha)</label>
                                            <input
                                              type="number"
                                              min={ 0 }
                                              step={ 0.01 }
                                              value={ cycle.actualYield ?? '' }
                                              onChange={ (e) => updateCycle(season.id, cycle.id, 'actualYield', e.target.value ? Number(e.target.value) : null) }
                                              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                                            />
                                          </div>
                                        </div>
                                      </div>

                                      <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Notes</label>
                                        <input
                                          value={ cycle.notes }
                                          onChange={ (e) => updateCycle(season.id, cycle.id, 'notes', e.target.value) }
                                          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                                        />
                                      </div>
                                    </div>
                                  )) }
                                  <button
                                    type="button"
                                    onClick={ () => addCycle(season.id) }
                                    className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/60 px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
                                  >
                                    <Plus className="size-4" strokeWidth={ 1.75 } />
                                    Add vegetation cycle
                                  </button>
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

            <div className="flex items-center justify-between gap-3 border-t border-border/60 pt-4">
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={ handleDelete }
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                >
                  Delete field
                </Button>
              </div>
              <div className="flex items-center gap-3">
                <Dialog.Close asChild>
                  <button type="button" className="rounded-lg border border-border px-4 py-2 text-sm text-foreground hover:bg-accent/40 transition-colors">
                    Cancel
                  </button>
                </Dialog.Close>
                <Button variant="primary" size="md" onClick={ handleSave }>
                  Save
                </Button>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
