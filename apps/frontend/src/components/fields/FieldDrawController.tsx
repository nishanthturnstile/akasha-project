import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Check, Pencil, X } from 'lucide-react';
import type { TerraDraw, GeoJSONStoreGeometries } from 'terra-draw';
import { Button } from '@/components/ui/button';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import { MAP_UI_COLORS } from '@/map/colors';
import type { Plot, PlotGeometry, PlotUpdatePayload } from '@/types/api';
import { deriveCircleFromRing, sanitizeRingPrecision } from '@/components/fields/circleGeometry';

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
  cutMode?: boolean;
  onCutLineComplete?: (lineCoords: [number, number][]) => void;
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
  // Rounds excessive-precision coordinates that may already be sitting in the
  // database (e.g. a circle saved before circleGeometry.ts started rounding its
  // output) -- otherwise TerraDraw's own validateFeature silently rejects the
  // feature and editing never becomes available for that field.
  const geometry = plot.geometry.type === 'Polygon'
    ? { type: 'Polygon' as const, coordinates: [sanitizeRingPrecision(plot.geometry.coordinates[0])] }
    : plot.geometry;
  return {
    type: 'Feature',
    id: plot.id,
    geometry: geometry as TerraDrawPolygonFeature['geometry'],
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
  cutMode = false,
  onCutLineComplete,
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
  const cutModeRef = useRef(cutMode);
  cutModeRef.current = cutMode;
  const onCutLineCompleteRef = useRef(onCutLineComplete);
  onCutLineCompleteRef.current = onCutLineComplete;
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
        { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode, TerraDrawCircleMode, TerraDrawFreehandLineStringMode },
        { TerraDrawMapLibreGLAdapter },
        { TerraDrawCircleEditMode },
      ] = await Promise.all([
        import('terra-draw'),
        import('terra-draw-maplibre-gl-adapter'),
        import('@/components/fields/circleEditMode'),
      ]);
      const polygonStyles = {
        fillColor: MAP_UI_COLORS.selection,
        fillOpacity: 0.25 as const,
        outlineColor: MAP_UI_COLORS.selectionOutline,
        outlineOpacity: 1 as const,
        outlineWidth: 3 as const,
        outlineDashStyle: [6, 4] as unknown as [number, number],
        closingPointColor: MAP_UI_COLORS.brand,
        closingPointWidth: 8 as const,
        closingPointOutlineColor: MAP_UI_COLORS.white,
        closingPointOutlineWidth: 2 as const,
        coordinatePointColor: MAP_UI_COLORS.selection,
        coordinatePointWidth: 5 as const,
        coordinatePointOutlineColor: MAP_UI_COLORS.white,
        coordinatePointOutlineWidth: 1.5 as const,
      };
      const circleStyles = {
        fillColor: MAP_UI_COLORS.selection,
        fillOpacity: 0.25 as const,
        outlineColor: MAP_UI_COLORS.selectionOutline,
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
          new TerraDrawFreehandLineStringMode({
            styles: {
              lineStringColor: MAP_UI_COLORS.destructive,
              lineStringWidth: 3 as const,
              lineStringOpacity: 1 as const,
              lineStringDash: [4, 4] as [number, number],
              closingPointColor: MAP_UI_COLORS.destructive,
              closingPointWidth: 6 as const,
              closingPointOutlineColor: MAP_UI_COLORS.white,
              closingPointOutlineWidth: 2 as const,
              closingPointOpacity: 1 as const,
              closingPointOutlineOpacity: 1 as const,
            },
          }),
          new TerraDrawCircleEditMode({
            styles: {
              handleColor: MAP_UI_COLORS.handle,
              handleOutlineColor: MAP_UI_COLORS.white,
              handleWidth: 6 as const,
            },
            pointerDistance: 20,
          }),
          enableVertexDragRef.current
            ? new TerraDrawSelectMode({
                // TerraDraw's default (40px) hit-tolerance around every vertex
                // and every edge midpoint covers most of a modest-sized field's
                // interior, making it hard to reliably grab the body for a
                // whole-shape drag without accidentally moving/inserting a
                // vertex instead. Tightening it leaves more of the interior
                // free for whole-feature dragging while vertices/midpoints are
                // still easily grabbable when clicked precisely.
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
              })
            : new TerraDrawSelectMode(),
        ],
      });
      draw.on('finish', (id) => {
        if (modeRef.current !== 'draw') return;
        // TerraDraw's SelectMode re-emits 'finish' as part of its own select/edit
        // lifecycle (e.g. right after a programmatic selectFeature() call), even
        // though no new shape was drawn. Only treat 'finish' as "a new polygon
        // was completed" when we were actually in a drawing mode when it fired --
        // otherwise the code below would reselect the feature, which re-fires
        // 'finish', creating a new pending field and looping indefinitely.
        const terraDrawMode = draw.getMode();
        if (terraDrawMode !== 'polygon' && terraDrawMode !== 'circle' && terraDrawMode !== 'freehand-linestring') {
          return;
        }
        let feature;
        try {
          feature = draw.getSnapshotFeature(id);
        } catch {
          return;
        }
        if (cutModeRef.current && feature?.geometry.type === 'LineString') {
          console.log('[finish handler] CUT LINE detected. cutModeRef.current:', cutModeRef.current, 'feature type:', feature.geometry.type);
          const coords = (feature.geometry as { type: 'LineString'; coordinates: [number, number][] }).coordinates;
          console.log('[finish handler] line coords count:', coords.length, 'first:', coords[0], 'last:', coords[coords.length - 1]);
          onCutLineCompleteRef.current?.(coords);
          console.log('[finish handler] after onCutLineComplete, removing cut line');
          try { draw.removeFeatures([id]); } catch (e) { console.error('[finish handler] removeFeatures failed:', e); }
          try { draw.setMode(drawModeRef.current === 'circle' ? 'circle' : 'polygon'); } catch (e) { console.error('[finish handler] setMode restore failed:', e); }
          console.log('[finish handler] mode restored, returning');
          if (map && typeof map.getCanvas === 'function') {
            map.getCanvas().style.cursor = 'crosshair';
          }
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
            const isCircle = terraDrawMode === 'circle';
            try { draw.removeFeatures([id]); } catch { /* ignore */ }
            const results = draw.addFeatures([
              {
                type: 'Feature',
                geometry: geometry as GeoJSONStoreGeometries,
                // Always 'polygon', even for circles: TerraDrawCircleEditMode targets
                // features by id, not by this tag, and 'polygon' reliably resolves to
                // TerraDrawPolygonMode's styling regardless of which mode is active.
                properties: { mode: 'polygon' },
              },
            ]);
            const newId = results[0]?.id ?? id;
            try {
              if (isCircle) {
                draw.setMode('circle-edit');
                draw.updateModeOptions('circle-edit', { targetFeatureId: newId });
              } else {
                draw.setMode('select');
                draw.selectFeature(newId);
              }
            } catch { /* ignore */ }
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
          if (terraDrawMode === 'circle' && enableVertexDragRef.current) {
            draw.setMode('circle-edit');
            draw.updateModeOptions('circle-edit', { targetFeatureId: id });
          } else {
            draw.setMode('select');
            draw.selectFeature(id);
          }
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
        const circleParams = deriveCircleFromRing(selectedPlot.geometry.coordinates[0]);
        if (circleParams) {
          draw.setMode('circle-edit');
          draw.updateModeOptions('circle-edit', { targetFeatureId: selectedPlot.id });
        } else {
          draw.setMode('select');
          draw.selectFeature(selectedPlot.id);
        }
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

  // Switch to freehand linestring mode for cutting
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw || !startedRef.current) return;
    if (modeRef.current !== 'draw') return;
    if (cutMode) {
      const currentMode = draw.getMode();
      // TerraDraw can't switch directly from 'select' (or our custom 'circle-edit', which
      // is also a select-like editing mode) to 'freehand-linestring' -- hop through
      // 'polygon' first. Skipping this hop for 'circle-edit' would leave it stuck active
      // (with its 4 handles still on screen) since the mode switch below silently no-ops
      // via the catch.
      if (currentMode === 'select' || currentMode === 'circle-edit') {
        draw.setMode('polygon');
      }
      try {
        draw.setMode('freehand-linestring');
      } catch {
        return;
      }
      if (map && typeof map.getCanvas === 'function') {
        map.getCanvas().style.cursor = 'crosshair';
      }
    } else if (draw.getMode() === 'freehand-linestring') {
      draw.setMode(drawModeRef.current === 'circle' ? 'circle' : 'polygon');
      if (map && typeof map.getCanvas === 'function') {
        map.getCanvas().style.cursor = 'crosshair';
      }
    }
  }, [cutMode, map]);

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
