import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IngestionJobsList from '@/pages/monitoring/IngestionJobsList';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

const jobsPayload = {
  status: 'ok',
  generatedAt: '2026-06-25T00:00:00Z',
  nextCursor: null,
  jobs: [
    {
      jobId: 'job-abc123456789012345678',
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      aoiId: 'bangalore-60km',
      state: 'succeeded',
      windowStart: '2026-05-01',
      windowEnd: '2026-05-31',
      foundCount: 8,
      selectedCount: 6,
      downloadedCount: 5,
      rejectedCount: 2,
      failureKind: null,
      message: 'Ingestion completed successfully',
      startedAt: '2026-06-01T08:00:00Z',
      finishedAt: '2026-06-01T09:30:00Z',
      updatedAt: '2026-06-01T09:30:00Z',
    },
    {
      jobId: 'job-failed9876543210123',
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      aoiId: 'bangalore-60km',
      state: 'failed',
      windowStart: '2026-06-01',
      windowEnd: '2026-06-15',
      foundCount: 3,
      selectedCount: 2,
      downloadedCount: 0,
      rejectedCount: 1,
      failureKind: 'download_error',
      message: 'Scene download timed out',
      startedAt: '2026-06-10T10:00:00Z',
      finishedAt: '2026-06-10T10:15:00Z',
      updatedAt: '2026-06-10T10:15:00Z',
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter>
        <IngestionJobsList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('IngestionJobsList', () => {
  it('renders job ID (truncated), source, provider, AOI, state, window, counts, and latest message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobsPayload)));

    renderPage();

    // Wait for the data to load by checking the source ID column (fully rendered, not truncated)
    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Job ID link — link aria-label contains the full job ID
    const link = screen.getByRole('link', { name: /View job job-abc123456789012345678/ });
    expect(link).toBeTruthy();
    expect((link as HTMLAnchorElement).href).toContain(
      encodeURIComponent('job-abc123456789012345678'),
    );

    // Source / provider
    expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ISRO/NRSC').length).toBeGreaterThan(0);

    // AOI
    expect(screen.getAllByText('bangalore-60km').length).toBeGreaterThan(0);

    // State badge for canonical succeeded job
    expect(screen.getByText('succeeded')).toBeTruthy();
    // State badge for failed job
    expect(screen.getByText('failed')).toBeTruthy();

    // Window dates
    expect(screen.getByText('2026-05-01')).toBeTruthy();
    expect(screen.getByText('2026-06-01')).toBeTruthy();

    // Counts — numeric values in the job rows
    expect(screen.getAllByText('8').length).toBeGreaterThan(0); // foundCount for first job
    expect(screen.getAllByText('6').length).toBeGreaterThan(0); // selectedCount
    expect(screen.getAllByText('5').length).toBeGreaterThan(0); // downloadedCount
    expect(screen.getAllByText('2').length).toBeGreaterThan(0); // rejectedCount

    // Latest message
    expect(screen.getByText('Ingestion completed successfully')).toBeTruthy();

    // Failure kind for failed job
    expect(screen.getByText('download_error')).toBeTruthy();
  });

  it('links each job row to its detail page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobsPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    const detailLink = screen.getByRole('link', {
      name: /View job job-abc123456789012345678/,
    });
    expect((detailLink as HTMLAnchorElement).href).toContain(
      '/admin/ingestion/jobs/' + encodeURIComponent('job-abc123456789012345678'),
    );
  });

  it('shows an empty state message when no jobs match', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ ...jobsPayload, jobs: [] }),
      ),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText('No ingestion jobs match the current filters.')).toBeTruthy(),
    );
  });

  it('shows an error alert when the fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Unauthorized' }, 401)),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeTruthy(),
    );
    expect(screen.getByText(/Failed to load ingestion jobs/)).toBeTruthy();
  });

  it('calls the ingestion-jobs API endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(jobsPayload));
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    expect(
      fetchMock.mock.calls.some((call) =>
        String(call[0]).includes('/api/monitoring/ingestion-jobs'),
      ),
    ).toBe(true);
  });

  it('offers only canonical scheduler states in the state filter', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobsPayload)));

    renderPage();

    const stateSelect = screen.getByLabelText('Filter by job state');
    const options = within(stateSelect).getAllByRole('option') as HTMLOptionElement[];

    expect(options.map((option) => option.value)).toEqual([
      '',
      'planned',
      'queued',
      'running',
      'succeeded',
      'failed',
      'validation_failed',
      'blocked_by_lock',
      'cancelled',
      'skipped_not_due',
      'skipped_gated',
    ]);
    expect(options.map((option) => option.textContent)).toEqual([
      'All states',
      'Planned',
      'Queued',
      'Running',
      'Succeeded',
      'Failed',
      'Validation failed',
      'Blocked by lock',
      'Cancelled',
      'Skipped not due',
      'Skipped gated',
    ]);
    expect(options.some((option) => option.value === 'pending')).toBe(false);
    expect(options.some((option) => option.value === 'scheduled')).toBe(false);
  });

  it('sends the selected canonical scheduler state as the API filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(jobsPayload));
    vi.stubGlobal('fetch', fetchMock);

    renderPage();
    fireEvent.change(screen.getByLabelText('Filter by job state'), {
      target: { value: 'validation_failed' },
    });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) =>
          String(call[0]).includes('state=validation_failed'),
        ),
      ).toBe(true),
    );
  });

  it('maps canonical scheduler states to the planned badge color families', async () => {
    const canonicalJobs = [
      { state: 'planned', expectedClass: 'text-warning' },
      { state: 'queued', expectedClass: 'text-info' },
      { state: 'running', expectedClass: 'text-info' },
      { state: 'succeeded', expectedClass: 'text-success' },
      { state: 'failed', expectedClass: 'text-destructive' },
      { state: 'validation_failed', expectedClass: 'text-destructive' },
      { state: 'blocked_by_lock', expectedClass: 'text-warning' },
      { state: 'cancelled', expectedClass: 'text-destructive' },
      { state: 'skipped_not_due', expectedClass: 'text-warning' },
      { state: 'skipped_gated', expectedClass: 'text-warning' },
      { state: 'provider_paused', expectedClass: 'text-muted-foreground' },
    ].map(({ state }) => ({
      ...jobsPayload.jobs[0],
      jobId: `job-${state}`,
      state,
      message: `${state} message`,
    }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      jsonResponse({ ...jobsPayload, jobs: canonicalJobs }),
    ));

    renderPage();

    await waitFor(() =>
      expect(screen.getByText('provider_paused')).toBeTruthy(),
    );

    for (const { state, expectedClass } of [
      { state: 'planned', expectedClass: 'text-warning' },
      { state: 'queued', expectedClass: 'text-info' },
      { state: 'running', expectedClass: 'text-info' },
      { state: 'succeeded', expectedClass: 'text-success' },
      { state: 'failed', expectedClass: 'text-destructive' },
      { state: 'validation_failed', expectedClass: 'text-destructive' },
      { state: 'blocked_by_lock', expectedClass: 'text-warning' },
      { state: 'cancelled', expectedClass: 'text-destructive' },
      { state: 'skipped_not_due', expectedClass: 'text-warning' },
      { state: 'skipped_gated', expectedClass: 'text-warning' },
      { state: 'provider_paused', expectedClass: 'text-muted-foreground' },
    ]) {
      expect(screen.getByText(state).className).toContain(expectedClass);
    }
  });
});
