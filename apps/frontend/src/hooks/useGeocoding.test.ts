import { describe, expect, it } from 'vitest';
import { parseCoords } from '@/hooks/useGeocoding';

describe('parseCoords', () => {
  it('parses longitude first and latitude last', () => {
    expect(parseCoords('77.5946, 12.9716')).toEqual({
      label: '77.5946, 12.9716',
      center: [77.5946, 12.9716],
      type: 'coords',
    });
  });

  it('accepts signed coordinates and a pasted Unicode minus sign', () => {
    expect(parseCoords('\u221243.1729, -22.9068')?.center).toEqual([-43.1729, -22.9068]);
  });

  it('rejects coordinates outside longitude and latitude ranges', () => {
    expect(parseCoords('181, 0')).toBeNull();
    expect(parseCoords('0, -91')).toBeNull();
  });
});
