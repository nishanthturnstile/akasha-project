import { describe, expect, it } from 'vitest';

import { modeLabel } from './displayMode';

describe('modeLabel', () => {
    it('labels compatible SAR grayscale route token as generic backscatter', () => {
        expect(modeLabel('VV_GRAYSCALE')).toBe('Backscatter');
    });
});
