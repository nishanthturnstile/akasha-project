import { useCallback, useEffect, useRef, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import type { SceneDate } from '@/types/api';
import { cn } from '@/lib/utils';

interface PlaybackControlsProps {
    /** Chronological, tile-available dates the playhead steps through. */
    dates: SceneDate[];
    selectedDate: string | null;
    onSelect: (acquisitionDate: string) => void;
    /** Pre-warm the upcoming scene's tiles to reduce flicker. */
    onPrefetch?: (acquisitionDate: string) => void;
}

/** Step cadence in ms for each speed multiplier. */
const SPEEDS = [1, 2, 4] as const;
const BASE_INTERVAL_MS = 1400;

/**
 * Temporal playback for the filmstrip: steps `selectedDate` oldest → newest,
 * looping at the end (Google Earth Timelapse pattern). The next scene is
 * pre-warmed so crossfades stay smooth. Pauses automatically when fewer than two
 * scenes are selectable.
 */
export function PlaybackControls({ dates, selectedDate, onSelect, onPrefetch }: PlaybackControlsProps) {
    const [playing, setPlaying] = useState(false);
    const [speedIdx, setSpeedIdx] = useState(0);

    // Keep the latest inputs in refs so the interval callback never goes stale.
    const datesRef = useRef(dates);
    const selectedRef = useRef(selectedDate);
    const onSelectRef = useRef(onSelect);
    const onPrefetchRef = useRef(onPrefetch);
    useEffect(() => {
        datesRef.current = dates;
        selectedRef.current = selectedDate;
        onSelectRef.current = onSelect;
        onPrefetchRef.current = onPrefetch;
    });

    const canPlay = dates.length >= 2;

    const step = useCallback(() => {
        const list = datesRef.current;
        if (list.length < 2) return;
        const idx = list.findIndex((d) => d.acquisitionDate === selectedRef.current);
        const nextIdx = idx < 0 ? 0 : (idx + 1) % list.length;
        onSelectRef.current(list[nextIdx].acquisitionDate);
        const prewarmIdx = (nextIdx + 1) % list.length;
        onPrefetchRef.current?.(list[prewarmIdx].acquisitionDate);
    }, []);

    useEffect(() => {
        if (!playing || !canPlay) return;
        const id = window.setInterval(step, BASE_INTERVAL_MS / SPEEDS[speedIdx]);
        return () => window.clearInterval(id);
    }, [playing, canPlay, speedIdx, step]);

    // Effective state: a "play" intent only animates while ≥2 scenes are selectable.
    const isPlaying = playing && canPlay;

    const togglePlay = useCallback(() => setPlaying((p) => !p), []);
    const cycleSpeed = useCallback(() => setSpeedIdx((i) => (i + 1) % SPEEDS.length), []);

    return (
        <div className="flex items-center gap-1" data-testid="playback-controls">
            <button
                type="button"
                onClick={ togglePlay }
                disabled={ !canPlay }
                aria-label={ isPlaying ? 'Pause timelapse' : 'Play timelapse' }
                aria-pressed={ isPlaying }
                title={ isPlaying ? 'Pause' : 'Play timelapse' }
                data-testid="playback-toggle"
                className={ cn(
                    'flex size-8 items-center justify-center rounded-md border border-border/60 bg-secondary/40 text-foreground/85 transition-colors duration-fast ease-standard',
                    'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    'disabled:cursor-not-allowed disabled:opacity-40',
                    isPlaying && 'bg-primary/15 text-foreground',
                ) }
            >
                { isPlaying ? (
                    <Pause className="size-4" strokeWidth={ 1.75 } />
                ) : (
                    <Play className="size-4" strokeWidth={ 1.75 } />
                ) }
            </button>
            <button
                type="button"
                onClick={ cycleSpeed }
                disabled={ !canPlay }
                aria-label={ `Playback speed ${SPEEDS[speedIdx]}×` }
                title="Cycle speed"
                data-testid="playback-speed"
                className={ cn(
                    'h-8 rounded-md border border-border/60 bg-secondary/40 px-2 font-mono text-[11px] tabular-nums text-foreground/85 transition-colors duration-fast ease-standard',
                    'hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    'disabled:cursor-not-allowed disabled:opacity-40',
                ) }
            >
                { SPEEDS[speedIdx] }×
            </button>
        </div>
    );
}
