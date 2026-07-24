import circle from '@turf/circle';
import distance from '@turf/distance';
import type { Position } from 'geojson';

/** Matches the ring density TerraDrawCircleMode({ segments: 64 }) produces. */
export const CIRCLE_SEGMENTS = 64;
const RADIUS_TOLERANCE = 0.005; // 0.5%
const ANGLE_TOLERANCE_DEG = 2;
const EARTH_RADIUS_M = 6371008.8;

export interface CircleParams {
  center: Position;
  radiusMeters: number;
}

function ringWithoutClosingPoint(ring: Position[]): Position[] {
  if (ring.length < 2) return ring;
  const [firstLng, firstLat] = ring[0];
  const [lastLng, lastLat] = ring[ring.length - 1];
  if (firstLng === lastLng && firstLat === lastLat) {
    return ring.slice(0, -1);
  }
  return ring;
}

function centroidOf(points: Position[]): Position {
  let sumLng = 0;
  let sumLat = 0;
  for (const [lng, lat] of points) {
    sumLng += lng;
    sumLat += lat;
  }
  return [sumLng / points.length, sumLat / points.length];
}

/**
 * Two-axis heuristic: a ring only counts as circle-editable if its vertices are both
 * equidistant from the centroid (radius uniformity) AND evenly spaced angularly around it
 * (angular uniformity). Radius uniformity alone can't rule out a non-circular closed curve
 * with the same average distance from centroid; a hand-drawn ring satisfying both checks
 * across exactly 64 points is not achievable by manual clicking. Non-destructive: this only
 * decides which edit affordance to offer, the ring itself is never rewritten just from a
 * positive match here.
 */
export function deriveCircleFromRing(ring: Position[] | undefined | null): CircleParams | null {
  if (!ring || ring.length === 0) return null;
  const points = ringWithoutClosingPoint(ring);
  if (points.length !== CIRCLE_SEGMENTS) return null;

  const center = centroidOf(points);
  const radiiKm = points.map((p) => distance(center, p, { units: 'kilometers' }));
  const meanKm = radiiKm.reduce((a, b) => a + b, 0) / radiiKm.length;
  if (!(meanKm > 0)) return null;

  for (const r of radiiKm) {
    if (Math.abs(r - meanKm) / meanKm > RADIUS_TOLERANCE) return null;
  }

  const angles = points
    .map(([lng, lat]) => (Math.atan2(lat - center[1], lng - center[0]) * 180) / Math.PI)
    .map((a) => (a + 360) % 360)
    .sort((a, b) => a - b);
  const expectedStep = 360 / CIRCLE_SEGMENTS;
  for (let i = 0; i < angles.length; i++) {
    const next = angles[(i + 1) % angles.length];
    let step = next - angles[i];
    if (step < 0) step += 360;
    if (Math.abs(step - expectedStep) > ANGLE_TOLERANCE_DEG) return null;
  }

  return { center, radiusMeters: meanKm * 1000 };
}

// Matches TerraDraw's own default `coordinatePrecision` (confirmed in its source).
// @turf/circle's raw floating-point output carries ~14-17 decimal digits of noise;
// TerraDraw's own validateFeature REJECTS features with "excessive precision" --
// silently, with no UI error -- so every ring this mode writes back to the store
// (and therefore to the backend) must be rounded to the same precision TerraDraw
// itself uses when *drawing* a circle, or a dragged/resized circle becomes
// unreadable the next time it's reopened for editing.
const COORDINATE_PRECISION = 9;

function roundCoordinate([lng, lat]: Position): Position {
  const factor = 10 ** COORDINATE_PRECISION;
  return [Math.round(lng * factor) / factor, Math.round(lat * factor) / factor];
}

/**
 * Rounds every vertex of a ring to TerraDraw's coordinate precision. Fields saved
 * before this fix (or from any other source of excessive-precision coordinates)
 * still have the raw, unrounded values sitting in the database -- loading one of
 * those into TerraDraw for editing hits the same silent rejection. Call this on
 * any ring right before handing it to `TerraDraw.addFeatures`, not just on ones
 * this module generates itself, so already-affected fields self-heal on next open
 * (the fix is re-applied and re-saved) without needing a data migration.
 */
export function sanitizeRingPrecision(ring: Position[]): Position[] {
  return ring.map(roundCoordinate);
}

/** Closed ring (first point repeated), same segment density as TerraDrawCircleMode's output. */
export function buildCircleRing(center: Position, radiusMeters: number): Position[] {
  const feature = circle(center, radiusMeters / 1000, { steps: CIRCLE_SEGMENTS, units: 'kilometers' });
  return feature.geometry.coordinates[0].map(roundCoordinate);
}

function destinationPoint(center: Position, radiusMeters: number, bearingDeg: number): Position {
  const angularDistance = radiusMeters / EARTH_RADIUS_M;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (center[1] * Math.PI) / 180;
  const lng1 = (center[0] * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angularDistance) +
      Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing),
  );
  const lng2 =
    lng1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
      Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2),
    );
  return roundCoordinate([(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
}

export type HandleRole = 'n' | 'e' | 's' | 'w';
export const HANDLE_ROLES: HandleRole[] = ['n', 'e', 's', 'w'];
const HANDLE_BEARINGS: Record<HandleRole, number> = { n: 0, e: 90, s: 180, w: 270 };

export function cardinalHandlePositions(center: Position, radiusMeters: number): Position[] {
  return HANDLE_ROLES.map((role) => destinationPoint(center, radiusMeters, HANDLE_BEARINGS[role]));
}

export function pointInRing(point: Position, ring: Position[]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
