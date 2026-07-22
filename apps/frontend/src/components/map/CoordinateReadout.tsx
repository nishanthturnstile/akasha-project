import { useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { ndviInterpretation } from '@/lib/indexRamp';

import type { PlotGeometry } from '@/types/api';

interface CoordinateReadoutProps {
    map: maplibregl.Map | null;
    interactiveLayerId?: string;
    indexLookup?: (point: { lng: number; lat: number }) => Promise<{
        indexType: string;
        value: number | null;
        masked: boolean;
        maskClass?: number | null;
        sourceId?: string;
    } | null>;
    fieldGeometry?: PlotGeometry | null;
}

function geometryCenter(geom: PlotGeometry): { lng: number; lat: number } {
    const coords = geom.type === 'Polygon'
        ? geom.coordinates[0]
        : geom.coordinates.flat(1)[0];
    let minLng = Infinity, maxLng = -Infinity;
    let minLat = Infinity, maxLat = -Infinity;
    for (const [lng, lat] of coords) {
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
    }
    return { lng: (minLng + maxLng) / 2, lat: (minLat + maxLat) / 2 };
}

/** Minimum time between point-request starts. Slow requests are serialized and
 * only the latest cursor position is retained, preventing raster-service floods. */
const INDEX_LOOKUP_INTERVAL_MS = 120;
const TOOLTIP_HALF_WIDTH_PX = 88;
const TOOLTIP_TOP_GUARD_PX = 84;

interface CursorPosition {
    lng: number;
    lat: number;
    x: number;
    y: number;
    tooltipX: number;
    tooltipBelow: boolean;
    inspectable: boolean;
}

interface IndexSample {
    indexType: string;
    value: number | null;
    masked: boolean;
    maskClass?: number | null;
    sourceId?: string;
    lookup: CoordinateReadoutProps['indexLookup'];
}

/** Format a signed degree value with a hemisphere suffix, fixed to 4 dp (~11 m). */
function formatLatLng(value: number, positive: string, negative: string): string {
    const hemisphere = value >= 0 ? positive : negative;
    return `${Math.abs(value).toFixed(4)}° ${hemisphere}`;
}

function maskedInterpretation(sourceId: string | undefined, maskClass: number | null | undefined) {
    if (maskClass == null) return 'Cloud / masked';
    const resourceSat = /resourcesat|liss|awifs/i.test(sourceId ?? '');
    if (resourceSat) {
        return ({
            0: 'No data',
            2: 'Cloud',
            3: 'Cloud shadow',
        } as Record<number, string>)[maskClass] ?? 'Cloud / masked';
    }
    return ({
        0: 'No data',
        1: 'Saturated / defective pixel',
        2: 'Dark area pixel',
        3: 'Cloud shadow',
        7: 'Low-confidence cloud',
        8: 'Cloud',
        9: 'Cloud',
        10: 'Thin cirrus',
        11: 'Snow / ice',
    } as Record<number, string>)[maskClass] ?? 'Cloud / masked';
}

function sampleInterpretation(sample: IndexSample): string | null {
    if (sample.masked) return maskedInterpretation(sample.sourceId, sample.maskClass);
    if (sample.value == null) return null;
    if (sample.indexType.toUpperCase() === 'NDVI') return ndviInterpretation(sample.value);
    return 'Valid observation';
}

function isInspectableMapPoint(
    map: maplibregl.Map,
    event: maplibregl.MapMouseEvent,
    interactiveLayerId: string | undefined,
): boolean {
    if (!interactiveLayerId) return true;
    if (!map.getLayer(interactiveLayerId)) return false;
    try {
        return map.queryRenderedFeatures(event.point, { layers: [interactiveLayerId] }).length > 0;
    } catch {
        return false;
    }
}

/**
 * Live longitude/latitude plus an EOS-style field index inspector. Pointer
 * updates are coalesced to one animation frame. Point sampling starts immediately,
 * stays serialized, and continuously consumes the latest cursor position while
 * the pointer remains over the rendered field fill. The last resolved value stays
 * visible while the next point is sampled, matching EOS without flooding the BFF.
 */
export function CoordinateReadout({ map, interactiveLayerId, indexLookup, fieldGeometry }: CoordinateReadoutProps) {
    const [cursor, setCursor] = useState<CursorPosition | null>(null);
    const [indexSample, setIndexSample] = useState<IndexSample | null>(null);
    const frame = useRef<number | null>(null);
    const lookupTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pending = useRef<CursorPosition | null>(null);

    useEffect(() => {
        if (!map) return;
        let disposed = false;
        let lookupInFlight = false;
        let lastLookupStartedAt: number | null = null;
        let lastRequestedPoint: { lng: number; lat: number } | null = null;
        let fieldSession = 0;

        const samePoint = (
            left: { lng: number; lat: number } | null,
            right: { lng: number; lat: number } | null,
        ) => left?.lng === right?.lng && left?.lat === right?.lat;

        const requestLatestPoint = () => {
            if (disposed || lookupInFlight || !indexLookup) return;
            const target = pending.current;
            if (!target?.inspectable) return;

            const elapsed = lastLookupStartedAt == null
                ? INDEX_LOOKUP_INTERVAL_MS
                : Date.now() - lastLookupStartedAt;
            if (elapsed < INDEX_LOOKUP_INTERVAL_MS) {
                if (lookupTimer.current !== null) clearTimeout(lookupTimer.current);
                lookupTimer.current = setTimeout(() => {
                    lookupTimer.current = null;
                    requestLatestPoint();
                }, INDEX_LOOKUP_INTERVAL_MS - elapsed);
                return;
            }

            lookupInFlight = true;
            lastLookupStartedAt = Date.now();
            lastRequestedPoint = { lng: target.lng, lat: target.lat };
            const requestSession = fieldSession;
            void indexLookup(lastRequestedPoint).then((sample) => {
                if (
                    disposed ||
                    requestSession !== fieldSession ||
                    !pending.current?.inspectable
                ) return;
                if (sample) {
                    setIndexSample({
                        ...sample,
                        lookup: indexLookup,
                    });
                }
            }).catch(() => {
                // Keep the last good value visible. A later cursor sample can recover.
            }).finally(() => {
                lookupInFlight = false;
                if (
                    !disposed &&
                    pending.current?.inspectable &&
                    !samePoint(pending.current, lastRequestedPoint)
                ) {
                    requestLatestPoint();
                }
            });
        };

        const flush = () => {
            frame.current = null;
            if (!pending.current) return;
            const next = pending.current;
            setCursor(next);
            if (!indexLookup || !next.inspectable) {
                if (lookupTimer.current !== null) clearTimeout(lookupTimer.current);
                lookupTimer.current = null;
                fieldSession += 1;
                lastRequestedPoint = null;
                setIndexSample(null);
                return;
            }
            if (!samePoint(next, lastRequestedPoint)) requestLatestPoint();
        };
        const onMove = (event: maplibregl.MapMouseEvent) => {
            const canvasWidth = map.getCanvas().clientWidth;
            pending.current = {
                lng: event.lngLat.lng,
                lat: event.lngLat.lat,
                x: event.point.x,
                y: event.point.y,
                tooltipX: Math.min(
                    Math.max(event.point.x, TOOLTIP_HALF_WIDTH_PX),
                    Math.max(TOOLTIP_HALF_WIDTH_PX, canvasWidth - TOOLTIP_HALF_WIDTH_PX),
                ),
                tooltipBelow: event.point.y < TOOLTIP_TOP_GUARD_PX,
                inspectable: isInspectableMapPoint(map, event, interactiveLayerId),
            };
            if (frame.current === null) frame.current = requestAnimationFrame(flush);
        };
        const onLeave = () => {
            pending.current = null;
            if (frame.current !== null) {
                cancelAnimationFrame(frame.current);
                frame.current = null;
            }
            if (lookupTimer.current !== null) {
                clearTimeout(lookupTimer.current);
                lookupTimer.current = null;
            }
            fieldSession += 1;
            lastRequestedPoint = null;
            setCursor(null);
            setIndexSample(null);
        };

        map.on('mousemove', onMove);
        map.on('mouseout', onLeave);
        return () => {
            disposed = true;
            map.off('mousemove', onMove);
            map.off('mouseout', onLeave);
            if (frame.current !== null) cancelAnimationFrame(frame.current);
            if (lookupTimer.current !== null) clearTimeout(lookupTimer.current);
        };
    }, [map, interactiveLayerId, indexLookup]);

    if (!cursor && !fieldGeometry) return null;

    const currentSample = indexSample?.lookup === indexLookup ? indexSample : null;
    const interpretation = currentSample ? sampleInterpretation(currentSample) : null;
    const showIndexTooltip = cursor?.inspectable && currentSample && (
        currentSample.masked || (currentSample.value !== null && interpretation !== null)
    );

    const displayPoint = fieldGeometry
        ? geometryCenter(fieldGeometry)
        : cursor
            ? { lat: cursor.lat, lng: cursor.lng }
            : null;

    if (!displayPoint) return null;

    return (
        <>
            <div
                data-testid="coordinate-readout"
                aria-hidden="true"
                className="glass pointer-events-none absolute left-4 top-4 hidden select-none items-center gap-2 rounded-md px-2.5 py-1.5 font-mono text-[11px] tabular-nums text-foreground/80 on-map-text sm:flex"
            >
                <span>{ formatLatLng(displayPoint.lat, 'N', 'S') }</span>
                <span className="text-border">|</span>
                <span>{ formatLatLng(displayPoint.lng, 'E', 'W') }</span>
            </div>
            { showIndexTooltip && (
                <div
                    data-testid="index-hover-tooltip"
                    role="status"
                    aria-live="polite"
                    className="pointer-events-none absolute hidden min-w-36 select-none rounded-lg bg-[#010203] px-4 py-3 text-left text-white shadow-e2 ring-1 ring-white/15 sm:block"
                    style={ {
                        left: cursor.tooltipX,
                        top: cursor.y,
                        transform: cursor.tooltipBelow
                            ? 'translate(-50%, 12px)'
                            : 'translate(-50%, calc(-100% - 12px))',
                    } }
                >
                    <strong className="block text-[13px] font-semibold leading-5 tabular-nums">
                        { currentSample.indexType }: { currentSample.masked
                            ? 'Masked'
                            : currentSample.value?.toFixed(2) }
                    </strong>
                    <span className="block text-[13px] leading-5 text-white/90">
                        { interpretation }
                    </span>
                </div>
            ) }
        </>
    );
}
