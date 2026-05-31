import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { CloudUsabilityChip } from '@/components/layers/CloudUsabilityChip';

function renderChip(percent: number | null) {
  return render(
    <TooltipProvider>
      <CloudUsabilityChip percent={percent} />
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
});
