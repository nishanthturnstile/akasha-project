import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DiseasesPestsPage from '@/pages/risk/DiseasesPestsPage';
import { MemoryRouter } from 'react-router-dom';
import { MapViewProvider, type MapViewState } from '@/state/mapViewContext';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

function renderPage(initialState?: Partial<MapViewState>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter>
        <MapViewProvider initialState={ initialState }>
          <DiseasesPestsPage />
        </MapViewProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DiseasesPestsPage', () => {
  it('renders selected-field empty state without calling risk API', () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    expect(screen.getByText(/Select a field/)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/risk/summary'),
      expect.anything(),
    );
  });

  it('renders non-diagnostic field-watch context for selected field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === '/api/plots') {
          return Promise.resolve(jsonResponse([{ id: 'plot-1', name: 'North Field' }]));
        }
        return Promise.resolve(
          jsonResponse({
            plotId: 'plot-1',
            fieldWatchLevel: 'high',
            vegetationStressContext: 'Scouting priority context. not a disease or pest diagnostic model.',
            score: 0.8,
            cropStage: {
              cropType: 'Paddy',
              startDateType: 'sowingDate',
              stageLabel: 'vegetative',
              daysAfterStart: 30,
              modelVersion: 'generic-v1',
              limitations: [],
            },
            components: [
              {
                id: 'vegetationCondition',
                label: 'Vegetation condition',
                available: true,
                level: 'high',
                score: 0.8,
                weight: 0.35,
                usedInAggregate: true,
                evidence: ['Latest NDVI value is low.'],
                limitations: ['Not diagnosis.'],
                source: 'akasha',
              },
            ],
            limitations: ['High means prioritize field scouting; it does not indicate disease or pest presence.'],
            metadata: {},
          }),
        );
      }),
    );

    renderPage({ selectedPlotId: 'plot-1' });

    await waitFor(() => expect(screen.getByText('Selected field: North Field')).toBeTruthy());
    expect(screen.getAllByText(/not a disease or pest diagnostic model/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Field watch priority/)).toBeTruthy();
    expect(screen.getByText(/vegetative/)).toBeTruthy();
    expect(document.body.textContent?.toLowerCase()).not.toContain('spray');
    expect(document.body.textContent?.toLowerCase()).not.toContain('detected');
  });
});
