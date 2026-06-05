import { describe, expect, it } from 'vitest';
import { usabilityStatus } from '@/lib/usability';

describe('usabilityStatus (cloud usability chip mapping)', () => {
  it('maps >=70% to success', () => {
    expect(usabilityStatus(70)).toBe('success');
    expect(usabilityStatus(82.85)).toBe('success');
    expect(usabilityStatus(100)).toBe('success');
  });

  it('maps 40-70% to warning', () => {
    expect(usabilityStatus(40)).toBe('warning');
    expect(usabilityStatus(55)).toBe('warning');
    expect(usabilityStatus(69.99)).toBe('warning');
  });

  it('maps <40% to destructive', () => {
    expect(usabilityStatus(39.99)).toBe('destructive');
    expect(usabilityStatus(12)).toBe('destructive');
    expect(usabilityStatus(0)).toBe('destructive');
  });

  it('maps missing/NaN to nodata', () => {
    expect(usabilityStatus(null)).toBe('nodata');
    expect(usabilityStatus(undefined)).toBe('nodata');
    expect(usabilityStatus(Number.NaN)).toBe('nodata');
  });
});
