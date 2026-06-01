import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { CloudUsabilityChip } from '@/components/layers/CloudUsabilityChip';
import type { SourceKind } from '@/types/api';

function renderChip(percent: number | null, sourceKind?: SourceKind, coveragePercent?: number | null) {
  return render(
    <TooltipProvider>
      <CloudUsabilityChip
        percent={percent}
        sourceKind={sourceKind}
        coveragePercent={coveragePercent}
      />
    </TooltipProvider>,
  );
}

describe('CloudUsabilityChip', () => {
  it('renders success status at >=70%', () => {
    const { getByTestId } = renderChip(82);
    expect(getByTestId('cloud-usability-chip').getAttribute('data-status')).toBe('success');
  });

  it('renders warning status between 40 and 70', () => {
    const { getByTestId } = renderChip(55);
    expect(getByTestId('cloud-usability-chip').getAttribute('data-status')).toBe('warning');
  });

  it('renders destructive status below 40', () => {
    const { getByTestId } = renderChip(12);
    expect(getByTestId('cloud-usability-chip').getAttribute('data-status')).toBe('destructive');
  });

  it('renders nodata status when the percentage is missing', () => {
    const { getByTestId } = renderChip(null);
    const chip = getByTestId('cloud-usability-chip');
    expect(chip.getAttribute('data-status')).toBe('nodata');
    expect(chip.textContent).toContain('No data');
  });

  it('renders SAR-safe radar pass copy without cloud or usable wording', () => {
    const { getByTestId, queryByTestId } = renderChip(null, 'sar', null);
    const chip = getByTestId('radar-coverage-chip');
    expect(queryByTestId('cloud-usability-chip')).toBeNull();
    expect(chip.textContent).toContain('Radar pass');
    expect(chip.textContent).not.toMatch(/cloud|usable/i);
  });
});
