import { describe, expect, it } from 'vitest';
import { selectDefaultDate } from '@/lib/selectDefaultDate';
import type { SceneDate } from '@/types/api';

function makeDate(partial: Partial<SceneDate>): SceneDate {
  return {
    acquisitionDate: '2025-01-01',
    datetime: '2025-01-01T00:00:00Z',
    usablePixelPercent: null,
    cloudMaskedPercent: null,
    coveragePercent: null,
    isLatestUsable: false,
    metricsProvisional: false,
    tileAvailable: true,
    ...partial,
  };
}

describe('selectDefaultDate', () => {
  it('returns null for an empty list', () => {
    expect(selectDefaultDate([], 70)).toBeNull();
  });

  it('prefers the isLatestUsable date', () => {
    const dates = [
      makeDate({ acquisitionDate: '2025-09-20', usablePixelPercent: 30 }),
      makeDate({ acquisitionDate: '2025-09-14', usablePixelPercent: 82, isLatestUsable: true }),
      makeDate({ acquisitionDate: '2025-09-01', usablePixelPercent: 90 }),
    ];
    expect(selectDefaultDate(dates, 70)?.acquisitionDate).toBe('2025-09-14');
  });

  it('falls back to the newest date over threshold when none flagged', () => {
    const dates = [
      makeDate({ acquisitionDate: '2025-09-20', usablePixelPercent: 30 }),
      makeDate({ acquisitionDate: '2025-09-14', usablePixelPercent: 75 }),
      makeDate({ acquisitionDate: '2025-09-01', usablePixelPercent: 95 }),
    ];
    expect(selectDefaultDate(dates, 70)?.acquisitionDate).toBe('2025-09-14');
  });

  it('falls back to the newest date when none qualify', () => {
    const dates = [
      makeDate({ acquisitionDate: '2025-09-20', usablePixelPercent: 10 }),
      makeDate({ acquisitionDate: '2025-09-14', usablePixelPercent: 20 }),
    ];
    expect(selectDefaultDate(dates, 70)?.acquisitionDate).toBe('2025-09-20');
  });
});
