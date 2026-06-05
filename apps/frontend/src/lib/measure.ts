// Pure geodesic helpers for the on-map measurement tool. Spherical-earth
// approximations (WGS84 mean radius) — accurate to well within a percent at the
// city/plot scale this tool is used for, and dependency-free.

const EARTH_RADIUS_M = 6371008.8; // IUGG mean radius
const WGS84_RADIUS_M = 6378137; // semi-major axis, used for the area formula

const toRad = (deg: number): number => (deg * Math.PI) / 180;

/** Great-circle distance between two [lng, lat] points, in metres. */
export function haversineMeters(a: [number, number], b: [number, number]): number {
  const [lng1, lat1] = a;
  const [lng2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const sinLat = Math.sin(dLat / 2);
  const sinLng = Math.sin(dLng / 2);
  const h =
    sinLat * sinLat + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * sinLng * sinLng;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Total length of a [lng, lat][] line, in metres. */
export function lineLengthMeters(coords: [number, number][]): number {
  let total = 0;
  for (let i = 1; i < coords.length; i += 1) {
    total += haversineMeters(coords[i - 1], coords[i]);
  }
  return total;
}

/**
 * Geodesic area of a polygon ring (outer ring of [lng, lat][][]), in square
 * metres. Uses the standard spherical-excess approximation (same formula as
 * `@turf/area`); sign is dropped so winding order is irrelevant.
 */
export function polygonAreaMeters(ring: [number, number][]): number {
  if (ring.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < ring.length; i += 1) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % ring.length];
    area += toRad(p2[0] - p1[0]) * (2 + Math.sin(toRad(p1[1])) + Math.sin(toRad(p2[1])));
  }
  area = (area * WGS84_RADIUS_M * WGS84_RADIUS_M) / 2;
  return Math.abs(area);
}

/** Human-readable distance: metres below 1 km, kilometres above. */
export function formatDistance(meters: number): string {
  if (meters < 1000) return `${meters.toFixed(meters < 10 ? 1 : 0)} m`;
  return `${(meters / 1000).toFixed(2)} km`;
}

/** Human-readable area: m² / ha / km² by magnitude. */
export function formatArea(squareMeters: number): string {
  if (squareMeters < 10000) return `${squareMeters.toFixed(0)} m²`;
  if (squareMeters < 1_000_000) return `${(squareMeters / 10000).toFixed(2)} ha`;
  return `${(squareMeters / 1_000_000).toFixed(2)} km²`;
}
