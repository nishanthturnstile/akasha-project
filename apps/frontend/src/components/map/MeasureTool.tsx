import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type maplibregl from 'maplibre-gl';
import { Ruler, X } from 'lucide-react';
import type { TerraDraw } from 'terra-draw';
import type { ActiveMapTool, MapToolOwner } from '@/components/map/mapToolState';
import { cn } from '@/lib/utils';
import {
    haversineMeters,
    lineLengthMeters,
    polygonAreaMeters,
} from '@/lib/measure';

function resolveCssVar(name: string): string {
    try {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    } catch {
        return '';
    }
}

function ringCentroid(ring: [number, number][]): [number, number] {
    let cx = 0;
    let cy = 0;
    for (const [lng, lat] of ring) {
        cx += lng;
        cy += lat;
    }
    return [cx / ring.length, cy / ring.length];
}

const SEGMENT_SOURCE = 'measure-segment-labels';
const SEGMENT_LAYER = 'measure-segment-label-layer';
const OUTLINE_ID = 'measure-polygon-outline';
const FILL_ID = 'measure-polygon-fill';
const POLYGON_SOURCE = 'measure-result-polygon';
const POLYGON_FILL_LAYER = 'measure-result-fill';
const POLYGON_OUTLINE_LAYER = 'measure-result-outline';

interface MeasureToolProps {
    activeTool?: ActiveMapTool;
    map: maplibregl.Map | null;
    onReleaseTool?: (owner: MapToolOwner) => void;
    onRequestTool?: (owner: MapToolOwner) => boolean;
}

interface MeasureResult {
    area: number;
    distance: number;
    geometry: [number, number][];
}

export function MeasureTool({
    activeTool = null,
    map,
    onReleaseTool,
    onRequestTool,
}: MeasureToolProps) {
    const [open, setOpen] = useState(false);
    const [result, setResult] = useState<MeasureResult | null>(null);
    const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(null);

    const drawRef = useRef<TerraDraw | null>(null);
    const startedRef = useRef(false);
    const centroidRef = useRef<[number, number]>([0, 0]);

    // ---- ensure CSS rules exist ----
    useEffect(() => {
        const styleId = 'measure-cursor-rules';
        if (document.getElementById(styleId)) return;
        const styleEl = document.createElement('style');
        styleEl.id = styleId;
        styleEl.textContent = `
            .measure-crosshair { cursor: crosshair !important; }
            .measure-done { cursor: default !important; }
        `;
        document.head.appendChild(styleEl);
        return () => {
            const el = document.getElementById(styleId);
            if (el) el.remove();
        };
    }, []);

    // ---- cursor class management ----
    const setCursorClass = useCallback(
        (cls: 'measure-crosshair' | 'measure-done' | '') => {
            if (!map) return;
            const canvas = map.getCanvas();
            canvas.classList.remove('measure-crosshair', 'measure-done');
            if (cls) canvas.classList.add(cls);
        },
        [map],
    );

    // ---- custom polygon layer for result ----
    const addResultPolygon = useCallback(
        (ring: [number, number][]) => {
            if (!map) return;
            removeResultPolygon();
            try {
                map.addSource(POLYGON_SOURCE, {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        geometry: {
                            type: 'Polygon',
                            coordinates: [ring],
                        },
                        properties: {},
                    },
                });
                const mc = resolveCssVar('--measure-color');
                map.addLayer({
                    id: POLYGON_FILL_LAYER,
                    type: 'fill',
                    source: POLYGON_SOURCE,
                    paint: {
                        'fill-color': mc,
                        'fill-opacity': 0.12,
                    },
                });
                map.addLayer({
                    id: POLYGON_OUTLINE_LAYER,
                    type: 'line',
                    source: POLYGON_SOURCE,
                    paint: {
                        'line-color': mc,
                        'line-width': 2,
                        'line-dasharray': [3, 3],
                    },
                });
            } catch {
                /* ignore */
            }
        },
        [map],
    );

    const removeResultPolygon = useCallback(() => {
        if (!map) return;
        try {
            if (map.getLayer(POLYGON_OUTLINE_LAYER))
                map.removeLayer(POLYGON_OUTLINE_LAYER);
            if (map.getLayer(POLYGON_FILL_LAYER))
                map.removeLayer(POLYGON_FILL_LAYER);
            if (map.getSource(POLYGON_SOURCE))
                map.removeSource(POLYGON_SOURCE);
        } catch {
            /* ignore */
        }
    }, [map]);

    const removeSegmentLabels = useCallback(() => {
        if (!map) return;
        try {
            if (map.getLayer(SEGMENT_LAYER)) map.removeLayer(SEGMENT_LAYER);
            if (map.getSource(SEGMENT_SOURCE)) map.removeSource(SEGMENT_SOURCE);
        } catch {
            /* ignore */
        }
    }, [map]);

    const updateSegmentLabels = useCallback(() => {
        if (!map) return;
        const draw = drawRef.current;
        if (!draw) return;
        const features = draw
            .getSnapshot()
            .filter((f) => f.properties?.mode === 'polygon');
        const feature = features[features.length - 1];
        if (!feature || feature.geometry.type !== 'Polygon') {
            removeSegmentLabels();
            return;
        }

        const coords = feature.geometry.coordinates[0] as [number, number][];
        if (coords.length < 2) {
            removeSegmentLabels();
            return;
        }

        const isDrawing = feature.properties?.currentlyDrawing === true;
        const endIndex =
            isDrawing && coords.length >= 3 ? coords.length - 1 : coords.length;

        const segments: GeoJSON.Feature<GeoJSON.Point>[] = [];
        for (let i = 1; i < endIndex; i++) {
            const prev = coords[i - 1] as [number, number];
            const curr = coords[i] as [number, number];
            segments.push({
                type: 'Feature',
                geometry: {
                    type: 'Point',
                    coordinates: [
                        (prev[0] + curr[0]) / 2,
                        (prev[1] + curr[1]) / 2,
                    ],
                },
                properties: {
                    label: `${(haversineMeters(prev, curr) / 1000).toFixed(2)} km`,
                },
            });
        }

        try {
            if (map.getSource(SEGMENT_SOURCE)) {
                (
                    map.getSource(SEGMENT_SOURCE) as maplibregl.GeoJSONSource
                ).setData({
                    type: 'FeatureCollection' as const,
                    features: segments,
                });
            } else {
                map.addSource(SEGMENT_SOURCE, {
                    type: 'geojson',
                    data: {
                        type: 'FeatureCollection' as const,
                        features: segments,
                    },
                });
                map.addLayer({
                    id: SEGMENT_LAYER,
                    type: 'symbol',
                    source: SEGMENT_SOURCE,
                    layout: {
                        'text-field': ['get', 'label'],
                        'text-size': 11,
                        'text-offset': [0, -1.5],
                    },
                    paint: {
                        'text-color': resolveCssVar('--measure-label-text'),
                        'text-halo-color': resolveCssVar('--measure-label-halo'),
                        'text-halo-width': 2,
                    },
                });
            }
        } catch {
            /* layers may not be ready yet */
        }
    }, [map, removeSegmentLabels]);

    const applyPolygonStyle = useCallback(
        (finished: boolean) => {
            if (!map) return;
            try {
                if (map.getLayer(OUTLINE_ID)) {
                    map.setPaintProperty(
                        OUTLINE_ID,
                        'line-dasharray',
                        [3, 3],
                    );
                    map.setPaintProperty(
                        OUTLINE_ID,
                        'line-color',
                        resolveCssVar('--measure-color'),
                    );
                    map.setPaintProperty(
                        OUTLINE_ID,
                        'line-width',
                        2,
                    );
                }
                if (map.getLayer(FILL_ID)) {
                    map.setPaintProperty(FILL_ID, 'fill-color', resolveCssVar('--measure-color'));
                    map.setPaintProperty(FILL_ID, 'fill-opacity', finished ? 0.12 : 0.06);
                }
            } catch {
                /* layers may not be ready */
            }
        },
        [map],
    );

    // ---- Terra Draw interaction refs (defined after callbacks to satisfy hoisting) ----
    const handleDrawChangeRef = useRef<() => void>(() => {});
    const handleDrawFinishRef = useRef<() => void>(() => {});

    useEffect(() => {
        handleDrawChangeRef.current = () => {
            updateSegmentLabels();
            applyPolygonStyle(false);
        };
    }, [updateSegmentLabels, applyPolygonStyle]);

    useEffect(() => {
        handleDrawFinishRef.current = () => {
            const draw = drawRef.current;
            if (!draw) return;
            const features = draw
                .getSnapshot()
                .filter((f) => f.properties?.mode === 'polygon');
            const feature = features[features.length - 1];
            if (feature?.geometry.type !== 'Polygon') return;

            const ring = feature.geometry.coordinates[0] as [number, number][];
            const distance = lineLengthMeters(ring);
            const area = polygonAreaMeters(ring);

            draw.stop();
            startedRef.current = false;

            centroidRef.current = ringCentroid(ring);
            setResult({ area, distance, geometry: ring });
            setCursorClass('measure-done');

            addResultPolygon(ring);
        };
    }, [setCursorClass, addResultPolygon]);

    const repositionPopup = useCallback(() => {
        if (!map || !result) return;
        const [lng, lat] = centroidRef.current;
        const p = map.project([lng, lat]);
        setPopupPos({ x: p.x, y: p.y });
    }, [map, result]);

    useEffect(() => {
        repositionPopup();
    }, [result, repositionPopup]);

    useEffect(() => {
        if (!map || !result) return;
        map.on('move', repositionPopup);
        return () => { map.off('move', repositionPopup); };
    }, [map, result, repositionPopup]);

    const ensureDraw = useCallback(async () => {
        if (!map) return null;
        if (!drawRef.current) {
            const [
                { TerraDraw, TerraDrawPolygonMode },
                { TerraDrawMapLibreGLAdapter },
            ] = await Promise.all([
                import('terra-draw'),
                import('terra-draw-maplibre-gl-adapter'),
            ]);
            const draw = new TerraDraw({
                adapter: new TerraDrawMapLibreGLAdapter({
                    map,
                    prefixId: 'measure',
                }),
                modes: [new TerraDrawPolygonMode()],
            });
            draw.on('change', () => handleDrawChangeRef.current());
            draw.on('finish', () => handleDrawFinishRef.current());
            drawRef.current = draw;
        }
        if (!startedRef.current) {
            drawRef.current.start();
            startedRef.current = true;
        }
        return drawRef.current;
    }, [map]);

    const startMeasuring = useCallback(async () => {
        const draw = await ensureDraw();
        if (!draw) return;
        setResult(null);
        setPopupPos(null);
        setCursorClass('measure-crosshair');
        removeResultPolygon();
        draw.clear();
        draw.setMode('polygon');
    }, [ensureDraw]);

    const stopMeasuring = useCallback(() => {
        removeSegmentLabels();
        removeResultPolygon();
        const draw = drawRef.current;
        if (draw && startedRef.current) {
            draw.clear();
            draw.stop();
            startedRef.current = false;
        }
        setResult(null);
        setPopupPos(null);
        setCursorClass('');
        onReleaseTool?.('measure');
    }, [onReleaseTool]);

    const toggleOpen = useCallback(() => {
        setOpen((prev) => {
            const nextOpen = !prev;
            if (nextOpen && onRequestTool && !onRequestTool('measure'))
                return prev;
            if (!nextOpen) {
                stopMeasuring();
            }
            return nextOpen;
        });
    }, [onRequestTool, stopMeasuring]);

    const handleModeSelect = useCallback(() => {
        void startMeasuring();
    }, [startMeasuring]);

    // ---- Escape handler ----
    useEffect(() => {
        if (!open) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                stopMeasuring();
                setOpen(false);
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [open, stopMeasuring]);

    // ---- close when another tool activates ----
    useEffect(() => {
        if (open && activeTool && activeTool !== 'measure') {
            setOpen(false);
            stopMeasuring();
        }
    }, [activeTool, open, stopMeasuring]);

    // ---- unmount cleanup ----
    const onReleaseToolRef = useRef(onReleaseTool);
    onReleaseToolRef.current = onReleaseTool;

    useEffect(() => {
        return () => {
            removeSegmentLabels();
            removeResultPolygon();
            const draw = drawRef.current;
            if (draw && startedRef.current) {
                draw.stop();
                startedRef.current = false;
            }
            drawRef.current = null;
            onReleaseToolRef.current?.('measure');
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    return (
        <>
            <div
                className="flex flex-col items-end gap-2"
                data-testid="measure-tool"
            >
                <button
                    type="button"
                    aria-label={
                        open
                            ? 'Close measurement tool'
                            : 'Measure distance and area'
                    }
                    aria-expanded={open}
                    title="Measure"
                    data-testid="measure-toggle"
                    onClick={toggleOpen}
                    className={cn(
                        'glass flex size-9 items-center justify-center rounded-md text-foreground/80 transition-colors duration-fast ease-standard',
                        'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        open && 'bg-primary/15 text-foreground',
                    )}
                >
                    <Ruler className="size-5" strokeWidth={1.75} />
                </button>
                {open && (
                    <div
                        data-testid="measure-panel"
                        className="flex flex-col gap-1"
                        role="region"
                        aria-label="Measurement modes"
                    >
                        <button
                            type="button"
                            data-testid="measure-distance-btn"
                            className="glass flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-foreground/80 transition-colors duration-fast ease-standard hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            onClick={handleModeSelect}
                        >
                            Distance
                        </button>
                        <button
                            type="button"
                            data-testid="measure-area-btn"
                            className="glass flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-foreground/80 transition-colors duration-fast ease-standard hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            onClick={handleModeSelect}
                        >
                            Area
                        </button>
                    </div>
                )}
            </div>

            {result && popupPos && createPortal(
                <div
                    className="fixed z-toolbar"
                    style={{ left: popupPos.x, top: popupPos.y, transform: 'translate(-50%, calc(-100% - 12px))' }}
                    data-testid="measure-readout"
                >
                    <div className="relative glass rounded-lg px-5 py-4 shadow-lg">
                        <button
                            type="button"
                            onClick={() => {
                                stopMeasuring();
                                setOpen(false);
                            }}
                            data-testid="measure-readout-close"
                            className="absolute right-2 top-2 rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label="Clear measurement"
                            title="Clear measurement"
                        >
                            <X className="size-4" strokeWidth={2} />
                        </button>
                        <div className="flex flex-col gap-1 pr-5">
                            <span className="text-xs font-medium text-foreground">
                                Measure distance
                            </span>
                            <span className="font-mono text-sm tabular-nums text-muted-foreground">
                                Total area:{' '}
                                <span className="text-foreground">
                                    {(result.area / 10000).toFixed(2)} ha
                                </span>
                            </span>
                            <span className="font-mono text-sm tabular-nums text-muted-foreground">
                                Total distance:{' '}
                                <span className="text-foreground">
                                    {(result.distance / 1000).toFixed(2)} km
                                </span>
                            </span>
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </>
    );
}
