import { useMemo, useState } from 'react';
import { ApiError } from '@/lib/api';
import {
  useCreateVegetationZoning,
  useExportZoningMap,
  useFieldScenes,
  usePlots,
  useZoningMap,
  useZoningMaps,
} from '@/lib/queries';
import { useMapView } from '@/state/mapViewContext';
import type { FileDownload, ZoningMap, ZoningZone } from '@/types/api';
import { SelectFieldNotice } from '@/components/shell/SelectFieldNotice';

const INDEX_OPTIONS = ['NDVI', 'NDRE', 'NDMI', 'MSAVI', 'RECI'];

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return 'Zoning provider rate limit was reached. Try again shortly.';
    if (error.code === 'FIELD_PROVIDER_NOT_SYNCED') {
      return 'Sync the selected field before creating a vegetation zoning map.';
    }
    return error.message;
  }
  return 'Zoning request could not be completed.';
}

function selectedPlotName(plotId: string | null, plots: { id: string; name: string }[] | undefined) {
  if (!plotId) return 'No field selected';
  return plots?.find((plot) => plot.id === plotId)?.name ?? plotId;
}

function formatNumber(value: number | null | undefined, suffix = '', digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a';
  return `${value.toFixed(digits)}${suffix}`;
}

function downloadFile(file: FileDownload): void {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename;
  link.click();
  URL.revokeObjectURL(url);
}

function zoneSort(a: ZoningZone, b: ZoningZone) {
  return a.zoneId.localeCompare(b.zoneId, undefined, { numeric: true });
}

function ZonePreview({ zoningMap }: { zoningMap: ZoningMap }) {
  if (zoningMap.zones.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
        Zone geometries will appear here when the map is ready.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2 rounded-md border border-border bg-background/50 p-3 md:grid-cols-3">
      { zoningMap.zones.slice().sort(zoneSort).map((zone) => (
        <div
          key={ zone.zoneId }
          className="rounded-md border border-border p-3"
          style={ { borderColor: zone.color } }
        >
          <div className="flex items-center gap-2">
            <span className="size-3 rounded-sm" style={ { backgroundColor: zone.color } } />
            <span className="text-sm font-medium text-foreground">{ zone.zoneId }</span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            { formatNumber(zone.areaHa, ' ha') } / { formatNumber(zone.areaPercent, '%') }
          </p>
        </div>
      )) }
    </div>
  );
}

export default function VraVegetationPage() {
  const { selectedPlotId } = useMapView();
  const plotsQ = usePlots();
  const scenesQ = useFieldScenes(selectedPlotId, 'auto');
  const mapsQ = useZoningMaps(selectedPlotId);
  const createMutation = useCreateVegetationZoning();
  const exportMutation = useExportZoningMap();
  const [indexType, setIndexType] = useState('NDVI');
  const [imageDate, setImageDate] = useState('');
  const [zoneCount, setZoneCount] = useState(3);
  const [minZoneArea, setMinZoneArea] = useState(0.25);
  const [activeMapId, setActiveMapId] = useState<string | null>(null);
  const activeMapQ = useZoningMap(selectedPlotId, activeMapId);

  const sceneDates = useMemo(
    () => scenesQ.data?.scenes.filter((scene) => scene.tileAvailable).map((scene) => scene.acquisitionDate) ?? [],
    [scenesQ.data],
  );
  const selectedDate = imageDate || sceneDates[0] || '';
  const fieldName = selectedPlotName(selectedPlotId, plotsQ.data);
  const activeMap = activeMapQ.data ?? mapsQ.data?.maps.find((item) => item.mapId === activeMapId);
  const latestMap = activeMap ?? mapsQ.data?.maps[0] ?? null;
  const createDisabled = !selectedPlotId || !selectedDate || createMutation.isPending;
  const error = createMutation.error ?? activeMapQ.error ?? mapsQ.error;

  async function handleCreate() {
    if (!selectedPlotId || !selectedDate) return;
    try {
      const created = await createMutation.mutateAsync({
        plotId: selectedPlotId,
        payload: {
          indexType,
          imageDate: selectedDate,
          zoneCount,
          minZoneArea,
          asyncProcessing: true,
        },
      });
      setActiveMapId(created.mapId);
    } catch {
      // TanStack Query keeps the sanitized error for rendering.
    }
  }

  async function handleExport(format: 'geojson' | 'shp') {
    if (!selectedPlotId || !latestMap) return;
    try {
      const file = await exportMutation.mutateAsync({ plotId: selectedPlotId, mapId: latestMap.mapId, format });
      downloadFile(file);
    } catch {
      // TanStack Query keeps the sanitized error for rendering.
    }
  }

  if (!selectedPlotId) {
    return (
      <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="vra-vegetation-page">
        <SelectFieldNotice
          title="VRA Vegetation"
          message="Select a field before creating vegetation zones."
        />
      </main>
    );
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="vra-vegetation-page">
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <section className="rounded-xl border border-border/80 bg-card/90 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">VRA maps</p>
          <h1 className="mt-1 text-2xl font-semibold">Vegetation zoning</h1>
          <p className="mt-1 text-sm text-muted-foreground">Selected field: { fieldName }</p>

          <div className="mt-5 grid gap-3">
            <label className="text-sm text-muted-foreground">
              Image date
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
                value={ selectedDate }
                onChange={ (event) => setImageDate(event.target.value) }
              >
                { sceneDates.length === 0 && <option value="">No field scenes available</option> }
                { sceneDates.map((date) => <option key={ date } value={ date }>{ date }</option>) }
              </select>
            </label>

            <label className="text-sm text-muted-foreground">
              Index
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
                value={ indexType }
                onChange={ (event) => setIndexType(event.target.value) }
              >
                { INDEX_OPTIONS.map((index) => <option key={ index } value={ index }>{ index }</option>) }
              </select>
            </label>

            <label className="text-sm text-muted-foreground">
              Zone count
              <input
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
                min={ 2 }
                max={ 12 }
                type="number"
                value={ zoneCount }
                onChange={ (event) => setZoneCount(Number(event.target.value)) }
              />
            </label>

            <label className="text-sm text-muted-foreground">
              Minimum zone area (ha)
              <input
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
                min={ 0.01 }
                step={ 0.01 }
                type="number"
                value={ minZoneArea }
                onChange={ (event) => setMinZoneArea(Number(event.target.value)) }
              />
            </label>

            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40"
              disabled={ createDisabled }
              onClick={ () => void handleCreate() }
              type="button"
            >
              { createMutation.isPending ? 'Creating zones...' : 'Create vegetation zones' }
            </button>
          </div>

          { error && (
            <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100" role="status">
              { errorMessage(error) }
            </div>
          ) }
        </section>

        <section className="grid gap-4">
          <article className="rounded-xl border border-border/80 bg-card/90 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Zone map result</h2>
                <p className="text-sm text-muted-foreground">
                  { latestMap ? `Status: ${latestMap.status}` : 'No vegetation zoning map has been created yet.' }
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-40"
                  disabled={ !latestMap || latestMap.status !== 'ready' || exportMutation.isPending }
                  onClick={ () => void handleExport('geojson') }
                  type="button"
                >
                  Export GeoJSON
                </button>
                <button
                  className="rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-40"
                  disabled={ !latestMap || latestMap.status !== 'ready' || exportMutation.isPending }
                  onClick={ () => void handleExport('shp') }
                  type="button"
                >
                  Export SHP
                </button>
              </div>
            </div>
            { activeMapQ.isFetching && latestMap?.status === 'processing' && (
              <p className="mt-3 text-sm text-muted-foreground">Processing map; polling for zones...</p>
            ) }
            { latestMap && <div className="mt-4"><ZonePreview zoningMap={ latestMap } /></div> }
          </article>

          <article className="rounded-xl border border-border/80 bg-card/90 p-4">
            <h2 className="text-lg font-semibold">Zones</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Zone</th>
                    <th className="py-2 pr-4">Area</th>
                    <th className="py-2 pr-4">Percent</th>
                    <th className="py-2 pr-4">Cluster value</th>
                  </tr>
                </thead>
                <tbody>
                  { latestMap?.zones.slice().sort(zoneSort).map((zone) => (
                    <tr key={ zone.zoneId } className="border-t border-border/60">
                      <td className="py-2 pr-4">
                        <span className="mr-2 inline-block size-3 rounded-sm" style={ { backgroundColor: zone.color } } />
                        { zone.zoneId }
                      </td>
                      <td className="py-2 pr-4">{ formatNumber(zone.areaHa, ' ha') }</td>
                      <td className="py-2 pr-4">{ formatNumber(zone.areaPercent, '%') }</td>
                      <td className="py-2 pr-4">{ formatNumber(zone.clusterValue, '', 3) }</td>
                    </tr>
                  )) }
                  { !latestMap?.zones.length && (
                    <tr>
                      <td className="py-3 text-muted-foreground" colSpan={ 4 }>
                        Zone rows will appear when the provider map is ready.
                      </td>
                    </tr>
                  ) }
                </tbody>
              </table>
            </div>
          </article>
        </section>
      </div>
    </main>
  );
}
