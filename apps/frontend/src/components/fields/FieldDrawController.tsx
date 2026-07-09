import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Check, Pencil, X } from 'lucide-react';
import type { TerraDraw, GeoJSONStoreGeometries } from 'terra-draw';
import { Button } from '@/components/ui/button';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import type { Plot, PlotGeometry, PlotUpdatePayload } from '@/types/api';

export type FieldDrawMode = 'draw' | 'edit' | null;

export type DrawShapeMode = 'polygon' | 'circle';

interface FieldDrawControllerProps {
  activeTool: ActiveMapTool;
  className?: string;
  map: maplibregl.Map | null;
  mode: FieldDrawMode;
  onCancel: () => void;
  onCreateField?: (payload: { name: string; geometry: PlotGeometry }) => Promise<Plot> | Plot;
  onReleaseTool: (owner: MapToolOwner) => void;
  onRequestTool: (owner: MapToolOwner) => boolean;
  onUpdateField: (plotId: string, payload: PlotUpdatePayload) => Promise<Plot | void> | Plot | void;
  selectedPlot: Plot | null;
  drawResetKey?: number;
  onPolygonComplete?: (geometry: PlotGeometry | null, featureId?: string) => void;
  drawMode?: DrawShapeMode;
  multiDraw?: boolean;
  hideCard?: boolean;
  enableVertexDrag?: boolean;
  onDrawReady?: (draw: TerraDraw) => void;
  onGeometryChange?: (geometry: PlotGeometry, featureId?: string) => void;
}

type TerraDrawFeature = Parameters<TerraDraw['addFeatures']>[0][number];
type TerraDrawPolygonFeature = TerraDrawFeature & { geometry: { type: 'Polygon' } };

function isPolygonGeometry(geometry: PlotGeometry | { type?: string } | undefined): geometry is PlotGeometry & { type: 'Polygon' } {
  return geometry?.type === 'Polygon';
}

function latestPolygon(draw: TerraDraw): PlotGeometry | null {
  const features = draw.getSnapshot().filter((feature) => feature.geometry.type === 'Polygon');
  const feature = features[features.length - 1];
  return feature?.geometry.type === 'Polygon' ? (feature.geometry as PlotGeometry) : null;
}

function toEditableFeature(plot: Plot): TerraDrawPolygonFeature {
  return {
    type: 'Feature',
    id: plot.id,
    geometry: plot.geometry as TerraDrawPolygonFeature['geometry'],
    properties: { fieldId: plot.id },
  } as TerraDrawPolygonFeature;
}

export function FieldDrawController({
  activeTool,
  className,
  map,
  mode,
  onCancel,
  onCreateField,
  onReleaseTool,
  onRequestTool,
  onUpdateField,
  selectedPlot,
  drawResetKey = 0,
  onPolygonComplete,
  drawMode = 'polygon',
  multiDraw = false,
  hideCard = false,
  enableVertexDrag = false,
  onDrawReady,
  onGeometryChange,
}: FieldDrawControllerProps) {
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const drawRef = useRef<TerraDraw | null>(null);
  const startedRef = useRef(false);
  const modeRef = useRef<FieldDrawMode>(mode);
  modeRef.current = mode;
  const selectedPlotRef = useRef<Plot | null>(selectedPlot);
  selectedPlotRef.current = selectedPlot;
  const onPolygonCompleteRef = useRef<typeof onPolygonComplete>(onPolygonComplete);
  onPolygonCompleteRef.current = onPolygonComplete;
  const drawModeRef = useRef<DrawShapeMode>(drawMode);
  drawModeRef.current = drawMode;
  const multiDrawRef = useRef(multiDraw);
  multiDrawRef.current = multiDraw;
  const enableVertexDragRef = useRef(enableVertexDrag);
  enableVertexDragRef.current = enableVertexDrag;
  const onDrawReadyRef = useRef(onDrawReady);
  onDrawReadyRef.current = onDrawReady;
  const onGeometryChangeRef = useRef(onGeometryChange);
  onGeometryChangeRef.current = onGeometryChange;
  const vertexCountRef = useRef(0);

  const owner = mode === 'draw' ? 'field-draw' : mode === 'edit' ? 'field-edit' : null;
  const isActiveOwner = owner != null && activeTool === owner;
  const canEditSelectedPlot = selectedPlot ? isPolygonGeometry(selectedPlot.geometry) : false;

  const stopDraw = useCallback(() => {
    const draw = drawRef.current;
    if (draw && startedRef.current) {
      startedRef.current = false;
      try {
        draw.clear();
      } catch {
        // Terra Draw can already be disabled during React cleanup/re-renders.
      }
      try {
        draw.stop();
      } catch {
        // Cleanup must stay idempotent so draw failures do not blank the map.
      }
    }
    drawRef.current = null;
    setDraftGeometry(null);
    setIsSaving(false);
    setError(null);
    if (owner) onReleaseTool(owner);
  }, [onReleaseTool, owner]);

  const ensureDraw = useCallback(async (): Promise<TerraDraw | null> => {
    if (!map) return null;
    if (!drawRef.current) {
      const [
        { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode, TerraDrawCircleMode },
        { TerraDrawMapLibreGLAdapter },
      ] = await Promise.all([import('terra-draw'), import('terra-draw-maplibre-gl-adapter')]);
      const polygonStyles = {
        fillColor: '#3b82f6' as const,
        fillOpacity: 0.25 as const,
        outlineColor: '#2563eb' as const,
        outlineOpacity: 1 as const,
        outlineWidth: 3 as const,
        outlineDashStyle: [6, 4] as unknown as [number, number],
        closingPointColor: '#22c55e' as const,
        closingPointWidth: 8 as const,
        closingPointOutlineColor: '#ffffff' as const,
        closingPointOutlineWidth: 2 as const,
        coordinatePointColor: '#3b82f6' as const,
        coordinatePointWidth: 5 as const,
        coordinatePointOutlineColor: '#ffffff' as const,
        coordinatePointOutlineWidth: 1.5 as const,
      };
      const circleStyles = {
        fillColor: '#3b82f6' as const,
        fillOpacity: 0.25 as const,
        outlineColor: '#2563eb' as const,
        outlineOpacity: 1 as const,
        outlineWidth: 3 as const,
      };
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map, prefixId: 'field-draw' }),
        modes: [
          new TerraDrawPolygonMode({ styles: polygonStyles }),
          new TerraDrawCircleMode({
            styles: circleStyles as Record<string, unknown>,
            segments: 64,
            projection: 'web-mercator',
          }),
          enableVertexDragRef.current
            ? new TerraDrawSelectMode({
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
              })
            : new TerraDrawSelectMode(),
        ],
      });
      draw.on('finish', (id) => {
        if (modeRef.current !== 'draw') return;
        let feature;
        try {
          feature = draw.getSnapshotFeature(id);
        } catch {
          return;
        }
        if (feature?.geometry.type !== 'Polygon') return;
        const geometry = feature.geometry as PlotGeometry;
        setDraftGeometry(geometry);

        if (multiDrawRef.current) {
          if (enableVertexDragRef.current) {
            // Re-add the feature so SelectMode picks up the draggable flags
            // (programmatic selectFeature often only highlights, not enables
            // interactive vertex handles).
            try { draw.removeFeatures([id]); } catch { /* ignore */ }
            const results = draw.addFeatures([
              {
                type: 'Feature',
                geometry: geometry as GeoJSONStoreGeometries,
                properties: { mode: 'polygon' },
              },
            ]);
            const newId = results[0]?.id ?? id;
            try { draw.setMode('select'); draw.selectFeature(newId); } catch { /* ignore */ }
            onPolygonCompleteRef.current?.(geometry, String(newId));
            setDraftGeometry(geometry);
            if (map && typeof map.getCanvas === 'function') {
              map.getCanvas().style.cursor = 'grab';
            }
          } else {
            onPolygonCompleteRef.current?.(geometry, String(id));
            // In multi-draw mode, clear the shape and stay in draw mode
            // so the user can immediately draw the next field.
            try { draw.clear(); } catch { /* ignore */ }
            setDraftGeometry(null);
            if (map && typeof map.getCanvas === 'function') {
              map.getCanvas().style.cursor = 'crosshair';
            }
          }
          return;
        }

        onPolygonCompleteRef.current?.(geometry, String(id));
        // Switch to select mode so the finished shape stays visible but the user
        // cannot accidentally start a second polygon on the next click.
        try {
          draw.setMode('select');
          draw.selectFeature(id);
        } catch {
          // Ignore mode-switch errors during cleanup.
        }
        if (map && typeof map.getCanvas === 'function') {
          map.getCanvas().style.cursor = 'grab';
        }
      });
      draw.on('change', (changedId) => {
        if (modeRef.current === 'draw') {
          const changedFeatureId = changedId?.[0];
          const changedFeature = changedFeatureId !== undefined
            ? draw.getSnapshotFeature(changedFeatureId)
            : undefined;
          const anyPolygon = !changedFeature
            ? draw.getSnapshot().find((f) => f.geometry.type === 'Polygon')
            : undefined;
          const refFeature = changedFeature ?? anyPolygon;
          const ring = refFeature?.geometry?.type === 'Polygon'
            ? (refFeature.geometry as PlotGeometry).coordinates[0]
            : undefined;
          const count = ring?.length ?? 0;
          if (count !== vertexCountRef.current) {
            vertexCountRef.current = count;
            if (map) {
              const canvas = map.getCanvas();
              canvas.style.cursor = count >= 4 ? 'grab' : 'crosshair';
            }
          }
          if (enableVertexDragRef.current && changedFeature && changedFeature.geometry.type === 'Polygon') {
            onGeometryChangeRef.current?.(changedFeature.geometry as PlotGeometry, String(changedFeatureId));
          }
        }
        if (modeRef.current !== 'edit') return;
        const geometry = latestPolygon(draw);
        if (geometry) setDraftGeometry(geometry);
      });
      drawRef.current = draw;
    }
    if (!startedRef.current) {
      drawRef.current.start();
      startedRef.current = true;
      onDrawReadyRef.current?.(drawRef.current);
    }
    return drawRef.current;
  }, [map]);

  useEffect(() => {
    if (!mode || !owner) {
      stopDraw();
      return;
    }
    if (!map) return;
    if (activeTool && activeTool !== owner) {
      if (startedRef.current) {
        stopDraw();
      } else if (!onRequestTool(owner)) {
        onCancel();
      }
      return;
    }
    if (!onRequestTool(owner)) {
      onCancel();
      return;
    }

    let cancelled = false;
    void (async () => {
      const draw = await ensureDraw();
      if (!draw || cancelled) return;
      if (mode === 'draw') {
        if (!enableVertexDragRef.current) {
          try { draw.clear(); } catch { /* ignore */ }
        }
        setDraftGeometry(null);
        setError(null);
        try {
          draw.setMode(drawModeRef.current === 'circle' ? 'circle' : 'polygon');
        } catch {
          // Ignore mode-switch errors.
        }
        if (map && typeof map.getCanvas === 'function') {
          map.getCanvas().style.cursor = 'crosshair';
        }
        return;
      }

      // Edit mode — always clear existing features
      try { draw.clear(); } catch { /* ignore */ }
      setDraftGeometry(null);
      setError(null);

      if (!selectedPlot) {
        setError('Select a field before editing its boundary.');
        return;
      }
      if (!isPolygonGeometry(selectedPlot.geometry)) {
        setError('Multi-part field editing is not available in this first field workflow.');
        return;
      }

      const validation = draw.addFeatures([toEditableFeature(selectedPlot)]);
      const invalid = validation.find((result) => result.valid === false);
      if (invalid) {
        setError('Unable to load the selected field into the editor.');
        return;
      }
      try {
        draw.setMode('select');
        draw.selectFeature(selectedPlot.id);
      } catch {
        // Ignore mode-switch errors during cleanup.
      }
      setDraftGeometry(selectedPlot.geometry);
    })();

    return () => {
      cancelled = true;
    };
  }, [activeTool, ensureDraw, map, mode, onCancel, onRequestTool, owner, selectedPlot, stopDraw]);

  useEffect(() => {
    return () => stopDraw();
  }, [stopDraw]);

  useEffect(() => {
    if (drawResetKey === 0) return;
    const draw = drawRef.current;
    if (!draw) return;
    // Soft-reset: clear the current sketch and return to polygon/circle mode
    // so the user can immediately start a fresh drawing.
    try {
      draw.clear();
    } catch {
      /* ignore */
    }
    try {
      draw.setMode(drawModeRef.current === 'circle' ? 'circle' : 'polygon');
    } catch {
      /* ignore */
    }
    setDraftGeometry(null);
    onPolygonComplete?.(null);
    vertexCountRef.current = 0;
    if (map) map.getCanvas().style.cursor = 'crosshair';
  }, [drawResetKey, map, onPolygonComplete]);

  const title = mode === 'draw' ? (multiDraw ? 'Add fields' : 'Save new field') : 'Save boundary edit';
  const hint = useMemo(() => {
    if (error) return error;
    if (mode === 'draw') {
      if (draftGeometry) return multiDraw ? 'Field added to the list. Draw another or save all.' : 'Name the field and save it to Akasha.';
      return drawMode === 'circle'
        ? 'Click to place the circle center, then click to set the radius.'
        : 'Click vertices on the map, then double-click to close the field.';
    }
    return draftGeometry ? 'Adjust the selected field, then save the boundary.' : 'Select and adjust the field boundary on the map.';
  }, [draftGeometry, error, mode, drawMode, multiDraw]);

  const [fieldName, setFieldName] = useState('');

  const save = async () => {
    if (!draftGeometry || !mode) return;
    setIsSaving(true);
    setError(null);
    try {
      if (mode === 'draw') {
        const name = fieldName.trim() || 'Untitled field';
        if (!onCreateField) {
          setError('Create field handler is not available.');
          return;
        }
        await onCreateField({ name, geometry: draftGeometry });
      } else {
        if (!selectedPlot) {
          setError('Select a field before saving edits.');
          return;
        }
        await onUpdateField(selectedPlot.id, { geometry: draftGeometry });
      }
      stopDraw();
      onCancel();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to save field boundary.');
    } finally {
      setIsSaving(false);
    }
  };

  if (!mode || !isActiveOwner) return null;

  if (hideCard) {
    return (
      <div
        className={ cn('pointer-events-none flex w-0 flex-col', className) }
        data-testid="field-draw-controller"
      />
    );
  }

  return (
    <div
      className={ cn('pointer-events-none flex w-[320px] max-w-[calc(100vw-2rem)] flex-col gap-3', className) }
      data-testid="field-draw-controller"
    >
      <div className="pointer-events-auto glass flex flex-col gap-3 rounded-md p-3">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-pill bg-primary/10 text-primary">
            <Pencil className="size-4" strokeWidth={ 1.75 } />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-[14px] font-semibold tracking-[-0.01em] text-foreground">
              { title }
            </h2>
            <p className={ cn('mt-1 text-[12px] leading-4 text-muted-foreground', error && 'text-destructive') }>
              { hint }
            </p>
          </div>
        </div>

        { mode === 'draw' && (
          <input
            type="text"
            value={ fieldName }
            onChange={ (e) => setFieldName(e.target.value) }
            placeholder="Field name"
            className="w-full rounded-sm border border-border bg-background px-2 py-1 text-[13px] text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-primary"
            data-testid="field-draw-name"
          />
        ) }

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={ () => { stopDraw(); onCancel(); } }>
            <X className="size-4" strokeWidth={ 1.75 } /> Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={ () => void save() }
            disabled={ !draftGeometry || isSaving || (mode === 'edit' && !canEditSelectedPlot) }
            data-testid="field-draw-save"
          >
            <Check className="size-4" strokeWidth={ 1.75 } />
            { isSaving ? 'Saving…' : 'Save' }
          </Button>
        </div>
      </div>
    </div>
  );
}
