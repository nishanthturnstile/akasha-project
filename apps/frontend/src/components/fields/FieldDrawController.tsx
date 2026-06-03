import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Check, Pencil, Sprout, X } from 'lucide-react';
import type { TerraDraw } from 'terra-draw';
import { Button } from '@/components/ui/button';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import type { Plot, PlotCreatePayload, PlotGeometry, PlotUpdatePayload } from '@/types/api';

export type FieldDrawMode = 'draw' | 'edit' | null;

interface FieldDrawControllerProps {
  activeTool: ActiveMapTool;
  className?: string;
  map: maplibregl.Map | null;
  mode: FieldDrawMode;
  onCancel: () => void;
  onCreateField: (payload: PlotCreatePayload) => Promise<Plot | void> | Plot | void;
  onReleaseTool: (owner: MapToolOwner) => void;
  onRequestTool: (owner: MapToolOwner) => boolean;
  onUpdateField: (plotId: string, payload: PlotUpdatePayload) => Promise<Plot | void> | Plot | void;
  selectedPlot: Plot | null;
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
}: FieldDrawControllerProps) {
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [draftName, setDraftName] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const drawRef = useRef<TerraDraw | null>(null);
  const startedRef = useRef(false);
  const modeRef = useRef<FieldDrawMode>(mode);
  modeRef.current = mode;
  const selectedPlotRef = useRef<Plot | null>(selectedPlot);
  selectedPlotRef.current = selectedPlot;

  const owner = mode === 'draw' ? 'field-draw' : mode === 'edit' ? 'field-edit' : null;
  const isActiveOwner = owner != null && activeTool === owner;
  const canEditSelectedPlot = selectedPlot ? isPolygonGeometry(selectedPlot.geometry) : false;

  const stopDraw = useCallback(() => {
    const draw = drawRef.current;
    if (draw && startedRef.current) {
      draw.clear();
      draw.stop();
      startedRef.current = false;
    }
    setDraftGeometry(null);
    setDraftName('');
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
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [new TerraDrawPolygonMode(), new TerraDrawSelectMode()],
      });
      draw.on('finish', (id) => {
        if (modeRef.current !== 'draw') return;
        const feature = draw.getSnapshotFeature(id);
        if (feature?.geometry.type !== 'Polygon') return;
        setDraftGeometry(feature.geometry as PlotGeometry);
        setDraftName((current) => current || `Field ${new Date().toISOString().slice(0, 10)}`);
        draw.setMode('select');
        draw.selectFeature(id);
      });
      draw.on('change', () => {
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
      draw.clear();
      setDraftGeometry(null);
      setDraftName('');
      setError(null);

      if (mode === 'draw') {
        draw.setMode('polygon');
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
      draw.setMode('select');
      draw.selectFeature(selectedPlot.id);
      setDraftGeometry(selectedPlot.geometry);
    })();

    return () => {
      cancelled = true;
    };
  }, [activeTool, ensureDraw, map, mode, onCancel, onRequestTool, owner, selectedPlot, stopDraw]);

  useEffect(() => {
    return () => stopDraw();
  }, [stopDraw]);

  const title = mode === 'draw' ? 'Save new field' : 'Save boundary edit';
  const hint = useMemo(() => {
    if (error) return error;
    if (mode === 'draw') {
      return draftGeometry ? 'Name the field and save it to Akasha.' : 'Click vertices on the map, then double-click to close the field.';
    }
    return draftGeometry ? 'Adjust the selected field, then save the boundary.' : 'Select and adjust the field boundary on the map.';
  }, [draftGeometry, error, mode]);

  const save = async () => {
    if (!draftGeometry || !mode) return;
    setIsSaving(true);
    setError(null);
    try {
      if (mode === 'draw') {
        const name = draftName.trim();
        if (!name) {
          setError('Field name is required.');
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
      className={ cn('glass flex w-[320px] max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-md p-3', className) }
      data-testid="field-draw-controller"
    >
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-pill bg-primary/10 text-primary">
          { mode === 'draw' ? <Sprout className="size-4" strokeWidth={ 1.75 } /> : <Pencil className="size-4" strokeWidth={ 1.75 } /> }
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

      { mode === 'draw' && draftGeometry && (
        <label className="flex flex-col gap-1.5 text-[12px] font-medium text-muted-foreground">
          Field name
          <input
            value={ draftName }
            onChange={ (event) => setDraftName(event.target.value) }
            className="h-9 rounded-md border border-input bg-background/65 px-3 text-[13px] text-foreground shadow-e1 focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
            data-testid="field-draw-name"
          />
        </label>
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
  );
}
