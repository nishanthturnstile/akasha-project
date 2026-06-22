import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { MapControls } from '@/components/map/MapControls';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { polygonAreaMeters } from '@/lib/measure';
import { useConfig, useCreateField, useSeasons, queryKeys } from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';

import type maplibregl from 'maplibre-gl';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import type { Field, GeoJsonPosition, PlotGeometry } from '@/types/api';
import CreateSeasonDialog from '@/components/seasons/CreateSeasonDialog';

function toLngLatRing(ring: GeoJsonPosition[]): [number, number][] {
  return ring.map(([lng, lat]) => [lng, lat]);
}

const DRAW_ZOOM = 18;

export default function FieldCreatePage() {
  const navigate = useNavigate();
  const configQ = useConfig();
  const seasonsQ = useSeasons();
  const createFieldMutation = useCreateField();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [fieldName, setFieldName] = useState('');
  const preselectedSeasonId = searchParams.get('seasonId');
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | null>(preselectedSeasonId);
  const [createSeasonOpen, setCreateSeasonOpen] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const drawResetKey = 0;

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

  useEffect(() => {
    if (!map || fieldMode) return;
    const handleClick = () => {
      requestMapTool('field-draw');
      setFieldMode('draw');
    };
    map.on('click', handleClick);
    return () => { map.off('click', handleClick); };
  }, [map, fieldMode, requestMapTool]);

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

  const handleClose = () => navigate('/monitoring/field-analytics');

  const saveField = async () => {
    setSaveError(null);
    if (!draftGeometry) {
      setSaveError('Please draw a field boundary first');
      return;
    }
    if (!selectedSeasonId) {
      setSaveError('Please select a season');
      return;
    }
    try {
      const polygon = draftGeometry.type === 'Polygon' ? draftGeometry : null;
      if (!polygon) {
        setSaveError('Field must be a single polygon.');
        return;
      }
      const areaMeters = polygonAreaMeters(toLngLatRing(polygon.coordinates[0] ?? []));
      const created = await createFieldMutation.mutateAsync({
        name: fieldName.trim() || 'Field',
        geometry: { type: 'Polygon', coordinates: polygon.coordinates },
        areaHa: areaMeters / 10000,
        seasonIds: [selectedSeasonId],
      });
      queryClient.setQueryData<Field[]>(queryKeys.fields, (old) => [...(old ?? []), created]);
      navigate(`/monitoring/field-analytics/field/${created.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to save field';
      setSaveError(message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-transparent">
      <CreateSeasonDialog open={ createSeasonOpen } onOpenChange={ setCreateSeasonOpen } />

      {/* Top bar */}
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

      {/* Season selector bar — hidden when a season is pre-selected from context */}
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

      {/* Map area */}
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

        <FieldBoundaryLayer
          map={ map }
          plot={ null }
          geometry={ draftGeometry }
          featureId="draft-field"
          name="Draft field"
        />

        <FieldDrawController
          activeTool={ activeMapTool }
          map={ map }
          mode={ fieldMode }
          onCancel={ () => setFieldMode(null) }
          onUpdateField={ () => Promise.resolve() }
          onRequestTool={ requestMapTool }
          onReleaseTool={ releaseMapTool }
          selectedPlot={ null }
          drawResetKey={ drawResetKey }
          onPolygonComplete={ (geometry) => setDraftGeometry(geometry) }
        />

        {/* Left controls */}
        <div className="absolute left-4 top-20 z-toolbar flex flex-col items-start gap-3">
          <MapControls
            map={ map }
            hasSelectedField={ false }
            legendOpen={ false }
            onFindSelectedField={ undefined }
            onLegendOpenChange={ undefined }
          />
          <div className="mt-2">
            <PlotToolbar
              activeAction={ fieldMode === 'draw' ? 'draw' : null }
              isMapAvailable={ Boolean(map) }
              onDrawField={ () => {
                requestMapTool('field-draw');
                setFieldMode((current) => (current === 'draw' ? null : 'draw'));
              } }
              onEditSelectedField={ () => undefined }
              onImportGeoJSON={ () => undefined }
              onExportGeoJSON={ () => undefined }
            />
          </div>
        </div>

        {/* Field name card when geometry is ready */}
        { draftGeometry && (
          <div className="absolute left-1/2 top-24 z-40 -translate-x-1/2 w-72">
            <div className="rounded-lg border border-border bg-card p-4 shadow-lg space-y-3">
              <input
                placeholder="Field name"
                value={ fieldName }
                onChange={ (e) => setFieldName(e.target.value) }
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={ handleClose }>Cancel</Button>
                <Button
                  variant="primary"
                  onClick={ saveField }
                  disabled={ !draftGeometry || !selectedSeasonId || createFieldMutation.isPending }
                >
                  { createFieldMutation.isPending ? 'Saving…' : 'Save' }
                </Button>
              </div>
            </div>
          </div>
        ) }

        {/* Bottom center hint */}
        { !draftGeometry && (
          <div className="absolute left-1/2 bottom-24 z-40 -translate-x-1/2">
            <div className="glass rounded-full px-4 py-2 text-sm">Put a dot on the map to start drawing</div>
          </div>
        ) }

        {/* Error toast */}
        { saveError && (
          <div className="absolute left-1/2 bottom-20 z-50 w-max max-w-[90vw] -translate-x-1/2 rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground shadow-lg">
            { saveError }
          </div>
        ) }
      </div>
    </div>
  );
}
