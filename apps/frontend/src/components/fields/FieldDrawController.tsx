import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Check, Pencil, X } from 'lucide-react';
import type { TerraDraw } from 'terra-draw';
import { Button } from '@/components/ui/button';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import type { Plot, PlotGeometry, PlotUpdatePayload } from '@/types/api';

export type FieldDrawMode = 'draw' | 'edit' | null;

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
  onPolygonComplete?: (geometry: PlotGeometry | null) => void;
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
        { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode },
        { TerraDrawMapLibreGLAdapter },
      ] = await Promise.all([import('terra-draw'), import('terra-draw-maplibre-gl-adapter')]);
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map, prefixId: 'field-draw' }),
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
          new TerraDrawSelectMode(),
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
        onPolygonCompleteRef.current?.(geometry);
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
      draw.on('change', () => {
        if (modeRef.current === 'draw') {
          const snapshot = draw.getSnapshot();
          const drawing = snapshot.find((f) => f.geometry.type === 'Polygon');
          const ring = drawing?.geometry?.type === 'Polygon'
            ? (drawing.geometry as PlotGeometry).coordinates[0]
            : undefined;
          const count = ring?.length ?? 0;
          if (count !== vertexCountRef.current) {
            vertexCountRef.current = count;
            if (map) {
              const canvas = map.getCanvas();
              canvas.style.cursor = count >= 4 ? 'grab' : 'crosshair';
            }
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
      try {
        draw.clear();
      } catch {
        // Ignore clear errors when Terra Draw is temporarily disabled.
      }
      setDraftGeometry(null);
      setError(null);

      if (mode === 'draw') {
        try {
          draw.setMode('polygon');
        } catch {
          // Ignore mode-switch errors.
        }
        if (map && typeof map.getCanvas === 'function') {
          map.getCanvas().style.cursor = 'crosshair';
        }
        return;
      }

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
    // Soft-reset: clear the current sketch and return to polygon mode
    // so the user can immediately start a fresh drawing.
    try {
      draw.clear();
    } catch {
      /* ignore */
    }
    try {
      draw.setMode('polygon');
    } catch {
      /* ignore */
    }
    setDraftGeometry(null);
    onPolygonComplete?.(null);
    vertexCountRef.current = 0;
    if (map) map.getCanvas().style.cursor = 'crosshair';
  }, [drawResetKey, map, onPolygonComplete]);

  const title = mode === 'draw' ? 'Save new field' : 'Save boundary edit';
  const hint = useMemo(() => {
    if (error) return error;
    if (mode === 'draw') {
      return draftGeometry ? 'Name the field and save it to Akasha.' : 'Click vertices on the map, then double-click to close the field.';
    }
    return draftGeometry ? 'Adjust the selected field, then save the boundary.' : 'Select and adjust the field boundary on the map.';
  }, [draftGeometry, error, mode]);

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
