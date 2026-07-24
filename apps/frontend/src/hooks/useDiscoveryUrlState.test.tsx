import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { useDiscoveryUrlState } from '@/hooks/useDiscoveryUrlState';

function Probe({ namespace }: { namespace: 'monitoring' | 'scouting' }) {
  const state = useDiscoveryUrlState(namespace, 'season-1', 'new');
  const location = useLocation();
  return (
    <>
      <output data-testid="filters">{JSON.stringify(state.filters)}</output>
      <output data-testid="search">{location.search}</output>
      <button
        type="button"
        onClick={() => state.update({ cropIds: [2, 3], includeUngrouped: true })}
      >
        Apply
      </button>
      <button type="button" onClick={() => state.update({ page: 4 }, { keepPage: true })}>
        Page
      </button>
    </>
  );
}

describe('useDiscoveryUrlState', () => {
  it('round-trips repeated values and preserves parameters owned by other modules', () => {
    render(
      <MemoryRouter initialEntries={[
        '/monitoring?monQ=North&monCrop=1&monPage=3&scoutQ=South&source=s2',
      ]}>
        <Probe namespace="monitoring" />
      </MemoryRouter>,
    );

    expect(JSON.parse(screen.getByTestId('filters').textContent ?? '{}')).toMatchObject({
      q: 'North',
      cropIds: [1],
      page: 3,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    const updated = new URLSearchParams(screen.getByTestId('search').textContent ?? '');
    expect(updated.getAll('monCrop')).toEqual(['2', '3']);
    expect(updated.get('monUngrouped')).toBe('1');
    expect(updated.has('monPage')).toBe(false);
    expect(updated.get('scoutQ')).toBe('South');
    expect(updated.get('source')).toBe('s2');
  });

  it('uses an independent scouting namespace and retains page-only navigation', () => {
    render(
      <MemoryRouter initialEntries={['/scout-tasks?monQ=North&scoutStatus=closed']}>
        <Probe namespace="scouting" />
      </MemoryRouter>,
    );
    expect(JSON.parse(screen.getByTestId('filters').textContent ?? '{}')).toMatchObject({
      q: '',
      status: 'closed',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Page' }));
    const updated = new URLSearchParams(screen.getByTestId('search').textContent ?? '');
    expect(updated.get('scoutPage')).toBe('4');
    expect(updated.get('monQ')).toBe('North');
  });
});
