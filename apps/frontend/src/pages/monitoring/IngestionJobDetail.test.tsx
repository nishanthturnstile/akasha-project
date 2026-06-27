import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IngestionJobDetail from '@/pages/monitoring/IngestionJobDetail';
import type { IngestionJobDetail as IngestionJobDetailPayload, IngestionJobEvent } from '@/types/api';

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

function eventsResponse(events: IngestionJobEvent[] = []) {
  return {
    status: 'ok',
    generatedAt: '2026-06-10T10:16:00Z',
    jobId: jobDetailPayload.jobId,
    events,
    truncated: false,
    scannedCount: events.length,
    totalEventsScanned: events.length,
    totalValidEvents: events.length,
  };
}

function mockJobAndEventsFetch({
  job = jobDetailPayload,
  events = [],
  eventsStatus = 200,
}: {
  job?: IngestionJobDetailPayload;
  events?: IngestionJobEvent[];
  eventsStatus?: number;
} = {}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/events')) {
      return Promise.resolve(jsonResponse(eventsResponse(events), eventsStatus));
    }
    if (url.includes('/api/monitoring/ingestion-jobs/')) {
      return Promise.resolve(jsonResponse(job));
    }
    return Promise.resolve(jsonResponse({ error: { code: 'unexpected_url', message: url } }, 500));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function mockDefaultJobAndEventsFetch(job: IngestionJobDetailPayload = jobDetailPayload) {
  return mockJobAndEventsFetch({ job, events: [] });
}

function getPipelineText() {
  const pipeline = screen.getByTestId('orchestration-pipeline');
  return pipeline.textContent ?? '';
}

async function waitForPipeline() {
  await waitFor(() =>
    expect(screen.getByTestId('orchestration-pipeline')).toBeTruthy(),
  );
}

function expectDistinctJobAndEventsFetches(fetchMock: ReturnType<typeof vi.fn>, jobId = jobDetailPayload.jobId) {
  const urls = fetchMock.mock.calls.map(([input]) => String(input));
  expect(urls).toContain(`/api/monitoring/ingestion-jobs/${jobId}`);
  expect(urls).toContain(`/api/monitoring/ingestion-jobs/${jobId}/events`);
}

/** A complete IngestionJobDetail fixture that exercises all tabs and sections. */
const jobDetailPayload: IngestionJobDetailPayload = {
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
  it('renders all tab triggers with Pipeline before Summary', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    // Wait for job data to load (sourceId appears in header + Summary tab)
    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    const expectedTabs = [
      'Pipeline',
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

    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabLabels.indexOf('Pipeline')).toBeLessThan(tabLabels.indexOf('Summary'));
  });

  it('renders the Pipeline tab success state from distinct job detail and events API responses', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'succeeded',
        failureKind: null,
        message: 'Job completed successfully',
      },
      events: [
        {
          timestamp: '2026-06-10T10:00:00Z',
          eventType: 'job_created',
          stage: 'planned',
          status: 'succeeded',
          message: 'Planning event recorded.',
          payload: {},
        },
      ],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('1 event');
    expect(pipelineText).toContain('succeeded');
    expect(pipelineText).toContain('Planning event recorded.');
  });

  it('renders the Pipeline tab running state from events while keeping fallback stage evidence visible', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'running',
        failureKind: null,
        finishedAt: null,
        message: 'Job is still running',
      },
      events: [
        {
          timestamp: '2026-06-10T10:02:00Z',
          eventType: 'status_change',
          stage: 'running',
          status: 'running',
          message: 'Scheduler marked the job running.',
          payload: {},
        },
      ],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('running');
    expect(pipelineText).toContain('Scheduler marked the job running.');
    expect(pipelineText).toContain('Found candidates: 8.');
  });

  it('renders the Pipeline tab failed state on the failed stage', async () => {
    const fetchMock = mockJobAndEventsFetch();

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('Terminal job state: failed');
    expect(pipelineText).toContain('Download');
    expect(pipelineText).toContain('download_error');
  });

  it('renders the Pipeline tab skipped_gated state without implying runtime approval', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'skipped_gated',
        failureKind: null,
        scheduleDecision: 'skipped_gated',
        foundCount: null,
        selectedCount: null,
        downloadedCount: null,
        rejectedCount: null,
        verificationSummary: {},
        artifactHandles: {},
        ledgerRows: [],
      },
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('skipped_gated');
    expect(pipelineText).toContain('Approved runtime');
    expect(pipelineText).toContain('No reliable stage evidence yet.');
    expect(pipelineText).not.toContain('Runtime approval inferred from job state.');
  });

  it('keeps planned jobs before runtime approval until execution evidence exists', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'planned',
        failureKind: null,
        foundCount: null,
        selectedCount: null,
        downloadedCount: null,
        rejectedCount: null,
        verificationSummary: {},
        artifactHandles: {},
        ledgerRows: [],
      },
      events: [
        {
          timestamp: '2026-06-10T10:00:00Z',
          eventType: 'job_created',
          stage: 'planned',
          status: 'planned',
          message: 'Job created.',
          payload: {},
        },
      ],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('Job created.');
    expect(pipelineText).toContain('Approved runtime');
    expect(pipelineText).toContain('No reliable stage evidence yet.');
    expect(pipelineText).not.toContain('Runtime approval inferred from job state.');
    expect(pipelineText).not.toContain('Job is running; per-stage instrumentation is not yet available.');
  });

  it('keeps queued jobs out of provider stages until worker execution starts', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'queued',
        failureKind: null,
        foundCount: null,
        selectedCount: null,
        downloadedCount: null,
        rejectedCount: null,
        verificationSummary: {},
        artifactHandles: {},
        ledgerRows: [],
      },
      events: [
        {
          timestamp: '2026-06-10T10:01:00Z',
          eventType: 'status_change',
          stage: 'running',
          status: 'queued',
          message: 'Job queued.',
          payload: {},
        },
      ],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('Job queued.');
    expect(pipelineText).toContain('Approved runtime');
    expect(pipelineText).toContain('Search');
    expect(pipelineText).toContain('No reliable stage evidence yet.');
    expect(pipelineText).not.toContain('Runtime approval inferred from job state.');
    expect(pipelineText).not.toContain('Job is running; per-stage instrumentation is not yet available.');
  });

  it('renders missing-events fallback states in the Pipeline tab', async () => {
    const fetchMock = mockJobAndEventsFetch({ events: [] });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    expect(pipelineText).toContain('0 events');
    expect(pipelineText).toContain('Plan inferred from job detail because no planned event was returned.');
    expect(pipelineText).toContain('inferred');
    expect(pipelineText).toContain('unavailable');
  });

  it('does not infer Prepare from search or download manifest handles alone', async () => {
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        state: 'succeeded',
        failureKind: null,
        message: 'Job completed without prepare artifact evidence in the response.',
        artifactHandles: {
          search_manifest: 'job-1:search_manifest',
          download_manifest: 'job-1:download_manifest',
        },
        ledgerRows: [],
      },
      events: [],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipeline = screen.getByTestId('orchestration-pipeline');
    const prepareStage = pipeline.querySelector('li[aria-label*="Prepare"]');
    expect(prepareStage?.textContent ?? '').toContain('No reliable stage evidence yet.');
    expect(prepareStage?.textContent ?? '').not.toContain(
      'Preparation evidence is present in sanitized artifact or ledger metadata.',
    );
  });

  it('does not leak raw filesystem paths or URL-like artifact values in the Pipeline tab', async () => {
    const rawValues = [
      '/srv/akasha/data/work/scene-001/analytic.tif',
      '/tmp/akasha-download/product.zip',
      'C:\\Users\\operator\\Downloads\\secret-scene.tif',
      'https://provider.example.test/raw-product.tif?token=secret',
    ];
    const fetchMock = mockJobAndEventsFetch({
      job: {
        ...jobDetailPayload,
        failureKind: rawValues[0],
        artifactHandles: {
          srv_path: rawValues[0],
          tmp_path: rawValues[1],
          windows_path: rawValues[2],
          signed_url: rawValues[3],
        },
        ledgerRows: [
          {
            productId: 'safe-product-id',
            status: 'failed',
            rawPath: rawValues[2],
          },
        ],
      },
      events: [
        {
          timestamp: '2026-06-10T10:00:00Z',
          eventType: 'job_created',
          stage: 'planned',
          status: 'succeeded',
          message: rawValues[3],
          payload: { rawPath: rawValues[0] },
        },
      ],
    });

    renderPage();

    await waitForPipeline();

    expectDistinctJobAndEventsFetches(fetchMock);
    const pipelineText = getPipelineText();
    for (const rawValue of rawValues) {
      expect(pipelineText).not.toContain(rawValue);
    }
    expect(pipelineText).not.toContain('/srv/akasha');
    expect(pipelineText).not.toContain('/tmp');
    expect(pipelineText).not.toContain('C:\\Users');
    expect(pipelineText).not.toContain('https://provider.example.test');
    expect(pipelineText).toContain('Detail redacted by monitoring safeguards.');
    expect(pipelineText).toContain('No raw paths or artifact values rendered');
  });

  it('Summary tab shows job ID, source, provider, AOI, state, window, and counts', async () => {
    mockDefaultJobAndEventsFetch();

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

  it('shows a top operator verdict for no new candidates', async () => {
    mockDefaultJobAndEventsFetch({
      ...jobDetailPayload,
      state: 'succeeded',
      failureKind: 'no_new_candidates',
      foundCount: 0,
      selectedCount: 0,
      downloadedCount: 0,
      rejectedCount: 0,
      message: 'No Bhoonidhi candidates matched the requested window.',
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('operator-verdict')).toBeTruthy(),
    );

    const verdict = screen.getByTestId('operator-verdict');
    expect(verdict.textContent).toContain('Provider returned no candidates');
    expect(verdict.textContent).toContain('No Bhoonidhi candidates matched the requested window.');
  });

  it('shows downloaded product count in the top operator verdict', async () => {
    mockDefaultJobAndEventsFetch({
      ...jobDetailPayload,
      state: 'succeeded',
      failureKind: null,
      downloadedCount: 5,
      message: 'Job completed successfully',
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('operator-verdict')).toBeTruthy(),
    );

    const verdict = screen.getByTestId('operator-verdict');
    expect(verdict.textContent).toContain('Downloaded 5 products');
    expect(verdict.textContent).toContain('Ingestion completed successfully.');
  });

  it('redacts raw path-like validation details in the top operator verdict', async () => {
    mockDefaultJobAndEventsFetch({
      ...jobDetailPayload,
      state: 'validation_failed',
      failureKind: 'validation_failed',
      message: 'Validation failed for /srv/akasha/data/work/scene-001/analytic.tif',
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('operator-verdict')).toBeTruthy(),
    );

    const verdict = screen.getByTestId('operator-verdict');
    expect(verdict.textContent).toContain('Validation failed');
    expect(verdict.textContent).toContain('Detail redacted by monitoring safeguards.');
    expect(verdict.textContent).not.toContain('/srv/akasha');
  });

  it('redacts path-like failure fields across force-mounted detail sections', async () => {
    const rawFailureKind = '/srv/akasha/ingestion/raw/failure-kind.txt';
    const rawMessage = 'failed reading C:\\Users\\operator\\secret\\download.zip';
    mockDefaultJobAndEventsFetch({
      ...jobDetailPayload,
      state: 'failed',
      failureKind: rawFailureKind,
      message: rawMessage,
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('ingestion-job-detail-page')).toBeTruthy(),
    );
    await waitFor(() =>
      expect(screen.getByTestId('operator-verdict')).toBeTruthy(),
    );

    const pageText = screen.getByTestId('ingestion-job-detail-page').textContent ?? '';
    expect(pageText).toContain('Detail redacted by monitoring safeguards.');
    expect(pageText).not.toContain('/srv/akasha');
    expect(pageText).not.toContain('C:\\Users');
    expect(pageText).not.toContain('failure-kind.txt');
    expect(pageText).not.toContain('download.zip');
  });

  it('shows artifact handles as opaque storage keys — not as raw filesystem paths or external URLs', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Handles should NOT appear as anchor hrefs pointing to raw storage paths
    const externalLinks = document.querySelectorAll(`a[href*="/srv/"], a[href*="s3://"], a[href*="/data/"]`);
    expect(externalLinks.length).toBe(0);

    // Artifact handles are rendered in force-mounted tab panels.
    const logHandle = 'resourcesat-2a-liss3-boa/logs/2026-05-01/search.log';
    expect(screen.getByText(logHandle)).toBeTruthy();

    // Manifest handles are rendered in Candidates / Downloads tab panels
    const searchHandle = 'resourcesat-2a-liss3-boa/search/2026-05-01/bangalore-60km.json';
    expect(screen.getByText(searchHandle)).toBeTruthy();

    // Prepare manifest handles are opaque storage keys — not external href links
    const prepareHandle = 'resourcesat-2a-liss3-boa/prepare/scene-1/manifest.json';
    const handleEl = screen.getByText(prepareHandle);
    // Must be a code element (monospace), not an anchor
    expect(handleEl.tagName.toLowerCase()).toBe('code');

    // "Raw content is not exposed here" disclaimer (in Logs tab panel)
    expect(screen.getByText(/Artifact handles are storage keys managed server-side/)).toBeTruthy();
  });

  it('renders failure reason and validation problems', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Verification tab panel content is force-mounted.
    expect(
      screen.getByText('Scene LISS3-20260501-001 checksum mismatch'),
    ).toBeTruthy();
    expect(
      screen.getByText('Scene LISS3-20260501-003 zero-byte analytic.tif'),
    ).toBeTruthy();
  });

  it('renders rejection reasons in the Candidates tab', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Candidates tab panel content is force-mounted.
    expect(
      screen.getByText('Scene LISS3-20260501-002 cloud cover 85% > threshold'),
    ).toBeTruthy();
  });

  it('renders ledger rows in the Ledger tab', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Ledger tab panel content is force-mounted.
    expect(screen.getByText('liss3-scene-001')).toBeTruthy();
    expect(screen.getByText('liss3-scene-002')).toBeTruthy();
  });

  it('renders prepare manifest handles in Downloads tab as opaque handles', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Downloads tab panel content is force-mounted.
    const h1 = screen.getByText(
      'resourcesat-2a-liss3-boa/prepare/scene-1/manifest.json',
    );
    const h2 = screen.getByText(
      'resourcesat-2a-liss3-boa/prepare/scene-2/manifest.json',
    );
    expect(h1).toBeTruthy();
    expect(h2).toBeTruthy();

    // Verify they are not rendered as <a> links
    const rawLinks = document.querySelectorAll(`a[href*="prepare/scene-1"]`);
    expect(rawLinks.length).toBe(0);
  });

  it('shows failure detail in the Logs tab', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('resourcesat-2a-liss3-boa').length).toBeGreaterThan(0),
    );

    // Failure kind is shown in both the Summary tab (Failure kind row) and Logs tab
    expect(screen.getAllByText(/download_error/).length).toBeGreaterThan(0);
    // Failure section header appears in Logs tab panel
    expect(screen.getByText('Failure')).toBeTruthy();
  });

  it('includes a back link to the ingestion jobs list', async () => {
    mockDefaultJobAndEventsFetch();

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Back to ingestion jobs list' })).toBeTruthy(),
    );
    const backLink = screen.getByRole('link', { name: 'Back to ingestion jobs list' });
    expect((backLink as HTMLAnchorElement).href).toContain('/admin/ingestion/jobs');
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

  it('maps canonical validation_failed to destructive while preserving backend state text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({
        ...jobDetailPayload,
        state: 'validation_failed',
        failureKind: 'verification_error',
      })),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('validation_failed').length).toBeGreaterThan(0),
    );

    const badges = screen
      .getAllByText('validation_failed')
      .filter((el) => el.className.includes('rounded-pill'));
    expect(badges.length).toBeGreaterThan(0);
    for (const badge of badges) {
      expect(badge.className).toContain('text-destructive');
    }
  });

  it('keeps unknown backend state text neutral instead of aliasing it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({
        ...jobDetailPayload,
        state: 'provider_paused',
        failureKind: null,
      })),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getAllByText('provider_paused').length).toBeGreaterThan(0),
    );

    const badges = screen
      .getAllByText('provider_paused')
      .filter((el) => el.className.includes('rounded-pill'));
    expect(badges.length).toBeGreaterThan(0);
    for (const badge of badges) {
      expect(badge.className).toContain('text-muted-foreground');
    }
  });
});
