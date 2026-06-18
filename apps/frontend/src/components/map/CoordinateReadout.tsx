import { useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';

interface CoordinateReadoutProps {
    map: maplibregl.Map | null;
    indexLookup?: (point: { lng: number; lat: number }) => Promise<{
        indexType: string;
        value: number | null;
        masked: boolean;
    } | null>;
}

/** Format a signed degree value with a hemisphere suffix, fixed to 4 dp (~11 m). */
function formatLatLng(value: number, positive: string, negative: string): string {
    const hemisphere = value >= 0 ? positive : negative;
    return `${Math.abs(value).toFixed(4)}° ${hemisphere}`;
}

/**
 * Live longitude/latitude under the cursor. Reads the pointer position on
 * `mousemove`, coalesced to one update per animation frame to keep it cheap, and
 * renders a compact monospaced pill. Hidden on touch (no hover) and until the
 * pointer first enters the map.
 */
export function CoordinateReadout({ map, indexLookup }: CoordinateReadoutProps) {
    const [coords, setCoords] = useState<{ lng: number; lat: number } | null>(null);
    const [indexSample, setIndexSample] = useState<{
        indexType: string;
        value: number | null;
        masked: boolean;
    } | null>(null);
    const frame = useRef<number | null>(null);
    const pending = useRef<{ lng: number; lat: number } | null>(null);
    const lookupSeq = useRef(0);

    useEffect(() => {
        if (!map) return;

        const flush = () => {
            frame.current = null;
            if (!pending.current) return;
            const next = pending.current;
            setCoords(next);
            if (!indexLookup) {
                setIndexSample(null);
                return;
            }
            const seq = ++lookupSeq.current;
            void indexLookup(next).then((sample) => {
                if (lookupSeq.current === seq) setIndexSample(sample);
            }).catch(() => {
                if (lookupSeq.current === seq) setIndexSample(null);
            });
        };
        const onMove = (event: maplibregl.MapMouseEvent) => {
            pending.current = { lng: event.lngLat.lng, lat: event.lngLat.lat };
            if (frame.current === null) frame.current = requestAnimationFrame(flush);
        };
        const onLeave = () => {
            pending.current = null;
            if (frame.current !== null) {
                cancelAnimationFrame(frame.current);
                frame.current = null;
            }
            lookupSeq.current += 1;
            setCoords(null);
            setIndexSample(null);
        };

        map.on('mousemove', onMove);
        map.on('mouseout', onLeave);
        return () => {
            map.off('mousemove', onMove);
            map.off('mouseout', onLeave);
            if (frame.current !== null) cancelAnimationFrame(frame.current);
        };
    }, [map, indexLookup]);

    if (!coords) return null;

    return (
        <div
            data-testid="coordinate-readout"
            aria-hidden="true"
            className="glass pointer-events-none hidden select-none items-center gap-2 rounded-md px-2.5 py-1.5 font-mono text-[11px] tabular-nums text-foreground/80 on-map-text sm:flex"
        >
            <span>{ formatLatLng(coords.lat, 'N', 'S') }</span>
            <span className="text-border">|</span>
            <span>{ formatLatLng(coords.lng, 'E', 'W') }</span>
            { indexSample && !indexSample.masked && indexSample.value !== null && (
                <>
                    <span className="text-border">|</span>
                    <span>{ indexSample.indexType } { indexSample.value.toFixed(2) }</span>
                </>
            ) }
        </div>
    );
}
