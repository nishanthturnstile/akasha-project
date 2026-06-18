import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Pencil, RotateCcw, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { useConfig } from '@/lib/queries';
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
  const [isRedrawing, setIsRedrawing] = useState(false);

  const drawRef = useRef<TerraDraw | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

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
    const bounds = polygonBounds(field.geometry);
    if (bounds) {
      map.fitBounds(bounds, { padding: 24, maxZoom: 18 });
    }
  }, [field.geometry]);

  const stopDraw = useCallback(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    drawRef.current = null;
    setIsRedrawing(false);
  }, []);

  // TerraDraw initialised only during active redraw — fresh polygon mode, no pre-loaded geometry
  useEffect(() => {
    if (!open || !miniMap || isMultiPart || !isRedrawing) return;

    let cancelled = false;

    void (async () => {
      try {
        const [{ TerraDraw, TerraDrawPolygonMode }, { TerraDrawMapLibreGLAdapter }] =
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
                outlineOpacity: 1,
                outlineWidth: 3,
              },
            }),
          ],
        });

        draw.start();
        draw.setMode('polygon');
        drawRef.current = draw;

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
  }, [open, miniMap, isRedrawing, isMultiPart, stopDraw]);

  const handleRedraw = useCallback(() => {
    setEditedGeometry(null);
    setIsRedrawing(true);
  }, []);

  const handleCancelRedraw = useCallback(() => {
    stopDraw();
    setEditedGeometry(null);
    setError(null);
  }, [stopDraw]);

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
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit field"
          className="glass fixed left-1/2 top-[18vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit field</Dialog.Title>
            <Dialog.Description>Edit field name and adjust its boundary on the map.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
            <h3 className="text-base font-display font-semibold">Edit field</h3>
            <Dialog.Close asChild>
              <button aria-label="Close" className="rounded-md p-1 text-muted-foreground hover:bg-accent/40">
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="p-4 space-y-4">
            {basemapResolution ? (
              <div className="relative h-[260px] w-full rounded-lg overflow-hidden border border-border">
                <MapLayerManager
                  basemap={basemapResolution}
                  center={center}
                  zoom={15}
                  scene={null}
                  opacity={1}
                  visible={true}
                  onBasemapError={() => {}}
                  onMapReady={handleMapReady}
                />
                {miniMap && !isRedrawing && (
                  <FieldBoundaryLayer
                    map={miniMap}
                    plot={null}
                    geometry={field.geometry}
                    featureId={`edit-field-${field.id}`}
                    name={field.name}
                  />
                )}
                {isMultiPart && (
                  <div className="absolute inset-0 flex items-center justify-center bg-background/60 text-sm text-muted-foreground">
                    Multi-part field editing is not available in this dialog.
                  </div>
                )}
                {!isMultiPart && open && (
                  <div className="absolute bottom-2 right-2 flex gap-1">
                    {isRedrawing ? (
                      <button
                        type="button"
                        onClick={handleCancelRedraw}
                        className="rounded bg-background/80 px-2 py-1 text-[11px] text-foreground shadow hover:bg-background transition-colors"
                      >
                        Cancel redraw
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleRedraw}
                        className="flex items-center gap-1 rounded bg-background/80 px-2 py-1 text-[11px] text-foreground shadow hover:bg-background transition-colors"
                      >
                        <RotateCcw className="size-3" strokeWidth={1.75} />
                        Redraw
                      </button>
                    )}
                  </div>
                )}
                {!isMultiPart && isRedrawing && open && (
                  <div className="absolute top-2 left-2 flex items-center gap-1.5 rounded bg-background/80 px-2 py-1 text-[11px] text-muted-foreground shadow">
                    <Pencil className="size-3" strokeWidth={1.75} />
                    Click to place vertices, double-click to close
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-[260px] rounded-lg border border-border bg-muted/30 text-sm text-muted-foreground">
                Loading map…
              </div>
            )}

            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Field name</label>
              <input
                className="rounded-md border border-border bg-background px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="text-sm text-muted-foreground">
              Area: {currentArea != null ? `${currentArea.toFixed(2)} ha` : '—'}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3">
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDelete}
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                >
                  Delete field
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Dialog.Close asChild>
                  <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm">
                    Cancel
                  </button>
                </Dialog.Close>
                <Button variant="primary" size="sm" onClick={handleSave}>
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
