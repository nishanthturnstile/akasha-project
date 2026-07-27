import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DiscoveryBrowser } from '@/components/discovery/DiscoveryBrowser';

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  fieldQuery: {
    data: {
      items: [],
      pinnedItems: [],
      appliedFilters: {
        seasonId: 'season-1',
        q: '',
        cropIds: [],
        groupIds: [],
        includeUngrouped: false,
        sort: 'name_asc',
        page: 1,
        pageSize: 20,
      },
      page: 1,
      pageSize: 20,
      total: 0,
      totalPages: 0,
      resultBounds: null,
    },
    isLoading: false,
    isFetching: true,
    error: null,
    refetch: vi.fn(),
  },
}));

vi.mock('@/hooks/useDiscoveryUrlState', () => ({
  useDiscoveryUrlState: () => ({
    filters: {
      seasonId: 'season-1',
      q: '',
      cropIds: [],
      groupIds: ['newly-applied-group'],
      includeUngrouped: false,
      sort: 'name_asc',
      page: 1,
      pageSize: 20,
    },
    update: mocks.update,
  }),
}));

vi.mock('@/lib/queries', () => ({
  useFieldDiscovery: () => mocks.fieldQuery,
  useFieldDiscoveryFacets: () => ({
    data: { crops: [], groups: [], hasUngrouped: false },
    error: null,
  }),
  useScoutTaskDiscovery: () => ({
    data: undefined,
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
  useUpdateScoutTask: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useField: () => ({ data: undefined, isLoading: false }),
  useUpdateField: () => ({ mutate: vi.fn() }),
  useDeleteField: () => ({ mutateAsync: vi.fn() }),
}));

// Real EditFieldDialog transitively pulls in MapLibre-dependent map components;
// stub it like MapPage.test.tsx stubs MapLayerManager to keep this test isolated.
vi.mock('@/components/seasons/EditFieldDialog', () => ({
  default: () => null,
}));

vi.mock('@/state/useMapView', () => ({
  useMapView: () => ({
    selectedPlotId: null,
    focusNonce: 0,
    setSelectedPlotId: vi.fn(),
    setFocusNonce: vi.fn(),
    setGlobalViewOpen: vi.fn(),
    setOverlaysVisible: vi.fn(),
  }),
}));

describe('DiscoveryBrowser saved-filter normalization', () => {
  beforeEach(() => {
    mocks.update.mockClear();
    mocks.fieldQuery.isFetching = true;
  });

  it('does not normalize freshly applied filters from previous data while refetching', async () => {
    const view = render(
      <MemoryRouter>
        <DiscoveryBrowser target="monitoring" seasonId="season-1" />
      </MemoryRouter>,
    );

    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(mocks.update).not.toHaveBeenCalled();

    mocks.fieldQuery.isFetching = false;
    view.rerender(
      <MemoryRouter>
        <DiscoveryBrowser target="monitoring" seasonId="season-1" />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith({
      cropIds: [],
      groupIds: [],
      includeUngrouped: false,
    }));
  });

  it('explains that scouting search uses the task field name', () => {
    render(
      <MemoryRouter>
        <DiscoveryBrowser target="scouting" seasonId="season-1" />
      </MemoryRouter>,
    );

    expect(screen.getByPlaceholderText('Search tasks by field name')).toBeTruthy();
  });
});
