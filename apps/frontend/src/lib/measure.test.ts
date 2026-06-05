import { describe, expect, it } from 'vitest';
import {
  formatArea,
  formatDistance,
  haversineMeters,
  lineLengthMeters,
  polygonAreaMeters,
} from '@/lib/measure';

describe('measure helpers', () => {
  it('haversineMeters matches ~1 degree of latitude', () => {
    // 1° of latitude ≈ 111.2 km on a sphere.
    const d = haversineMeters([0, 0], [0, 1]);
    expect(d).toBeGreaterThan(111_000);
    expect(d).toBeLessThan(111_400);
  });

  it('haversineMeters is zero for identical points', () => {
    expect(haversineMeters([77.6, 12.9], [77.6, 12.9])).toBe(0);
  });

  it('lineLengthMeters sums segment lengths', () => {
    const total = lineLengthMeters([
      [0, 0],
      [0, 1],
      [0, 2],
    ]);
    const single = haversineMeters([0, 0], [0, 1]);
    expect(total).toBeCloseTo(single * 2, 0);
  });

  it('lineLengthMeters returns 0 for under two points', () => {
    expect(lineLengthMeters([])).toBe(0);
    expect(lineLengthMeters([[0, 0]])).toBe(0);
  });

  it('polygonAreaMeters approximates a 1°×1° box near the equator', () => {
    const area = polygonAreaMeters([
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
      [0, 0],
    ]);
    // ~12,300 km² at the equator; allow generous tolerance.
    expect(area).toBeGreaterThan(1.2e10);
    expect(area).toBeLessThan(1.3e10);
  });

  it('formatDistance switches units sensibly', () => {
    expect(formatDistance(5)).toMatch(/m$/);
    expect(formatDistance(950)).toMatch(/m$/);
    expect(formatDistance(2500)).toMatch(/km$/);
  });

  it('formatArea switches units sensibly', () => {
    expect(formatArea(500)).toMatch(/m²$/);
    expect(formatArea(50_000)).toMatch(/ha$/);
    expect(formatArea(5_000_000)).toMatch(/km²$/);
  });
});
