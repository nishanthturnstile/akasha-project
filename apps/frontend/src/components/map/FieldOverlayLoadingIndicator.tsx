import { useCallback, useEffect, useMemo, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Loader2 } from 'lucide-react';
import type { Plot } from '@/types/api';

type LngLat = [number, number];

interface ScreenPoint {
    x: number;
    y: number;
}

export interface FieldOverlayLoadingIndicatorProps {
    loading: boolean;
    map: maplibregl.Map | null;
    plot: Pick<Plot, 'geometry'> | null;
}

function geometryBboxCenter(geometry: Plot['geometry'] | undefined): LngLat | null {
    if (!geometry) return null;
    let west = Infinity;
    let south = Infinity;
    let east = -Infinity;
    let north = -Infinity;

    const visit = (node: unknown): void => {
        if (Array.isArray(node) && typeof node[0] === 'number') {
            const [lng, lat] = node as LngLat;
            west = Math.min(west, lng);
            east = Math.max(east, lng);
            south = Math.min(south, lat);
            north = Math.max(north, lat);
        } else if (Array.isArray(node)) {
            node.forEach(visit);
        }
    };

    visit((geometry as { coordinates?: unknown }).coordinates);
    if (![west, south, east, north].every(Number.isFinite) || west === east || south === north) {
        return null;
    }
    return [(west + east) / 2, (south + north) / 2];
}

function projectCenter(map: maplibregl.Map | null, center: LngLat | null): ScreenPoint | null {
    if (!map || !center) return null;
    const point = map.project(center);
    return { x: point.x, y: point.y };
}

export function FieldOverlayLoadingIndicator({
    loading,
    map,
    plot,
}: FieldOverlayLoadingIndicatorProps) {
    const center = useMemo(() => geometryBboxCenter(plot?.geometry), [plot?.geometry]);
    const [, forceReposition] = useState(0);

    const updatePosition = useCallback(() => {
        forceReposition((current) => current + 1);
    }, []);

    const position = loading ? projectCenter(map, center) : null;

    useEffect(() => {
        if (!loading || !map || !center) {
            return undefined;
        }

        map.on('move', updatePosition);
        map.on('zoom', updatePosition);
        map.on('resize', updatePosition);

        return () => {
            map.off('move', updatePosition);
            map.off('zoom', updatePosition);
            map.off('resize', updatePosition);
        };
    }, [center, loading, map, updatePosition]);

    if (!loading || !position) return null;

    return (
        <div
            role="status"
            aria-live="polite"
            data-testid="field-overlay-loading-indicator"
            className="pointer-events-none absolute z-toolbar -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/35 bg-background/85 px-3 py-2 text-[12px] font-medium text-foreground shadow-e2 backdrop-blur-md"
            style={ { left: position.x, top: position.y } }
        >
            <span className="flex items-center gap-2 whitespace-nowrap">
                <Loader2 className="size-3.5 animate-spin text-primary" strokeWidth={ 1.9 } aria-hidden="true" />
                <span>Calculating index…</span>
            </span>
            <span className="sr-only">Field index overlay is recalculating.</span>
        </div>
    );
}