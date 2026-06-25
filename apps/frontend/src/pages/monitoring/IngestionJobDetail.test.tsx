import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IngestionJobDetail from '@/pages/monitoring/IngestionJobDetail';

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

/** A complete IngestionJobDetail fixture that exercises all tabs and sections. */
const jobDetailPayload = {
  jobId: 'job-abc123456789012345678',
  sourceId: 'resourcesat-2a-liss3-boa',
  provider: 'ISRO/NRSC',
  aoiId: 'bangalore-60km',
  state: 'failed',
  request: {
    aoi: 'bangalore-60km',
    windowStart: '2026-05-01',
    windowEnd: '2026-05-31',
  },
  providerInputSummary: {
    endpoint: 'bhoonidhi-api',
    queryParams: 'Online=Y,sensor=LISS3',
  },
  providerResponseSummary: {
    totalFound: 8,
    selected: 6,
  },
  searchManifestHandle: 'resourcesat-2a-liss3-boa/search/2026-05-01/bangalore-60km.json',
  downloadManifestHandle: 'resourcesat-2a-liss3-boa/download/2026-05-01/bangalore-60km.json',
  prepareManifestHandles: [
    'resourcesat-2a-liss3-boa/prepare/scene-1/manifest.json',
    'resourcesat-2a-liss3-boa/prepare/scene-2/manifest.json',
  ],
  verificationSummary: {
    verified: 4,
    failed: 2,
  },
  scheduleDecision: 'force_run',
  nextDueAt: '2026-07-01T00:00:00Z',
  windowStart: '2026-05-01',
  windowEnd: '2026-05-31',
  foundCount: 8,
  selectedCount: 6,
  downloadedCount: 0,
  rejectedCount: 2,
  failureKind: 'download_error',
  message: 'Scene download timed out after 300s',
  startedAt: '2026-06-10T10:00:00Z',
  finishedAt: '2026-06-10T10:15:00Z',
  updatedAt: '2026-06-10T10:15:00Z',
  validationProblems: [
    'Scene LISS3-20260501-001 checksum mismatch',
    'Scene LISS3-20260501-003 zero-byte analytic.tif',
  ],
  rejectionReasons: [
    'Scene LISS3-20260501-002 cloud cover 85% > threshold',
  ],
  artifactHandles: {
    search_log: 'resourcesat-2a-liss3-boa/logs/2026-05-01/search.log',
    download_log: 'resourcesat-2a-liss3-boa/logs/2026-05-01/download.log',
  },
  ledgerRows: [
    {
      productId: 'liss3-scene-001',
      status: 'failed',
      failureKind: 'download_error',
      bytes: 0,
      retries: 2,
    },
    {
      productId: 'liss3-scene-002',
      status: 'composited',
      failureKind: null,
      bytes: 52428800,
      retries: 0,
    },
  ],
};

function renderPage(jobId = 'job-abc123456789012345678') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter initialEntries={ [`/monitoring/ingestion-jobs/${jobId}`] }>
        <Routes>
          <Route
            path="/monitoring/ingestion-jobs/:jobId"
            element={ <IngestionJobDetail /> }
          />
        </Routes>
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

describe('IngestionJobDetail', () => {
  it('renders all tab triggers: Summary, Provider Inputs, Candidates, Downloads, Verification, Ledger, Logs, Actions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    // Wait for job data to load (sourceId appears in header + Summary tab)
    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    const expectedTabs = [
      'Summary',
      'Provider Inputs',
      'Candidates',
      'Downloads',
      'Verification',
      'Ledger',
      'Logs',
      'Actions',
    ];
    for (const tab of expectedTabs) {
      expect(screen.getByRole('tab', { name: tab })).toBeTruthy();
    }
  });

  it('Summary tab shows job ID, source, provider, AOI, state, window, and counts', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Job ID shown in monospace
    expect(screen.getAllByText('job-abc123456789012345678').length).toBeGreaterThan(0);

    // Source, provider, AOI
    expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ISRO/NRSC').length).toBeGreaterThan(0);
    expect(screen.getAllByText('bangalore-60km').length).toBeGreaterThan(0);

    // State badge
    expect(screen.getAllByText('failed').length).toBeGreaterThan(0);

    // Failure kind (appears in Summary tab KVRow)
    expect(screen.getAllByText('download_error').length).toBeGreaterThan(0);

    // Window dates are shown
    expect(screen.getAllByText('2026-05-01').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-05-31').length).toBeGreaterThan(0);

    // Counts section labels appear in Summary and Candidates tabs (both forceMount)
    expect(screen.getAllByText('Found').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Selected').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Downloaded').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Rejected').length).toBeGreaterThan(0);

    // Message (appears in Summary and Logs tabs with forceMount)
    expect(screen.getAllByText('Scene download timed out after 300s').length).toBeGreaterThan(0);
  });

  it('shows artifact handles as opaque storage keys — not as raw filesystem paths or external URLs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Handles should NOT appear as anchor hrefs pointing to raw storage paths
    const externalLinks = document.querySelectorAll(`a[href*="/srv/"], a[href*="s3://"], a[href*="/data/"]`);
    expect(externalLinks.length).toBe(0);

    // Artifact handles are rendered in the Logs tab panel (may be hidden until activated).
    // Use { hidden: true } to confirm data was rendered regardless of active tab state.
    const logHandle = 'resourcesat-2a-liss3-boa/logs/2026-05-01/search.log';
    expect(screen.getByText(logHandle, { hidden: true })).toBeTruthy();

    // Manifest handles are rendered in Candidates / Downloads tab panels
    const searchHandle = 'resourcesat-2a-liss3-boa/search/2026-05-01/bangalore-60km.json';
    expect(screen.getByText(searchHandle, { hidden: true })).toBeTruthy();

    // Prepare manifest handles are opaque storage keys — not external href links
    const prepareHandle = 'resourcesat-2a-liss3-boa/prepare/scene-1/manifest.json';
    const handleEl = screen.getByText(prepareHandle, { hidden: true });
    // Must be a code element (monospace), not an anchor
    expect(handleEl.tagName.toLowerCase()).toBe('code');

    // "Raw content is not exposed here" disclaimer (in Logs tab panel)
    expect(screen.getByText(/Artifact handles are storage keys managed server-side/, { hidden: true })).toBeTruthy();
  });

  it('renders failure reason and validation problems', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Verification tab panel content (may be hidden until tab is activated)
    // Use { hidden: true } to confirm the validation problems are rendered
    expect(
      screen.getByText('Scene LISS3-20260501-001 checksum mismatch', { hidden: true }),
    ).toBeTruthy();
    expect(
      screen.getByText('Scene LISS3-20260501-003 zero-byte analytic.tif', { hidden: true }),
    ).toBeTruthy();
  });

  it('renders rejection reasons in the Candidates tab', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Candidates tab panel content (use { hidden: true } to reach inactive tab panel)
    expect(
      screen.getByText('Scene LISS3-20260501-002 cloud cover 85% > threshold', { hidden: true }),
    ).toBeTruthy();
  });

  it('renders ledger rows in the Ledger tab', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Ledger tab panel content (use { hidden: true } to reach inactive tab panel)
    expect(screen.getByText('liss3-scene-001', { hidden: true })).toBeTruthy();
    expect(screen.getByText('liss3-scene-002', { hidden: true })).toBeTruthy();
  });

  it('renders prepare manifest handles in Downloads tab as opaque handles', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Downloads tab panel content (use { hidden: true } to reach inactive tab panel)
    const h1 = screen.getByText(
      'resourcesat-2a-liss3-boa/prepare/scene-1/manifest.json',
      { hidden: true },
    );
    const h2 = screen.getByText(
      'resourcesat-2a-liss3-boa/prepare/scene-2/manifest.json',
      { hidden: true },
    );
    expect(h1).toBeTruthy();
    expect(h2).toBeTruthy();

    // Verify they are not rendered as <a> links
    const rawLinks = document.querySelectorAll(`a[href*="prepare/scene-1"]`);
    expect(rawLinks.length).toBe(0);
  });

  it('shows failure detail in the Logs tab', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Failure kind is shown in both the Summary tab (Failure kind row) and Logs tab
    expect(screen.getAllByText(/download_error/).length).toBeGreaterThan(0);
    // Failure section header appears in Logs tab panel
    expect(screen.getByText('Failure', { hidden: true })).toBeTruthy();
  });

  it('includes a back link to the ingestion jobs list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(jobDetailPayload)));

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Back to ingestion jobs list' })).toBeTruthy(),
    );
    const backLink = screen.getByRole('link', { name: 'Back to ingestion jobs list' });
    expect((backLink as HTMLAnchorElement).href).toContain('/monitoring/ingestion-jobs');
  });

  it('shows an error alert when the job fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Not found' }, 404)),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeTruthy(),
    );
    expect(screen.getByText(/Failed to load job detail/)).toBeTruthy();
  });
});
