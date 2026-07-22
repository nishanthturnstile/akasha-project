import type { PlotGeometry } from '@/types/api';

/** Converts field geometry into stable SVG path data without changing coordinates. */
export function geometryToSvg(geometry: PlotGeometry): {
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

  const paths = rings.map((ring) => {
    const d = `${ring.map((point, index) => `${index === 0 ? 'M' : 'L'}${point[0]},${point[1]}`).join('')}Z`;
    const label = ring.length > 0 ? `${ring[0][0].toFixed(4)}, ${ring[0][1].toFixed(4)}` : '';
    return { d, label };
  });

  return { viewBox: `${x} ${y} ${w} ${h}`, paths };
}
