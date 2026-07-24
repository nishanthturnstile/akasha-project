import { describe, expect, it } from 'vitest';
import { TerraDrawExtend, TerraDrawPolygonMode } from 'terra-draw';
import { buildCircleRing, cardinalHandlePositions, deriveCircleFromRing } from './circleGeometry';

const { GeoJSONStore } = TerraDrawExtend;

// Regression test for a real bug: @turf/circle's raw floating-point output carries
// ~14-17 decimal digits of noise. TerraDraw's own validateFeature silently REJECTS
// features with "excessive coordinate precision" (no error surfaced to the user),
// so a circle resized/moved via the drag handles would save fine but come back
// completely blank -- not even a plain polygon outline -- the next time it was
// reopened for editing. Registering a real TerraDrawPolygonMode and running its
// actual validateFeature is what caught this originally; a plain decimal-count
// assertion would not have caught the same class of regression as reliably.
function registerPolygonMode() {
  const mode = new TerraDrawPolygonMode();
  mode.register({
    mode: 'polygon',
    store: new GeoJSONStore(),
    setDoubleClickToZoom: () => {},
    setCursor: () => {},
    onChange: () => {},
    onSelect: () => {},
    onDeselect: () => {},
    onFinish: () => {},
    project: (lng: number, lat: number) => ({ x: lng, y: lat }),
    unproject: (x: number, y: number) => ({ lng: x, lat: y }),
    coordinatePrecision: 9,
  });
  return mode;
}

describe('circleGeometry precision', () => {
  it('buildCircleRing output passes TerraDraw\'s own feature validation', () => {
    const mode = registerPolygonMode();
    const ring = buildCircleRing([77.5751, 13.0734], 120);
    const feature = {
      type: 'Feature' as const,
      id: '12345678-1234-1234-1234-123456789012',
      geometry: { type: 'Polygon' as const, coordinates: [ring] },
      properties: { mode: 'polygon' },
    };
    expect(mode.validateFeature(feature)).toEqual({ valid: true });
  });

  it('buildCircleRing coordinates never exceed 9 decimal places', () => {
    const ring = buildCircleRing([77.5751, 13.0734], 250);
    for (const [lng, lat] of ring) {
      expect(lng.toString().split('.')[1]?.length ?? 0).toBeLessThanOrEqual(9);
      expect(lat.toString().split('.')[1]?.length ?? 0).toBeLessThanOrEqual(9);
    }
  });

  it('cardinalHandlePositions coordinates never exceed 9 decimal places', () => {
    const handles = cardinalHandlePositions([77.5751, 13.0734], 80);
    expect(handles).toHaveLength(4);
    for (const [lng, lat] of handles) {
      expect(lng.toString().split('.')[1]?.length ?? 0).toBeLessThanOrEqual(9);
      expect(lat.toString().split('.')[1]?.length ?? 0).toBeLessThanOrEqual(9);
    }
  });

  it('a ring regenerated from a dragged/resized circle still round-trips through the heuristic', () => {
    // Simulates what happens after a resize drag: build a ring, then immediately
    // re-derive circle params from it on "reopen" -- must still detect as a circle.
    const ring = buildCircleRing([77.5751, 13.0734], 300);
    const params = deriveCircleFromRing(ring);
    expect(params).not.toBeNull();
    expect(params?.radiusMeters).toBeGreaterThan(295);
    expect(params?.radiusMeters).toBeLessThan(305);
  });
});
