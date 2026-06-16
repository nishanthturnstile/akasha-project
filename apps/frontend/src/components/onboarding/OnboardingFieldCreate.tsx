import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldDrawController, type FieldDrawMode } from '@/components/fields/FieldDrawController';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { MapControls } from '@/components/map/MapControls';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';
import { useConfig, useCreateField } from '@/lib/queries';
import { BasemapConfigurationError, resolveBasemapConfig } from '@/map/basemap';

import type maplibregl from 'maplibre-gl';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import type { PlotGeometry } from '@/types/api';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const ONBOARDING_FIELDS_KEY = 'akasha.onboarding.fieldIds';

/**
 * Onboarding field-create screen: full-screen modal with the map and draw controls.
 * Creates a Field via the Field API linked to the onboarding season.
 */
export default function OnboardingFieldCreate() {
  const navigate = useNavigate();
  const configQ = useConfig();
  const createFieldMutation = useCreateField();

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [fieldMode, setFieldMode] = useState<FieldDrawMode>(null);
  const [activeMapTool, setActiveMapTool] = useState<ActiveMapTool>(null);
  const [draftGeometry, setDraftGeometry] = useState<PlotGeometry | null>(null);
  const [fieldName, setFieldName] = useState('');
  const [drawResetKey] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);

  const seasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);

  const requestMapTool = (owner: MapToolOwner): boolean => {
    if (!activeMapTool || activeMapTool === owner) {
      setActiveMapTool(owner);
      return true;
    }
    return false;
  };

  const releaseMapTool = (owner: MapToolOwner) => {
    setActiveMapTool((current) => (current === owner ? null : current));
  };

  // Clicking the map when no tool is active initiates draw mode.
  useEffect(() => {
    if (!map || fieldMode) return;
    const handleClick = () => setFieldMode('draw');
    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [map, fieldMode]);

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
        <div className="glass p-4">{basemapResolution.basemapError.message}</div>
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
      const created = await createFieldMutation.mutateAsync({
        name: fieldName.trim() || 'Field',
        geometry: draftGeometry,
        seasonIds: [seasonId],
      });
      // Persist field ID in sessionStorage so Step2 can show it
      const existing = (() => {
        try {
          const raw = sessionStorage.getItem(ONBOARDING_FIELDS_KEY);
          return raw ? (JSON.parse(raw) as string[]) : [];
        } catch {
          return [];
        }
      })();
      sessionStorage.setItem(ONBOARDING_FIELDS_KEY, JSON.stringify([...existing, created.id]));
      navigate('/onboarding/step2');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to save field';
      setSaveError(message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-transparent">
      {/* Top bar */}
      <div className="glass z-50 flex items-center justify-center px-4 py-3 relative">
        <h2 className="font-display text-lg font-semibold">Add field</h2>
        <button aria-label="Close" onClick={handleClose} className="absolute right-4 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="size-5" strokeWidth={1.75} />
        </button>
      </div>

      {/* Map area */}
      <div className="relative flex-1">
        <MapLayerManager
          basemap={basemapResolution.basemapConfig!}
          center={configQ.data.aoi.center}
          zoom={configQ.data.aoi.zoom}
          scene={null}
          opacity={1}
          visible={true}
          onBasemapError={() => undefined}
          onMapReady={setMap}
        />

        <FieldBoundaryLayer map={map} plot={null} />

        <FieldDrawController
          activeTool={activeMapTool}
          map={map}
          mode={fieldMode}
          onCancel={() => setFieldMode(null)}
          onUpdateField={() => Promise.resolve()}
          onRequestTool={requestMapTool}
          onReleaseTool={releaseMapTool}
          selectedPlot={null}
          drawResetKey={drawResetKey}
          onPolygonComplete={(geometry) => setDraftGeometry(geometry)}
        />

        {/* Left controls */}
        <div className="absolute left-4 top-20 z-toolbar flex flex-col items-start gap-3">
          <MapControls
            map={map}
            hasSelectedField={false}
            legendOpen={false}
            onFindSelectedField={undefined}
            onLegendOpenChange={undefined}
          />
          <div className="mt-2">
            <PlotToolbar
              activeAction={fieldMode === 'draw' ? 'draw' : null}
              isMapAvailable={Boolean(map)}
              onDrawField={() => {
                // Request ownership of the field-draw tool before entering draw mode
                requestMapTool('field-draw');
                setFieldMode((current) => (current === 'draw' ? null : 'draw'));
              }}
              onEditSelectedField={() => setFieldMode((current) => (current === 'edit' ? null : 'edit'))}
              onImportGeoJSON={() => undefined}
              onExportGeoJSON={() => undefined}
            />
          </div>
        </div>

        {/* Field name input when geometry is ready */}
        {draftGeometry && (
          <div className="absolute left-1/2 top-24 z-40 -translate-x-1/2 w-72">
            <input
              placeholder="Field name"
              value={fieldName}
              onChange={(e) => setFieldName(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 shadow-lg"
              autoFocus
            />
          </div>
        )}

        {/* Bottom center hint */}
        <div className="absolute left-1/2 bottom-24 z-40 -translate-x-1/2">
          <div className="glass rounded-full px-4 py-2 text-sm">Put a dot on the map to start drawing</div>
        </div>

        {/* Error toast */}
        {saveError && (
          <div className="absolute left-1/2 bottom-20 z-50 w-max max-w-[90vw] -translate-x-1/2 rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground shadow-lg">
            {saveError}
          </div>
        )}

        {/* Bottom action bar */}
        <div className="glass absolute inset-x-0 bottom-0 z-50 flex items-center justify-end gap-2 px-4 py-3">
          <Button variant="ghost" onClick={handleClose}>Cancel</Button>
          <Button variant="primary" onClick={saveField} disabled={!draftGeometry || createFieldMutation.isPending}>
            {createFieldMutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  );
}
