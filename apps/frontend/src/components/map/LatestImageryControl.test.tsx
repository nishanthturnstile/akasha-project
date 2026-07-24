import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LatestImageryControl } from '@/components/map/LatestImageryControl';
import { searchLatestImagery } from '@/lib/api';
import type { LatestImageryPolicy, SceneCandidate } from '@/types/api';

vi.mock('@/lib/api', () => ({ searchLatestImagery: vi.fn() }));

const policy: LatestImageryPolicy = {
  policyVersion: 'latest-image-s2-l2a-v1',
  sourceId: 'sentinel-2-l2a',
  processingLevel: 'L2A',
  lookbackDays: 365,
  maxCloudPercent: 10,
  maxViewportDiagonalMeters: 2_000,
  resultLimit: 24,
  entitled: true,
};

function mapMock(span = 0.005) {
  const listeners = new Map<string, () => void>();
  return {
    getBounds: () => ({
      getWest: () => 77,
      getEast: () => 77 + span,
      getSouth: () => 12,
      getNorth: () => 12 + span,
    }),
    on: vi.fn((name: string, handler: () => void) => listeners.set(name, handler)),
    off: vi.fn(),
    getCanvas: () => ({ focus: vi.fn() }),
    listeners,
  };
}

const candidate = (overrides: Partial<SceneCandidate> = {}): SceneCandidate => ({
  sceneId: 'scene-new',
  acquisitionDate: '2026-07-20',
  acquisitionDatetime: '2026-07-20T10:00:00Z',
  sourceId: 'sentinel-2-l2a',
  sensor: 'Sentinel-2',
  processingLevel: 'L2A',
  cloudPercent: 3,
  coveragePercent: 100,
  coverageStatus: 'full',
  usable: true,
  bounds: [77, 12, 77.01, 12.01],
  tileUrlTemplate: '/api/imagery/scenes/scene-new/tiles/{z}/{x}/{y}.png',
  thumbnailUrl: '/api/imagery/scenes/scene-new/thumbnail.png',
  ...overrides,
});

describe('LatestImageryControl', () => {
  it('snapshots the viewport only on explicit search and selects the newest usable scene', async () => {
    const map = mapMock();
    const onSelectedChange = vi.fn();
    vi.mocked(searchLatestImagery).mockResolvedValue({
      policyVersion: policy.policyVersion,
      searchedAt: '2026-07-22T00:00:00Z',
      viewportDiagonalMeters: 777,
      candidates: [
        candidate({
          sceneId: 'scene-partial',
          acquisitionDate: '2026-07-22',
          acquisitionDatetime: '2026-07-22T10:00:00Z',
          usable: false,
          coverageStatus: 'partial',
          coveragePercent: 70,
          unavailableReason: 'Scene does not fully cover the searched viewport.',
        }),
        candidate({
          sceneId: 'scene-old',
          acquisitionDate: '2026-07-18',
          acquisitionDatetime: '2026-07-18T10:00:00Z',
        }),
        candidate(),
      ],
    });

    render(
      <LatestImageryControl
        map={ map as never }
        policy={ policy }
        mode="latest"
        onModeChange={ vi.fn() }
        selected={ null }
        onSelectedChange={ onSelectedChange }
      />,
    );

    expect(searchLatestImagery).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Search this area' }));

    await waitFor(() => expect(onSelectedChange).toHaveBeenCalledWith(expect.objectContaining({ sceneId: 'scene-new' })));
    expect(screen.queryByText(/Map moved/)).toBeNull();
    expect(searchLatestImagery).toHaveBeenCalledWith(
      {
        type: 'Polygon',
        coordinates: [[[77, 12], [77.005, 12], [77.005, 12.005], [77, 12.005], [77, 12]]],
      },
      expect.any(AbortSignal),
    );
    expect(screen.getByRole('button', { name: '2026-07-22' }).hasAttribute('disabled')).toBe(true);

    act(() => map.listeners.get('moveend')?.());
    expect(await screen.findByText(/Map moved/)).toBeTruthy();
  });

  it('disables search when the viewport exceeds the configured 2 km diagonal', () => {
    render(
      <LatestImageryControl
        map={ mapMock(0.05) as never }
        policy={ policy }
        mode="latest"
        onModeChange={ vi.fn() }
        selected={ null }
        onSelectedChange={ vi.fn() }
      />,
    );

    expect(screen.getByRole('button', { name: 'Search this area' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/Zoom in/)).toBeTruthy();
  });

  it('explains why search is unavailable when the account is not entitled', () => {
    render(
      <LatestImageryControl
        map={ mapMock() as never }
        policy={ { ...policy, entitled: false } }
        mode="latest"
        onModeChange={ vi.fn() }
        selected={ null }
        onSelectedChange={ vi.fn() }
      />,
    );

    expect(screen.getByRole('button', { name: 'Search this area' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByText(/not available for this account/)).toBeTruthy();
  });
});
