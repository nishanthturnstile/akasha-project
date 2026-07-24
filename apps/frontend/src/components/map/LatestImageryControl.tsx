import { useCallback, useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Loader2, Search } from 'lucide-react';
import { searchLatestImagery } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { LatestImageryPolicy, PlotGeometry, SceneCandidate } from '@/types/api';

type ImageryMode = 'default' | 'latest';

interface LatestImageryControlProps {
  map: maplibregl.Map | null;
  policy: LatestImageryPolicy;
  mode: ImageryMode;
  onModeChange: (mode: ImageryMode) => void;
  selected: SceneCandidate | null;
  onSelectedChange: (scene: SceneCandidate | null) => void;
}

function viewportPolygon(map: maplibregl.Map) {
  const bounds = map.getBounds();
  return {
    type: 'Polygon' as const,
    coordinates: [[
      [bounds.getWest(), bounds.getSouth()],
      [bounds.getEast(), bounds.getSouth()],
      [bounds.getEast(), bounds.getNorth()],
      [bounds.getWest(), bounds.getNorth()],
      [bounds.getWest(), bounds.getSouth()],
    ]],
  };
}

function viewportDiagonalMeters(map: maplibregl.Map): number {
  const bounds = map.getBounds();
  const meanLat = ((bounds.getSouth() + bounds.getNorth()) / 2) * Math.PI / 180;
  const dx = (bounds.getEast() - bounds.getWest()) * Math.PI / 180 * 6_371_008.8 * Math.cos(meanLat);
  const dy = (bounds.getNorth() - bounds.getSouth()) * Math.PI / 180 * 6_371_008.8;
  return Math.hypot(dx, dy);
}

function newestFirst(candidates: SceneCandidate[]): SceneCandidate[] {
  return [...candidates].sort((left, right) => (
    right.acquisitionDatetime.localeCompare(left.acquisitionDatetime)
    || right.acquisitionDate.localeCompare(left.acquisitionDate)
  ));
}

export function LatestImageryControl({
  map,
  policy,
  mode,
  onModeChange,
  selected,
  onSelectedChange,
}: LatestImageryControlProps) {
  const [candidates, setCandidates] = useState<SceneCandidate[]>([]);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diagonal, setDiagonal] = useState(Infinity);
  const abortRef = useRef<AbortController | null>(null);
  const searchToken = useRef(0);
  const hasCandidatesRef = useRef(false);
  hasCandidatesRef.current = candidates.length > 0;

  useEffect(() => {
    if (!map) return;
    const moved = () => {
      setDiagonal(viewportDiagonalMeters(map));
      if (hasCandidatesRef.current) setStale(true);
    };
    moved();
    map.on('moveend', moved);
    return () => { map.off('moveend', moved); };
  }, [map]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const search = useCallback(async () => {
    if (!map || diagonal > policy.maxViewportDiagonalMeters) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const token = ++searchToken.current;
    setLoading(true);
    setError(null);
    setStale(false);
    try {
      const result = await searchLatestImagery(
        viewportPolygon(map) as PlotGeometry,
        controller.signal,
      );
      if (token !== searchToken.current) return;
      const ordered = newestFirst(result.candidates);
      setCandidates(ordered);
      const newest = ordered.find((candidate) => candidate.usable) ?? null;
      onSelectedChange(newest);
      if (!newest) setError('No full-coverage imagery is available for this area.');
    } catch (reason) {
      if (controller.signal.aborted) return;
      onSelectedChange(null);
      setCandidates([]);
      setError(reason instanceof Error ? reason.message : 'Unable to search imagery.');
    } finally {
      if (token === searchToken.current) setLoading(false);
    }
  }, [diagonal, map, onSelectedChange, policy.maxViewportDiagonalMeters]);

  const canSearch = policy.entitled && diagonal <= policy.maxViewportDiagonalMeters && !loading;

  return (
    <div className="glass absolute right-4 top-4 z-toolbar w-80 rounded-lg p-3" data-testid="latest-imagery-control">
      <div className="grid grid-cols-2 gap-1 rounded-md bg-background/60 p-1">
        { (['default', 'latest'] as const).map((value) => (
          <button
            key={ value }
            type="button"
            aria-pressed={ mode === value }
            onClick={ () => {
              onModeChange(value);
              if (value === 'default') onSelectedChange(null);
            } }
            className={ cn(
              'rounded px-2 py-1.5 text-xs font-medium',
              mode === value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
            ) }
          >
            { value === 'default' ? 'Default Map' : 'Latest Image' }
          </button>
        )) }
      </div>
      { mode === 'latest' && (
        <div className="mt-3 space-y-2">
          <button
            type="button"
            disabled={ !canSearch }
            onClick={ () => void search() }
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-45"
          >
            { loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" /> }
            Search this area
          </button>
          { diagonal > policy.maxViewportDiagonalMeters && (
            <p className="text-xs text-muted-foreground">Zoom in until the visible area is about 2 km.</p>
          ) }
          { !policy.entitled && (
            <p className="text-xs text-muted-foreground">Latest Image is not available for this account.</p>
          ) }
          { stale && <p className="text-xs text-warning">Map moved. Search again to refresh imagery.</p> }
          { error && (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>{ error }</p>
              <div className="flex gap-3">
                <button type="button" className="text-primary underline" onClick={ () => map?.getCanvas().focus() }>Move map</button>
                <button type="button" className="text-primary underline" disabled={ !canSearch } onClick={ () => void search() }>Search again</button>
                <button type="button" className="text-primary underline" onClick={ () => onModeChange('default') }>Use Default Map</button>
              </div>
            </div>
          ) }
          { candidates.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Latest imagery dates">
              { candidates.map((candidate) => (
                <button
                  key={ candidate.sceneId }
                  type="button"
                  aria-pressed={ selected?.sceneId === candidate.sceneId }
                  disabled={ !candidate.usable }
                  title={ candidate.unavailableReason ?? `${candidate.cloudPercent}% cloud` }
                  onClick={ () => onSelectedChange(candidate) }
                  className={ cn(
                    'shrink-0 rounded border px-2 py-1 text-[11px] tabular-nums',
                    selected?.sceneId === candidate.sceneId && 'border-primary bg-primary/15',
                    !candidate.usable && 'opacity-45',
                  ) }
                >
                  { candidate.acquisitionDate }
                </button>
              )) }
            </div>
          ) }
        </div>
      ) }
    </div>
  );
}
