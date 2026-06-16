import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MonitoringGlobalView from '@/pages/monitoring/MonitoringGlobalView';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

const monitoringPayload = {
  generatedAt: '2026-06-16T12:00:00Z',
  staleAfterDays: 30,
  sources: [
    {
      sourceId: 'resourcesat-2a-liss3-boa',
      label: 'ResourceSat LISS-3',
      provider: 'ISRO/NRSC',
      kind: 'optical',
      availabilityStatus: 'active',
      analysisLevel: 'field',
      refreshPolicy: 'scheduled',
      latestAvailableDate: '2026-06-01',
      latestUsableDate: '2026-06-01',
      daysSinceLatestAvailable: 15,
      staleAfterDays: 30,
      isStale: false,
      dateCount: 4,
      tileAvailableDateCount: 3,
      coveragePercent: 98.2,
      usablePixelPercent: 82.5,
      cloudMaskedPercent: 12.1,
      metricsProvisional: true,
      warnings: ['LATEST_SUCCESSFUL_COMPOSITE_STALE'],
      tileUnavailableReasons: ['Missing mask asset'],
      latestSuccessfulCompositeDate: '2026-05-01',
      latestSuccessfulCompositeProductId: 'composite:bangalore-60km:2026-05-01',
      latestSuccessfulCompositeAoiId: 'bangalore-60km',
      latestSuccessfulCompositeUpdatedAt: '2026-05-02T01:00:00Z',
      latestSuccessfulComposites: [
        {
          aoiId: 'bangalore-60km',
          date: '2026-05-01',
          productId: 'composite:bangalore-60km:2026-05-01',
          updatedAt: '2026-05-02T01:00:00Z',
        },
      ],
      daysSinceLatestSuccessfulComposite: 46,
      isSuccessfulCompositeStale: true,
    },
    {
      sourceId: 'cartosat-3-gated',
      label: 'Cartosat-3 gated',
      provider: 'ISRO/NRSC',
      kind: 'context',
      availabilityStatus: 'gated',
      analysisLevel: 'context',
      refreshPolicy: 'manual',
      latestAvailableDate: null,
      latestUsableDate: null,
      daysSinceLatestAvailable: null,
      staleAfterDays: 30,
      isStale: false,
      dateCount: 0,
      tileAvailableDateCount: 0,
      coveragePercent: null,
      usablePixelPercent: null,
      cloudMaskedPercent: null,
      metricsProvisional: false,
      gatedReason: 'Manual order workflow only',
      warnings: ['SOURCE_GATED'],
      tileUnavailableReasons: [],
      latestSuccessfulComposites: [],
      daysSinceLatestSuccessfulComposite: null,
      isSuccessfulCompositeStale: false,
    },
  ],
  storage: {
    status: 'ok',
    bucket: 'akasha-cogs',
    objectCount: 5,
    bytes: 10485760,
    zeroByteObjectCount: 1,
    byPrefix: [
      {
        prefix: 'resourcesat-2a-liss3-boa',
        objectCount: 4,
        bytes: 10485760,
        zeroByteObjectCount: 1,
      },
    ],
  },
  ingestionLedger: {
    status: 'ok',
    path: '/srv/akasha/ingestion/ledger.sqlite',
    rowCount: 4,
    statusCounts: { failed: 1, composited: 1 },
    bytes: 10485760,
    lastUpdatedAt: '2026-06-16T10:00:00Z',
    failureCountsByKind: { storage_upload: 1 },
    lastFailures: [
      {
        productId: 'composite:bangalore-60km:2026-06-01',
        sourceId: 'resourcesat-2a-liss3-boa',
        sceneKey: null,
        status: 'failed',
        retries: 1,
        bytes: 0,
        updatedAt: '2026-06-16T10:00:00Z',
        failureKind: 'storage_upload',
        error: 'storage upload failed: MinIO PutObject failed',
      },
    ],
    bySource: [],
  },
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MonitoringGlobalView />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MonitoringGlobalView', () => {
  it('renders source freshness, storage, and recent ingestion failures', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      void input;
      return Promise.resolve(jsonResponse(monitoringPayload));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    await waitFor(() => expect(screen.getByText('ResourceSat LISS-3')).toBeTruthy());
    expect(screen.getByText('stale composite')).toBeTruthy();
    expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0);
    expect(screen.getByText('storage_upload')).toBeTruthy();
    expect(screen.getByText('1 zero-byte object(s)')).toBeTruthy();
    expect(screen.getByText(/Missing mask asset/)).toBeTruthy();
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]) === '/api/monitoring/imagery-sources'),
    ).toBe(true);
  });

  it('refetches the operator payload when refreshed', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      void input;
      return Promise.resolve(jsonResponse(monitoringPayload));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    await waitFor(() => expect(screen.getByText('ResourceSat LISS-3')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
