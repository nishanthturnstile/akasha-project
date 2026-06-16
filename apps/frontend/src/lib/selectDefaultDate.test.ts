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

  it('does not depend on the API returning dates newest-first', () => {
    const dates = [
      makeDate({ acquisitionDate: '2025-09-01', usablePixelPercent: 95 }),
      makeDate({ acquisitionDate: '2025-09-20', usablePixelPercent: 30 }),
      makeDate({ acquisitionDate: '2025-09-14', usablePixelPercent: 75 }),
    ];
    expect(selectDefaultDate(dates, 70)?.acquisitionDate).toBe('2025-09-14');
  });

  it('selects the latest SAR radar pass without usablePixelPercent', () => {
    const dates = [
      makeDate({ acquisitionDate: '2026-04-24', usablePixelPercent: null }),
      makeDate({ acquisitionDate: '2026-04-29', usablePixelPercent: null }),
      makeDate({
        acquisitionDate: '2026-05-01',
        usablePixelPercent: null,
        tileAvailable: false,
      }),
    ];

    expect(selectDefaultDate(dates, 70, { sourceKind: 'sar' })?.acquisitionDate).toBe(
      '2026-04-29',
    );
  });

  it('selects the latest context date without usablePixelPercent', () => {
    const dates = [
      makeDate({ acquisitionDate: '2026-04-08', usablePixelPercent: null }),
      makeDate({ acquisitionDate: '2026-04-16', usablePixelPercent: null }),
    ];

    expect(selectDefaultDate(dates, 70, { sourceKind: 'context' })?.acquisitionDate).toBe(
      '2026-04-16',
    );
  });
});
