import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { BrandLockup } from '@/components/BrandLockup';
import { X } from 'lucide-react';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { MapControls } from '@/components/map/MapControls';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { polygonAreaMeters } from '@/lib/measure';
import { getField } from '@/lib/api';
import { useConfig, useCreateField, useFields, useNextFieldName, useUpdateField } from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';

import type maplibregl from 'maplibre-gl';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import type { GeoJsonPosition, PlotGeometry } from '@/types/api';

function toLngLatRing(ring: GeoJsonPosition[]): [number, number][] {
  return ring.map(([lng, lat]) => [lng, lat]);
}

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const ONBOARDING_FIELD_KEY = 'akasha.onboarding.fieldId';

// Zoom in closer than the AOI overview default so users can draw a field boundary
// straight away without manually zooming.
const ONBOARDING_DRAW_ZOOM = 18;

/**
 * Onboarding field-create screen: full-screen modal with the map and draw controls.
 *
 * Two modes:
 *   - Create (no query param): draws a new field, POST /api/fields
 *   - Edit (?fieldId=xxx): loads existing field, PATCH /api/fields/{fieldId}
 *
 * Stores/updates the single field ID in sessionStorage so Step2 can show it.
 */
export default function OnboardingFieldCreate() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const configQ = useConfig();
  const createFieldMutation = useCreateField();
  const updateFieldMutation = useUpdateField();

  const editingFieldId = searchParams.get('fieldId');

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [fieldName, setFieldName] = useState('');
  const [drawResetKey] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [basemapRuntimeError, setBasemapRuntimeError] = useState<Error | null>(null);
  const [initialised, setInitialised] = useState(false);

  const fieldsQ = useFields();
  const nextNameQ = useNextFieldName();

  // Derive the suggested field name — use server-side if available, else compute locally
  const suggestedFieldName = useMemo(() => {
    if (nextNameQ.data?.name) return nextNameQ.data.name;
    let maxNum = 0;
    for (const f of (fieldsQ.data ?? [])) {
      const m = f.name.match(/^Field (\d+)$/);
      if (m) maxNum = Math.max(maxNum, parseInt(m[1]));
    }
    return `Field ${maxNum + 1}`;
  }, [nextNameQ.data, fieldsQ.data]);

  const seasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);

  // Load existing field data when in edit mode
  useEffect(() => {
    if (initialised || !editingFieldId) return;
    let cancelled = false;
    getField(editingFieldId)
      .then((field) => {
        if (cancelled) return;
        setFieldName(field.name);
        if (field.geometry) {
          setDraftGeometry(field.geometry);
        }
        setInitialised(true);
      })
      .catch(() => {
        // fall through — user can draw from scratch
      });
    return () => { cancelled = true; };
  }, [editingFieldId, initialised]);

  const isEditing = !!editingFieldId;
  const isPending = createFieldMutation.isPending || updateFieldMutation.isPending;

  const requestMapTool = useCallback((owner: MapToolOwner): boolean => {
    setActiveMapTool((current) => {
      if (!current || current === owner) {
        return owner;
      }
      return current;
    });
    return true;
  }, []);

  const releaseMapTool = useCallback((owner: MapToolOwner) => {
    setActiveMapTool((current) => (current === owner ? null : current));
  }, []);

  // Clicking the map when no tool is active initiates draw mode.
  useEffect(() => {
    if (!map || fieldMode) return;
    const handleClick = () => {
      requestMapTool('field-draw');
      setFieldMode('draw');
    };
    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
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
        <div className="glass-card p-4">Loading map…</div>
      </div>
    );
  }

  if (configQ.isError || !configQ.data) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass-card p-4">Unable to load map configuration.</div>
      </div>
    );
  }

  if (basemapResolution.basemapError instanceof BasemapConfigurationError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass-card p-4">{ basemapResolution.basemapError.message }</div>
      </div>
    );
  }

  const handleClose = () => navigate('/onboarding/step2');

  const saveField = async () => {
    setSaveError(null);
    if (!draftGeometry) {
      setSaveError('Please draw a field boundary first');
      return;
    }
    if (!seasonId) {
      setSaveError('No season found. Please go back and create a season first.');
      return;
    }
    try {
      const polygon = draftGeometry.type === 'Polygon' ? draftGeometry : null;
      if (!polygon) {
        setSaveError('Field must be a single polygon.');
        return;
      }
      const areaMeters = polygonAreaMeters(toLngLatRing(polygon.coordinates[0] ?? []));
      const payload = {
        name: fieldName.trim() || suggestedFieldName,
        geometry: {
          type: 'Polygon' as const,
          coordinates: polygon.coordinates,
        },
        areaHa: areaMeters / 10000,
        seasonIds: [seasonId],
      };

      if (isEditing) {
        await updateFieldMutation.mutateAsync({
          fieldId: editingFieldId,
          payload,
        });
        sessionStorage.setItem(ONBOARDING_FIELD_KEY, editingFieldId);
      } else {
        const created = await createFieldMutation.mutateAsync(payload);
        sessionStorage.setItem(ONBOARDING_FIELD_KEY, created.id);
      }
      navigate('/onboarding/step2');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to save field';
      setSaveError(message);
    }
  };

  return (
    <div className="fixed inset-0 z-modal flex flex-col bg-transparent">
      {/* Top bar */ }
      <div className="glass-card relative z-toolbar flex items-center justify-center rounded-none px-4 py-3">
        <BrandLockup className="absolute left-4 hidden sm:inline-flex" variant="compact" />
        <h2 className="font-display text-lg font-bold">{ isEditing ? 'Edit field' : 'Add field' }</h2>
        <button aria-label="Close" onClick={ handleClose } className="absolute right-4 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="size-5" strokeWidth={ 1.75 } />
        </button>
      </div>

      {/* Map area */ }
      <div className="relative flex-1">
        <MapLayerManager
          basemap={ basemapResolution.basemapConfig! }
          center={ configQ.data.aoi.center }
          zoom={ Math.max(configQ.data.aoi.zoom, ONBOARDING_DRAW_ZOOM) }
          scene={ null }
          opacity={ 1 }
          visible={ true }
          onBasemapError={ setBasemapRuntimeError }
          onMapReady={ setMap }
        />

        { basemapRuntimeError && (
          <div
            className="absolute left-1/2 top-20 z-popover w-max max-w-[90vw] -translate-x-1/2 rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground shadow-e2"
            data-testid="basemap-runtime-error"
          >
            Unable to load Esri basemap: { basemapRuntimeError.message }
          </div>
        ) }

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

        {/* Left controls */ }
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
                // Request ownership of the field-draw tool before entering draw mode
                requestMapTool('field-draw');
                setFieldMode((current) => (current === 'draw' ? null : 'draw'));
              } }
              onEditSelectedField={ () => setFieldMode((current) => (current === 'edit' ? null : 'edit')) }
              onImportGeoJSON={ () => undefined }
              onExportGeoJSON={ () => undefined }
            />
          </div>
        </div>

        {/* Field name card when geometry is ready */ }
        { draftGeometry && (
          <div className="absolute left-1/2 top-24 z-40 w-full max-w-72 -translate-x-1/2 px-4">
            <div className="glass-card space-y-3 p-4">
              <input
                placeholder="Field name"
                value={ fieldName || (!editingFieldId && suggestedFieldName) || '' }
                onChange={ (e) => setFieldName(e.target.value) }
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={ handleClose }>Cancel</Button>
                <Button variant="primary" onClick={ saveField } disabled={ !draftGeometry || isPending }>
                  { isPending ? 'Saving…' : isEditing ? 'Update' : 'Save' }
                </Button>
              </div>
            </div>
          </div>
        ) }

        {/* Bottom center hint */ }
        <div className="absolute left-1/2 bottom-24 z-40 -translate-x-1/2">
          <div className="glass-card rounded-full px-4 py-2 text-sm">{ isEditing ? 'Edit your field boundary on the map' : 'Put a dot on the map to start drawing' }</div>
        </div>

        {/* Error toast */ }
        { saveError && (
          <div className="absolute left-1/2 bottom-20 z-popover w-max max-w-[90vw] -translate-x-1/2 rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground shadow-e2">
            { saveError }
          </div>
        ) }
      </div>
    </div>
  );
}
