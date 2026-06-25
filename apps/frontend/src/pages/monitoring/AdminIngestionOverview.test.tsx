import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AdminIngestionOverview from '@/pages/monitoring/AdminIngestionOverview';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

const imagerySourcesPayload = {
  generatedAt: '2026-06-25T08:00:00Z',
  status: 'warning',
  statusReasons: [],
  staleAfterDays: 10,
  coverageThresholdPercent: 80,
  usablePixelThresholdPercent: 70,
  storage: {
    status: 'ok',
    objectCount: 12,
    bytes: 4096,
    byPrefix: [],
  },
  ingestionLedger: {
    status: 'ok',
    statusCounts: {},
    failureCountsByKind: {},
    lastFailures: [],
    bySource: [],
  },
  sources: [
    {
      sourceId: 'resourcesat-2a-liss3-boa',
      status: 'ok',
      statusReasons: [],
      availabilityStatus: 'active',
      staleAfterDays: 10,
      isStale: false,
      dateCount: 3,
      tileAvailableDateCount: 3,
      metricsProvisional: false,
      warnings: [],
      tileUnavailableReasons: [],
      isSuccessfulCompositeStale: false,
      isSuccessfulSearchStale: false,
      isUpstreamDataStale: false,
      ingestionFailureCountsByKind: {},
      hasUnresolvedIngestionFailure: false,
    },
    {
      sourceId: 'resourcesat-gated',
      status: 'ok',
      statusReasons: [],
      availabilityStatus: 'gated',
      staleAfterDays: 10,
      isStale: false,
      dateCount: 0,
      tileAvailableDateCount: 0,
      metricsProvisional: false,
      warnings: [],
      tileUnavailableReasons: [],
      isSuccessfulCompositeStale: false,
      isSuccessfulSearchStale: false,
      isUpstreamDataStale: false,
      ingestionFailureCountsByKind: {},
      hasUnresolvedIngestionFailure: false,
    },
    {
      sourceId: 'resourcesat-warning',
      status: 'warning',
      statusReasons: ['successful composite stale'],
      availabilityStatus: 'active',
      staleAfterDays: 10,
      isStale: true,
      dateCount: 1,
      tileAvailableDateCount: 1,
      metricsProvisional: false,
      warnings: ['successful composite stale'],
      tileUnavailableReasons: [],
      isSuccessfulCompositeStale: true,
      isSuccessfulSearchStale: false,
      isUpstreamDataStale: false,
      ingestionFailureCountsByKind: {},
      hasUnresolvedIngestionFailure: false,
    },
  ],
};

const schedulesPayload = {
  status: 'ok',
  generatedAt: '2026-06-25T08:15:00Z',
  lastError: null,
  schedules: [
    {
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      adapter: 'bhoonidhi',
      aoiId: 'bangalore-60km',
      lifecycleState: 'active',
      scheduleState: 'enabled',
      capabilities: ['search', 'download'],
      scheduleEnabled: true,
      nextDueAt: '2026-06-25T10:00:00Z',
      cadenceDays: 15,
      isDue: true,
      isOverdue: false,
    },
    {
      sourceId: 'resourcesat-overdue',
      provider: 'ISRO/NRSC',
      adapter: 'bhoonidhi',
      aoiId: 'bangalore-60km',
      lifecycleState: 'active',
      scheduleState: 'enabled',
      capabilities: ['search'],
      scheduleEnabled: true,
      nextDueAt: '2026-06-24T10:00:00Z',
      cadenceDays: 15,
      isDue: true,
      isOverdue: true,
    },
  ],
};

const jobsPayload = {
  status: 'ok',
  generatedAt: '2026-06-25T08:30:00Z',
  nextCursor: null,
  lastError: null,
  jobs: [
    {
      jobId: 'job-success-001',
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      aoiId: 'bangalore-60km',
      state: 'succeeded',
      startedAt: '2026-06-24T06:00:00Z',
      finishedAt: '2026-06-24T06:40:00Z',
      updatedAt: '2026-06-24T06:40:00Z',
    },
    {
      jobId: 'job-failed-001',
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      aoiId: 'bangalore-60km',
      state: 'failed',
      failureKind: 'download_error',
      message: 'Download timed out',
      startedAt: '2026-06-25T07:00:00Z',
      finishedAt: '2026-06-25T07:10:00Z',
      updatedAt: '2026-06-25T07:10:00Z',
    },
    {
      jobId: 'job-validation-failed-001',
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      aoiId: 'bangalore-60km',
      state: 'validation_failed',
      startedAt: '2026-06-23T07:00:00Z',
      finishedAt: '2026-06-23T07:10:00Z',
      updatedAt: '2026-06-23T07:10:00Z',
    },
  ],
};

function createOverviewFetchMock(
  overrides: {
    sources?: unknown;
    schedules?: unknown;
    jobs?: unknown;
    statusByPath?: Record<string, number>;
  } = {},
) {
  return vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    const status = overrides.statusByPath?.[path] ?? 200;
    if (path === '/api/monitoring/imagery-sources') {
      return Promise.resolve(jsonResponse(overrides.sources ?? imagerySourcesPayload, status));
    }
    if (path === '/api/monitoring/ingestion-schedules') {
      return Promise.resolve(jsonResponse(overrides.schedules ?? schedulesPayload, status));
    }
    if (path.startsWith('/api/monitoring/ingestion-jobs')) {
      return Promise.resolve(jsonResponse(overrides.jobs ?? jobsPayload, status));
    }
    return Promise.resolve(jsonResponse({ error: { code: 'UNEXPECTED_TEST_REQUEST', message: path } }, 500));
  });
}

function renderOverview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter>
        <AdminIngestionOverview />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminIngestionOverview', () => {
  it('renders the six high-level overview cards from scheduler, job, and source health data', async () => {
    vi.stubGlobal('fetch', createOverviewFetchMock());

    renderOverview();

    await waitFor(() => expect(screen.getByText('Generated 2026-06-25 08:15')).toBeTruthy());

    expect(screen.getByLabelText('Scheduler status')).toBeTruthy();
    expect(screen.getAllByText('ok').length).toBeGreaterThan(0);

    expect(screen.getByLabelText('Due / overdue')).toBeTruthy();
    expect(screen.getByText('1 due · 1 overdue')).toBeTruthy();

    expect(screen.getByLabelText('Failed jobs')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();

    expect(screen.getByLabelText('Latest successful job')).toBeTruthy();
    expect(screen.getByText('2026-06-24 06:40 · bangalore-60km')).toBeTruthy();

    expect(screen.getByLabelText('Latest failed job')).toBeTruthy();
    expect(screen.getByText('2026-06-25 07:10 · bangalore-60km')).toBeTruthy();

    expect(screen.getByLabelText('Source health')).toBeTruthy();
    expect(screen.getByText('1 need attention')).toBeTruthy();
    expect(screen.getByText('2 active · 1 gated')).toBeTruthy();
  });

  it('links overview actions to canonical admin schedules, jobs, and latest job detail routes', async () => {
    vi.stubGlobal('fetch', createOverviewFetchMock());

    renderOverview();

    await waitFor(() => expect(screen.getByText('2026-06-25 07:10 · bangalore-60km')).toBeTruthy());

    const scheduleLinks = screen.getAllByRole('link').filter((link) =>
      (link as HTMLAnchorElement).href.includes('/admin/ingestion/schedules'),
    );
    const jobLinks = screen.getAllByRole('link').filter((link) =>
      (link as HTMLAnchorElement).href.includes('/admin/ingestion/jobs'),
    );

    expect(scheduleLinks.length).toBeGreaterThanOrEqual(2);
    expect(jobLinks.length).toBeGreaterThanOrEqual(3);
    expect(
      jobLinks.some((link) =>
        (link as HTMLAnchorElement).href.includes('/admin/ingestion/jobs/job-success-001'),
      ),
    ).toBe(true);
    expect(
      jobLinks.some((link) =>
        (link as HTMLAnchorElement).href.includes('/admin/ingestion/jobs/job-failed-001'),
      ),
    ).toBe(true);
  });

  it('shows loading, error, and unconfigured states without hiding the overview cards', async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise((resolve) => {
        resolveFetch = resolve;
      })),
    );

    const view = renderOverview();
    expect(screen.getByLabelText('Loading ingestion overview')).toBeTruthy();
    view.unmount();
    resolveFetch(jsonResponse(schedulesPayload));

    vi.stubGlobal(
      'fetch',
      createOverviewFetchMock({
        schedules: {
          ...schedulesPayload,
          status: 'unconfigured',
          lastError: 'scheduler config missing',
          schedules: [],
        },
        jobs: {
          ...jobsPayload,
          status: 'unavailable',
          lastError: 'ledger unavailable',
          jobs: [],
        },
        statusByPath: {
          '/api/monitoring/imagery-sources': 500,
        },
      }),
    );

    renderOverview();

    await waitFor(() =>
      expect(screen.getByText('The ingestion scheduler is not configured for this environment yet.')).toBeTruthy(),
    );
    expect(screen.getByText(/Scheduler overview is available with a warning/)).toBeTruthy();
    expect(screen.getByText(/Job overview is available with a warning/)).toBeTruthy();
    expect(screen.queryByText('scheduler config missing')).toBeNull();
    expect(screen.queryByText('ledger unavailable')).toBeNull();
    expect(screen.getByText('Imagery source health could not be loaded.')).toBeTruthy();
    expect(screen.getByLabelText('Scheduler status')).toBeTruthy();
  });

  it('requests the distinct admin monitoring endpoints used by the overview', async () => {
    const fetchMock = createOverviewFetchMock();
    vi.stubGlobal('fetch', fetchMock);

    renderOverview();

    await waitFor(() => expect(screen.getByLabelText('Source health')).toBeTruthy());

    const requestedPaths = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(requestedPaths).toContain('/api/monitoring/imagery-sources');
    expect(requestedPaths).toContain('/api/monitoring/ingestion-schedules');
    expect(requestedPaths).toContain('/api/monitoring/ingestion-jobs?limit=50');
  });
});
