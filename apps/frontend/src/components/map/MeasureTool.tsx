import { useCallback, useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Ruler, Spline, Pentagon, X } from 'lucide-react';
import type { TerraDraw } from 'terra-draw';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import {
    formatArea,
    formatDistance,
    lineLengthMeters,
    polygonAreaMeters,
} from '@/lib/measure';

interface MeasureToolProps {
    activeTool?: ActiveMapTool;
    map: maplibregl.Map | null;
    onReleaseTool?: (owner: MapToolOwner) => void;
    onRequestTool?: (owner: MapToolOwner) => boolean;
}

type MeasureMode = 'distance' | 'area';

interface MeasureResult {
    mode: MeasureMode;
    value: number;
}

/** Terra Draw's mode name for each measurement kind. */
const MODE_NAME: Record<MeasureMode, string> = {
    distance: 'linestring',
    area: 'polygon',
};

/**
 * On-map distance/area measurement, powered by Terra Draw (the project's
 * sanctioned draw library — see CLAUDE.md). The library is dynamically imported
 * on first activation so it stays out of the initial bundle. A single active
 * measurement is kept; drawing geometry updates the readout live.
 */
export function MeasureTool({
    activeTool = null,
    map,
    onReleaseTool,
    onRequestTool,
}: MeasureToolProps) {
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState<MeasureMode | null>(null);
    const [result, setResult] = useState<MeasureResult | null>(null);

    const drawRef = useRef<TerraDraw | null>(null);
    const startedRef = useRef(false);
    const modeRef = useRef<MeasureMode | null>(null);
    modeRef.current = mode;

    const recompute = useCallback(() => {
        const draw = drawRef.current;
        const activeMode = modeRef.current;
        if (!draw || !activeMode) return;
        const features = draw
            .getSnapshot()
            .filter((f) => f.properties?.mode === MODE_NAME[activeMode]);
        const feature = features[features.length - 1];
        if (!feature) {
            setResult(null);
            return;
        }
        if (activeMode === 'distance' && feature.geometry.type === 'LineString') {
            const coords = feature.geometry.coordinates as [number, number][];
            setResult({ mode: 'distance', value: lineLengthMeters(coords) });
        } else if (activeMode === 'area' && feature.geometry.type === 'Polygon') {
            const ring = feature.geometry.coordinates[0] as [number, number][];
            setResult({ mode: 'area', value: polygonAreaMeters(ring) });
        }
    }, []);

    const ensureDraw = useCallback(async (): Promise<TerraDraw | null> => {
        if (!map) return null;
        if (!drawRef.current) {
            const [{ TerraDraw, TerraDrawLineStringMode, TerraDrawPolygonMode }, { TerraDrawMapLibreGLAdapter }] =
                await Promise.all([import('terra-draw'), import('terra-draw-maplibre-gl-adapter')]);
            const draw = new TerraDraw({
                adapter: new TerraDrawMapLibreGLAdapter({ map }),
                modes: [new TerraDrawLineStringMode(), new TerraDrawPolygonMode()],
            });
            draw.on('change', recompute);
            draw.on('finish', recompute);
            drawRef.current = draw;
        }
        if (!startedRef.current) {
            drawRef.current.start();
            startedRef.current = true;
        }
        return drawRef.current;
    }, [map, recompute]);

    const activateMode = useCallback(
        async (next: MeasureMode) => {
            const draw = await ensureDraw();
            if (!draw) return;
            draw.clear();
            setResult(null);
            draw.setMode(MODE_NAME[next]);
            setMode(next);
        },
        [ensureDraw],
    );

    const clearMeasurement = useCallback(() => {
        drawRef.current?.clear();
        setResult(null);
    }, []);

    const stopMeasuring = useCallback(() => {
        const draw = drawRef.current;
        if (draw && startedRef.current) {
            draw.clear();
            draw.stop();
            startedRef.current = false;
        }
        setMode(null);
        setResult(null);
        onReleaseTool?.('measure');
    }, [onReleaseTool]);

    const toggleOpen = useCallback(() => {
        setOpen((prev) => {
            const nextOpen = !prev;
            if (nextOpen && onRequestTool && !onRequestTool('measure')) return prev;
            if (!nextOpen) stopMeasuring();
            return nextOpen;
        });
    }, [onRequestTool, stopMeasuring]);

    useEffect(() => {
        if (open && activeTool && activeTool !== 'measure') {
            setOpen(false);
            stopMeasuring();
        }
    }, [activeTool, open, stopMeasuring]);

    // Tear down Terra Draw on unmount.
    useEffect(() => {
        return () => {
            const draw = drawRef.current;
            if (draw && startedRef.current) {
                draw.stop();
                startedRef.current = false;
            }
            drawRef.current = null;
        };
    }, []);

    const ButtonBase = (
        label: string,
        active: boolean,
        onClick: () => void,
        icon: React.ReactNode,
        testId: string,
    ) => (
        <button
            type="button"
            aria-label={ label }
            aria-pressed={ active }
            title={ label }
            data-testid={ testId }
            onClick={ onClick }
            className={ cn(
                'flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium transition-colors duration-fast ease-standard',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                active
                    ? 'bg-primary/15 text-foreground shadow-e1'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            ) }
        >
            { icon }
            { label }
        </button>
    );

    return (
        <div className="flex flex-col items-end gap-2" data-testid="measure-tool">
            { open && (
                <div className="glass flex flex-col gap-2 rounded-md p-2" data-testid="measure-panel">
                    <div className="flex items-center gap-1.5">
                        { ButtonBase(
                            'Distance',
                            mode === 'distance',
                            () => void activateMode('distance'),
                            <Spline className="size-3.5" strokeWidth={ 1.75 } />,
                            'measure-distance-btn',
                        ) }
                        { ButtonBase(
                            'Area',
                            mode === 'area',
                            () => void activateMode('area'),
                            <Pentagon className="size-3.5" strokeWidth={ 1.75 } />,
                            'measure-area-btn',
                        ) }
                    </div>

                    { result && (
                        <div
                            className="flex items-center justify-between gap-3 rounded-md bg-secondary/60 px-2.5 py-1.5"
                            data-testid="measure-result"
                        >
                            <span className="font-mono text-[13px] tabular-nums text-foreground">
                                { result.mode === 'distance'
                                    ? formatDistance(result.value)
                                    : formatArea(result.value) }
                            </span>
                            <button
                                type="button"
                                onClick={ clearMeasurement }
                                data-testid="measure-clear-btn"
                                className="rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                aria-label="Clear measurement"
                                title="Clear measurement"
                            >
                                <X className="size-3.5" strokeWidth={ 2 } />
                            </button>
                        </div>
                    ) }

                    { mode && !result && (
                        <p className="px-0.5 text-[11px] leading-4 text-muted-foreground" data-testid="measure-hint">
                            { mode === 'distance'
                                ? 'Click to add points · double-click to finish.'
                                : 'Click to add vertices · double-click to close.' }
                        </p>
                    ) }
                </div>
            ) }

            <button
                type="button"
                aria-label={ open ? 'Close measurement tool' : 'Measure distance or area' }
                aria-expanded={ open }
                title="Measure"
                data-testid="measure-toggle"
                onClick={ toggleOpen }
                className={ cn(
                    'glass flex size-9 items-center justify-center rounded-md text-foreground/80 transition-colors duration-fast ease-standard',
                    'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    open && 'bg-primary/15 text-foreground',
                ) }
            >
                <Ruler className="size-5" strokeWidth={ 1.75 } />
            </button>
        </div>
    );
}
