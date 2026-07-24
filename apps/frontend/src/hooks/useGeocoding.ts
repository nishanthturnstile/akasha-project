import { useState, useEffect, useRef } from 'react';

export interface GeocodingResult {
  label: string;
  center: [number, number];
  bbox?: [number, number, number, number];
  type: 'place' | 'coords';
}

const COORDS_PATTERN = /^\s*([+-]?\d+\.?\d*)\s*,\s*([+-]?\d+\.?\d*)\s*$/;

export function parseCoords(query: string): GeocodingResult | null {
  const match = query.replace(/\u2212/g, '-').match(COORDS_PATTERN);
  if (!match) return null;
  const lon = parseFloat(match[1]);
  const lat = parseFloat(match[2]);
  if (isNaN(lon) || isNaN(lat)) return null;
  if (lon < -180 || lon > 180) return null;
  if (lat < -90 || lat > 90) return null;
  return {
    label: `${lon.toFixed(4)}, ${lat.toFixed(4)}`,
    center: [lon, lat],
    type: 'coords',
  };
}

export function useGeocoding(query: string): {
  results: GeocodingResult[];
  loading: boolean;
  error: string | null;
} {
  const [results, setResults] = useState<GeocodingResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const controller = new AbortController();

    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }

    const coords = parseCoords(trimmed);
    if (coords) {
      setResults([coords]);
      setLoading(false);
      setError(null);
      return;
    }
    if (COORDS_PATTERN.test(trimmed.replace(/\u2212/g, '-'))) {
      setResults([]);
      setLoading(false);
      setError('Coordinates must be longitude from -180 to 180, then latitude from -90 to 90');
      return;
    }

    setLoading(true);
    setError(null);
    debounceRef.current = setTimeout(async () => {
      try {
        const url = `/api/geocoding/search?q=${encodeURIComponent(trimmed)}`;
        const res = await fetch(url, { credentials: 'include', signal: controller.signal });
        if (!res.ok) {
          const payload = await res.json().catch(() => null) as {
            error?: { message?: string };
          } | null;
          throw new Error(payload?.error?.message ?? 'Location search failed');
        }
        const data = await res.json() as { results?: GeocodingResult[] };
        const placeResults = Array.isArray(data.results) ? data.results : [];
        setResults(placeResults);
        setError(placeResults.length === 0 ? 'No results found' : null);
      } catch (requestError) {
        if (controller.signal.aborted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Failed to search location',
        );
        setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      controller.abort();
    };
  }, [query]);

  return { results, loading, error };
}
