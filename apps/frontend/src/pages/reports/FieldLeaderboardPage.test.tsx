import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FieldLeaderboardPage from '@/pages/reports/FieldLeaderboardPage';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <FieldLeaderboardPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('FieldLeaderboardPage', () => {
  it('renders rows, truncation notice, filters, and CSV export', async () => {
    const blob = new Blob(['csv'], { type: 'text/csv' });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes('/export.csv')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Disposition': 'attachment; filename="leaderboard.csv"' }),
          blob: async () => blob,
        });
      }
      return Promise.resolve(
        jsonResponse({
          rows: [
            {
              plotId: 'plot-1',
              rank: 1,
              field: 'North Field',
              name: 'North Field',
              groupName: 'North',
              cropType: 'Paddy',
              location: '12.1000, 77.1000',
              areaHa: 5,
              latestIndexValue: 0.7,
              indexDelta: 0.1,
              weatherRiskLabel: 'Weather risk pending field weather aggregation',
              weatherRiskLevel: 'unknown',
              dataAvailable: true,
              latestImageDate: '2026-06-01',
              score: 0.82,
              preview: '/monitoring/field-analytics?field=plot-1',
              scoreComponents: {},
            },
          ],
          metadata: { truncated: true, evaluationLimit: 100 },
        }),
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:csv'), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    renderPage();

    await waitFor(() => expect(screen.getByText('North Field')).toBeTruthy());
    expect(screen.getByText(/Ranking computed for first 100 filtered fields/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/export.csv')),
      ).toBe(true),
    );
    fireEvent.change(screen.getByLabelText('crop Type'), { target: { value: 'Paddy' } });
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('cropType=Paddy')),
      ).toBe(true),
    );
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('api-connect');
  });
});
