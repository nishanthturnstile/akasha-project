import { useCallback, useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Crosshair, Loader2, MapPin, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGeocoding, type GeocodingResult } from '@/hooks/useGeocoding';

interface LocationSearchProps {
  map: maplibregl.Map | null;
  className?: string;
}

export function LocationSearch({ map, className }: LocationSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const { results, loading, error } = useGeocoding(query);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointer = (e: PointerEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('pointerdown', handlePointer);
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('pointerdown', handlePointer);
      window.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const flyTo = useCallback((result: GeocodingResult) => {
    if (!map) return;
    if (result.bbox) {
      map.fitBounds(
        [[result.bbox[0], result.bbox[1]], [result.bbox[2], result.bbox[3]]],
        { padding: 64, maxZoom: 18, duration: 650 },
      );
    } else {
      map.flyTo({ center: result.center, zoom: 13, duration: 650 });
    }
    setOpen(false);
    setQuery('');
    inputRef.current?.blur();
  }, [map]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0 && results[selectedIndex]) {
        flyTo(results[selectedIndex]);
      } else if (results.length > 0) {
        flyTo(results[0]);
      }
    }
  };

  const showDropdown = open && query.trim().length > 0;

  return (
    <div ref={ref} className={cn('relative', className)}>
      <div className="glass-card flex items-center gap-2 rounded-md px-3 h-12 shadow-e2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setSelectedIndex(-1); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search Location"
          className="h-full flex-1 bg-transparent text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none"
          aria-label="Search location"
          autoComplete="off"
          spellCheck={false}
        />
        {loading ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" strokeWidth={1.75} />
        ) : (
          <Search className="size-4 shrink-0 text-muted-foreground/70" strokeWidth={1.75} />
        )}
      </div>

      {showDropdown && (
        <div className="absolute left-0 top-full mt-1 w-full min-w-64 rounded-md border border-border bg-popover shadow-e2 max-h-60 overflow-y-auto z-popover">
          {loading && (
            <p className="flex items-center gap-2 px-3 py-2.5 text-[12px] text-muted-foreground">
              <Loader2 className="size-3 animate-spin" strokeWidth={1.75} />
              Searching\u2026
            </p>
          )}
          {!loading && error && (
            <p className="px-3 py-2.5 text-[12px] text-muted-foreground">{error}</p>
          )}
          {!loading && !error && results.length === 0 && (
            <p className="px-3 py-2.5 text-[12px] text-muted-foreground">No results found</p>
          )}
          {results.map((result, i) => (
            <button
              key={`${result.type}-${i}`}
              type="button"
              onClick={() => flyTo(result)}
              onMouseEnter={() => setSelectedIndex(i)}
              className={cn(
                'flex w-full items-center gap-3 px-3 py-2.5 text-left text-[13px] transition-colors duration-fast',
                i === selectedIndex ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-accent/50',
              )}
            >
              {result.type === 'coords' ? (
                <Crosshair className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
              ) : (
                <MapPin className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
              )}
              <span className="flex-1 truncate">{result.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
