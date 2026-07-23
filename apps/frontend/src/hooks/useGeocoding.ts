import { useState, useEffect, useRef } from 'react';

export interface GeocodingResult {
  label: string;
  center: [number, number];
  bbox?: [number, number, number, number];
  type: 'place' | 'coords';
}

const COORDS_PATTERN = /^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$/;

interface NominatimItem {
  display_name: string;
  lon: string;
  lat: string;
  boundingbox: [string, string, string, string];
}

function parseCoords(query: string): GeocodingResult | null {
  const match = query.match(COORDS_PATTERN);
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

    setLoading(true);
    setError(null);
    debounceRef.current = setTimeout(async () => {
      try {
        const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(trimmed)}&format=json&limit=5&addressdetails=0`;
        const res = await fetch(url, {
          headers: { 'Accept-Language': 'en' },
        });
        if (!res.ok) throw new Error('Geocoding request failed');
        const data = await res.json() as NominatimItem[];
        const placeResults: GeocodingResult[] = data.map((item) => ({
          label: item.display_name,
          center: [parseFloat(item.lon), parseFloat(item.lat)] as [number, number],
          bbox: item.boundingbox
            ? ([
                parseFloat(item.boundingbox[2]),
                parseFloat(item.boundingbox[0]),
                parseFloat(item.boundingbox[3]),
                parseFloat(item.boundingbox[1]),
              ] as [number, number, number, number])
            : undefined,
          type: 'place' as const,
        }));
        setResults(placeResults);
        setError(placeResults.length === 0 ? 'No results found' : null);
      } catch {
        setError('Failed to search location');
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  return { results, loading, error };
}
