import { describe, expect, it } from 'vitest';

import { radarEvidenceDescription, radarSensorLabel } from './radarEvidence';

describe('radar evidence copy', () => {
  it('identifies NISAR as S-band and includes the displayed polarization', () => {
    expect(radarSensorLabel('nisar-ssar-beta-gcov')).toBe('NISAR S-band');
    const copy = radarEvidenceDescription('nisar-ssar-beta-gcov', '2026-07-18', 'HH');
    expect(copy).toContain('NISAR S-band radar evidence');
    expect(copy).toContain('using HH');
    expect(copy).toContain('not NDVI or a direct soil-moisture measurement');
  });

  it('preserves the EOS-04 sensor label', () => {
    expect(radarSensorLabel('eos-04-sar-mrs-l2b')).toBe('EOS-04');
  });
});
