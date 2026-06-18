import type { PlotGeometry } from '@/types/api';

/**
 * Converts a PlotGeometry into SVG viewBox + path data for a simple
 * polygon preview. Handles Polygon and MultiPolygon.
 */
function geometryToSvg(geometry: PlotGeometry): {
  viewBox: string;
  paths: { d: string; label: string }[];
} {
  const rings: [number, number][][] = [];

  const toLngLat = (ring: number[][]): [number, number][] =>
    ring.map(([lng, lat]) => [lng, lat] as [number, number]);

  if (geometry.type === 'Polygon') {
    rings.push(...geometry.coordinates.map((ring) => toLngLat(ring)));
  } else if (geometry.type === 'MultiPolygon') {
    for (const poly of geometry.coordinates) {
      rings.push(...poly.map((ring) => toLngLat(ring)));
    }
  }

  const allPoints = rings.flat();
  if (allPoints.length === 0) {
    return { viewBox: '0 0 100 100', paths: [] };
  }

  const lngs = allPoints.map(([lng]) => lng);
  const lats = allPoints.map(([, lat]) => lat);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);

  const pad = Math.max((maxLng - minLng) * 0.1 || 0.01, (maxLat - minLat) * 0.1 || 0.01);
  const x = minLng - pad;
  const y = minLat - pad;
  const w = maxLng - minLng + pad * 2 || 1;
  const h = maxLat - minLat + pad * 2 || 1;

  const viewBox = `${x} ${y} ${w} ${h}`;

  const paths = rings.map((ring) => {
    const d = ring.map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt[0]},${pt[1]}`).join('') + 'Z';
    return { d, label: ring.length > 0 ? `${ring[0][0].toFixed(4)}, ${ring[0][1].toFixed(4)}` : '' };
  });

  return { viewBox, paths };
}

interface GeometryPreviewProps {
  geometry: PlotGeometry;
  className?: string;
  width?: number;
  height?: number;
}

export function GeometryPreview({
  geometry,
  className,
  width = 80,
  height = 80,
}: GeometryPreviewProps) {
  const { viewBox, paths } = geometryToSvg(geometry);

  if (paths.length === 0) {
    return (
      <div
        className={className}
        style={{ width, height }}
        aria-label="No geometry available"
      />
    );
  }

  return (
    <svg
      viewBox={viewBox}
      width={width}
      height={height}
      className={className}
      aria-label="Field geometry preview"
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      {paths.map((p, i) => (
        <path
          key={i}
          d={p.d}
          fill="hsl(var(--primary) / 0.15)"
          stroke="hsl(var(--primary))"
          strokeWidth={Math.max(width / 200, 0.5)}
        />
      ))}
    </svg>
  );
}
