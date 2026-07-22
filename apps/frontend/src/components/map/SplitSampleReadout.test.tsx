import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SplitSampleReadout } from '@/components/map/SplitSampleReadout';
import { sampleFieldComparison } from '@/lib/api';
import type { ViewerSelection } from '@/types/api';

vi.mock('@/lib/api', () => ({ sampleFieldComparison: vi.fn() }));

function mapMock(xOffset: number) {
  const handlers = new Map<string, (event: unknown) => void>();
  const container = document.createElement('div');
  container.style.position = 'relative';
  Object.defineProperty(container, 'clientWidth', { value: 500 });
  Object.defineProperty(container, 'clientHeight', { value: 400 });
  document.body.appendChild(container);
  return {
    map: {
      getContainer: () => container,
      project: () => ({ x: 120 + xOffset, y: 140 }),
      on: vi.fn((name: string, handler: (event: unknown) => void) => handlers.set(name, handler)),
      off: vi.fn(),
    },
    handlers,
    container,
  };
}

const selection = (indexType: string): ViewerSelection => ({
  sourceId: 'sentinel-2-l2a',
  acquisitionDate: '2026-05-12',
  indexType,
  cloudMask: { clouds: true, cloudShadows: true, cirrus: true },
  renderProfile: 'standard',
  preferHighRes: true,
});

afterEach(() => document.body.replaceChildren());

describe('SplitSampleReadout', () => {
  it('shows an independent hover popover in both synchronized viewers', async () => {
    const left = mapMock(0);
    const right = mapMock(20);
    vi.mocked(sampleFieldComparison).mockResolvedValue({
      left: { status: 'ok', value: 0.713, category: 4, masked: false, maskClass: null },
      right: { status: 'error', value: null, category: null, masked: false, maskClass: null, error: 'Scene unavailable' },
    });

    render(
      <SplitSampleReadout
        leftMap={ left.map as never }
        rightMap={ right.map as never }
        plotId="field-1"
        left={ selection('NDVI') }
        right={ selection('NDMI') }
      />,
    );

    act(() => left.handlers.get('mousemove')?.({ lngLat: { lng: 77.59, lat: 12.97 } }));

    expect(screen.getByTestId('left-sample-popover').textContent).toContain('NDVI · 2026-05-12');
    expect(screen.getByTestId('right-sample-popover').textContent).toContain('NDMI · 2026-05-12');
    await waitFor(() => expect(screen.getByTestId('left-sample-popover').textContent).toContain('0.713'));
    expect(screen.getByTestId('right-sample-popover').textContent).toContain('Scene unavailable');
    expect(left.container.querySelectorAll('div').length).toBeGreaterThan(1);
    expect(right.container.querySelectorAll('div').length).toBeGreaterThan(1);
  });
});
