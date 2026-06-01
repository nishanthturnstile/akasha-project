import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { DateList } from '@/components/layers/DateList';
import type { SceneDate } from '@/types/api';

function makeDate(partial: Partial<SceneDate>): SceneDate {
  return {
    acquisitionDate: '2026-04-26',
    datetime: '2026-04-26T00:00:00Z',
    usablePixelPercent: null,
    cloudMaskedPercent: null,
    coveragePercent: null,
    isLatestUsable: true,
    metricsProvisional: false,
    tileAvailable: true,
    ...partial,
  };
}

describe('DateList', () => {
  it('uses radar-pass wording for SAR rows without cloud or usable copy', () => {
    const { container, getByTestId, queryByTestId } = render(
      <TooltipProvider>
        <DateList
          dates={[makeDate({ coveragePercent: null })]}
          selectedDate="2026-04-26"
          onSelect={vi.fn()}
          loading={false}
          error={null}
          onRetry={vi.fn()}
          sourceKind="sar"
        />
      </TooltipProvider>,
    );

    expect(getByTestId('radar-coverage-chip').textContent).toContain('Radar pass');
    expect(queryByTestId('cloud-usability-chip')).toBeNull();
    expect(container.textContent).not.toMatch(/cloud|usable/i);
  });
});
