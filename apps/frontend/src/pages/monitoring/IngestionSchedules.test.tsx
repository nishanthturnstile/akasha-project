import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IngestionSchedules from '@/pages/monitoring/IngestionSchedules';
import type { AppConfig, IngestionScheduleResponse } from '@/types/api';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

const schedulePayload: IngestionScheduleResponse = {
  status: 'ok',
  generatedAt: '2026-06-25T12:00:00Z',
  schedules: [
    {
      sourceId: 'resourcesat-2a-liss3-boa',
      provider: 'ISRO/NRSC',
      adapter: 'bhoonidhi',
      aoiId: 'bangalore-60km',
      lifecycleState: 'active',
      scheduleState: 'queued',
      capabilities: ['optical_indices'],
      commercialState: 'production',
      aoiScope: 'regional',
      validationState: 'validated',
      scheduleEnabled: true,
      productExposure: 'public',
      lastRunAt: '2026-06-24T08:00:00Z',
      lastSuccessAt: '2026-06-24T09:15:00Z',
      lastFailureAt: '2026-06-15T10:30:00Z',
      nextDueAt: '2026-07-01T00:00:00Z',
      nextWindowStart: '2026-06-01T00:00:00Z',
      nextWindowEnd: '2026-06-16T00:00:00Z',
      cadenceDays: 16,
      dueReason: 'Backend marked this source overdue after the latest scheduler check.',
      isDue: true,
      isOverdue: true,
    },
    {
      sourceId: 'liss4-validation',
      provider: 'ISRO/NRSC',
      adapter: 'bhoonidhi',
      aoiId: 'mysore-30km',
      lifecycleState: 'trial',
      scheduleState: 'planned',
      capabilities: ['visual_review'],
      commercialState: 'trial',
      aoiScope: 'regional',
      validationState: 'pending',
      scheduleEnabled: true,
      productExposure: 'internal',
      lastRunAt: '2026-06-20T07:00:00Z',
      lastSuccessAt: null,
      lastFailureAt: null,
      nextDueAt: '2026-07-05T00:00:00Z',
      nextWindowStart: '2026-06-17T00:00:00Z',
      nextWindowEnd: '2026-07-01T00:00:00Z',
      cadenceDays: 14,
      dueReason: 'Backend marked this validation source due.',
      isDue: true,
      isOverdue: false,
    },
    {
      sourceId: 'sentinel-legacy-context',
      provider: 'ESA',
      adapter: 'sentinel',
      aoiId: 'archive-context',
      lifecycleState: 'disabled',
      scheduleState: 'skipped_not_due',
      capabilities: ['archive'],
      commercialState: 'legacy',
      aoiScope: 'archive',
      validationState: 'blocked',
      scheduleEnabled: false,
      productExposure: 'hidden',
      lastRunAt: null,
      lastSuccessAt: '2026-05-01T06:00:00Z',
      lastFailureAt: '2026-05-15T06:00:00Z',
      nextDueAt: '2026-06-01T00:00:00Z',
      nextWindowStart: null,
      nextWindowEnd: null,
      cadenceDays: 30,
      dueReason: 'Backend marked this legacy source current despite the old next due date.',
      isDue: false,
      isOverdue: false,
    },
  ],
};

function appConfigPayload(liveTriggerEnabled = false): AppConfig {
  return {
    appName: 'Akasha',
    aoi: {
      id: 'bangalore-60km',
      name: 'Bangalore 60 km',
      center: [77.5946, 12.9716],
      zoom: 9,
      bounds: [77, 12, 78, 13],
    },
    aois: [],
    basemapStyleUrl: '',
    basemap: {
      provider: 'empty',
      style: '',
      styleFamily: 'empty',
      usageModel: 'session',
      places: 'none',
      sessionDurationSeconds: 0,
    },
    maxPolygonAreaHa: 1000,
    maxPolygonVertices: 500,
    usablePixelThresholdPercent: 75,
    supportedIndices: ['NDVI'],
    defaultIndex: 'NDVI',
    adminIngestionLiveTriggerEnabled: liveTriggerEnabled,
  };
}

function renderPage(
  payload: IngestionScheduleResponse = schedulePayload,
  stubFetch = true,
  liveTriggerEnabled = false,
) {
  if (stubFetch) {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.includes('/api/config')) {
          return Promise.resolve(jsonResponse(appConfigPayload(liveTriggerEnabled)));
        }
        return Promise.resolve(jsonResponse(payload));
      }),
    );
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter>
        <IngestionSchedules />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function waitForSchedules() {
  await waitFor(() =>
    expect(screen.getByText('resourcesat-2a-liss3-boa')).toBeTruthy(),
  );
}

function expectVisibleSources(sources: string[]) {
  for (const schedule of schedulePayload.schedules) {
    const assertion = expect(screen.queryByText(schedule.sourceId));
    if (sources.includes(schedule.sourceId)) {
      assertion.toBeTruthy();
    } else {
      assertion.toBeNull();
    }
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('IngestionSchedules', () => {
  it('renders schedule rows with source, state, exposure, validation, run timing, cadence, due reason, and backend due badges', async () => {
    renderPage();

    await waitForSchedules();

    expect(screen.getByText('Admin · Internal operations')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Ingestion schedules' })).toBeTruthy();
    for (const heading of [
      'Source ID',
      'Provider',
      'AOI',
      'Lifecycle',
      'Schedule',
      'Exposure',
      'Validation',
      'Last run',
      'Last success',
      'Last failure',
      'Next due',
      'Next window',
      'Cadence',
      'Due reason',
      'Status',
    ]) {
      expect(screen.getAllByText(heading).length).toBeGreaterThan(0);
    }

    expect(screen.getAllByText('ISRO/NRSC').length).toBeGreaterThan(0);
    expect(screen.getAllByText('bangalore-60km').length).toBeGreaterThan(0);
    expect(screen.getAllByText('active').length).toBeGreaterThan(0);
    expect(screen.getAllByText('queued').length).toBeGreaterThan(0);
    expect(screen.getAllByText('public').length).toBeGreaterThan(0);
    expect(screen.getAllByText('validated').length).toBeGreaterThan(0);
    expect(screen.getByText('2026-06-24 08:00')).toBeTruthy();
    expect(screen.getByText('2026-06-24 09:15')).toBeTruthy();
    expect(screen.getByText('2026-06-15 10:30')).toBeTruthy();
    expect(screen.getByText('2026-07-01 00:00')).toBeTruthy();
    expect(screen.getByText('2026-06-01 00:00 → 2026-06-16 00:00')).toBeTruthy();
    expect(screen.getByText('16 d')).toBeTruthy();
    expect(
      screen.getByText('Backend marked this source overdue after the latest scheduler check.'),
    ).toBeTruthy();

    expect(screen.getAllByText('Overdue').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Due').length).toBeGreaterThan(0);
    expect(screen.getByText('Current')).toBeTruthy();
    expect(screen.getByText('1 overdue')).toBeTruthy();
    expect(screen.getByText('1 due')).toBeTruthy();
  });

  it('shows an unconfigured state without rendering the schedules table', async () => {
    renderPage({
      status: 'unconfigured',
      generatedAt: '2026-06-25T12:00:00Z',
      schedules: [],
    });

    await waitFor(() =>
      expect(screen.getByText(/ingestion scheduler is not configured/i)).toBeTruthy(),
    );
    expect(screen.queryByText('Source/AOI cadence')).toBeNull();
  });

  it('shows an empty state when the scheduler reports no schedules', async () => {
    renderPage({
      status: 'ok',
      generatedAt: '2026-06-25T12:00:00Z',
      schedules: [],
    });

    await waitFor(() =>
      expect(
        screen.getByText('No ingestion schedules are currently reported by the scheduler.'),
      ).toBeTruthy(),
    );
  });

  it('filters schedules client-side by source ID, provider, schedule state, exposure, due state, and validation', async () => {
    renderPage();
    await waitForSchedules();

    fireEvent.change(screen.getByLabelText('Filter by source ID'), {
      target: { value: 'liss4' },
    });
    expectVisibleSources(['liss4-validation']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText('Filter by provider'), { target: { value: 'ESA' } });
    expectVisibleSources(['sentinel-legacy-context']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText('Filter by schedule'), {
      target: { value: 'planned' },
    });
    expectVisibleSources(['liss4-validation']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText('Filter by exposure'), {
      target: { value: 'public' },
    });
    expectVisibleSources(['resourcesat-2a-liss3-boa']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText('Filter by due or overdue status'), {
      target: { value: 'overdue' },
    });
    expectVisibleSources(['resourcesat-2a-liss3-boa']);

    fireEvent.change(screen.getByLabelText('Filter by due or overdue status'), {
      target: { value: 'due' },
    });
    expectVisibleSources(['liss4-validation']);

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    fireEvent.change(screen.getByLabelText('Filter by validation'), {
      target: { value: 'blocked' },
    });
    expectVisibleSources(['sentinel-legacy-context']);
  });

  it('shows a no-match state when filters exclude every schedule', async () => {
    renderPage();
    await waitForSchedules();

    fireEvent.change(screen.getByLabelText('Filter by source ID'), {
      target: { value: 'does-not-exist' },
    });

    expect(screen.getByText('No schedules match the current filters.')).toBeTruthy();
  });

  it('calls the ingestion schedules API endpoint', async () => {
    renderPage();

    await waitForSchedules();

    expect(
      vi.mocked(globalThis.fetch).mock.calls.some((call) =>
        String(call[0]).includes('/api/monitoring/ingestion-schedules'),
      ),
    ).toBe(true);
  });

  it('renders the admin run panel with ResourceSat selectable and dry run as the default', async () => {
    renderPage();
    await waitForSchedules();

    expect(screen.getByRole('heading', { name: 'Run one ingestion source' })).toBeTruthy();
    const sourceSelect = screen.getByLabelText('Ingestion source');
    const options = within(sourceSelect).getAllByRole('option') as HTMLOptionElement[];
    expect(options.some((option) => option.value === 'resourcesat-2a-liss3-boa')).toBe(true);
    expect((screen.getByLabelText('Ingestion AOI') as HTMLSelectElement).value).toBe('bangalore-60km');
    expect((screen.getByLabelText('Dry run') as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByLabelText('Live canary')).toBeNull();
  });

  it('prefills the run panel from a schedule row action', async () => {
    renderPage();
    await waitForSchedules();

    fireEvent.click(screen.getByRole('button', { name: /Run this source liss4-validation/ }));

    expect((screen.getByLabelText('Ingestion source') as HTMLSelectElement).value).toBe('liss4-validation');
    expect((screen.getByLabelText('Ingestion AOI') as HTMLSelectElement).value).toBe('mysore-30km');
  });

  it('gates live canary submit until the checkbox and typed acknowledgment are complete', async () => {
    renderPage(schedulePayload, true, true);
    await waitForSchedules();

    fireEvent.click(screen.getByLabelText('Live canary'));
    const submit = screen.getByRole('button', { name: /Submit ingestion request/ }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText('Confirm live ingestion side effects'));
    fireEvent.change(screen.getByLabelText('Live canary acknowledgment'), {
      target: { value: 'LIVE CANARY' },
    });

    expect(submit.disabled).toBe(false);
  });

  it('submits a dry-run trigger request and shows the filtered jobs link on success', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.includes('/api/monitoring/ingestion-jobs/trigger') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({
          status: 'submitted',
          jobRequestId: 'ingest-ui-20260626-abcdef12',
          dryRun: true,
          jobsUrl: '/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa',
          message: 'Submitted',
        }));
      }
      if (path.includes('/api/config')) {
        return Promise.resolve(jsonResponse(appConfigPayload()));
      }
      return Promise.resolve(jsonResponse(schedulePayload));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage(schedulePayload, false);
    await waitForSchedules();
    fireEvent.change(screen.getByLabelText('Operator notes'), {
      target: { value: 'Check latest Bangalore coverage' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Submit ingestion request/ }));

    await waitFor(() =>
      expect(screen.getByText('Submitted — waiting for staging runner pickup')).toBeTruthy(),
    );

    const triggerCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes('/api/monitoring/ingestion-jobs/trigger'),
    );
    expect(triggerCall).toBeTruthy();
    expect(JSON.parse(String(triggerCall?.[1]?.body))).toMatchObject({
      sourceId: 'resourcesat-2a-liss3-boa',
      aoiId: 'bangalore-60km',
      dryRun: true,
      confirmLive: false,
      windowDays: 12,
      maxDownloads: 1,
      notes: 'Check latest Bangalore coverage',
    });
    expect((screen.getByRole('link', { name: 'View filtered jobs' }) as HTMLAnchorElement).href)
      .toContain('/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa');
    expect(screen.getByRole('link', { name: 'All ingestion jobs' })).toBeTruthy();
  });

  it('shows unavailable trigger responses without claiming the job was submitted', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.includes('/api/monitoring/ingestion-jobs/trigger') && init?.method === 'POST') {
          return Promise.resolve(jsonResponse({
            status: 'unavailable',
            jobRequestId: null,
            dryRun: true,
            jobsUrl: '/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa',
            message: 'Ingestion trigger inbox is not configured or unavailable.',
          }));
        }
        if (path.includes('/api/config')) {
          return Promise.resolve(jsonResponse(appConfigPayload()));
        }
        return Promise.resolve(jsonResponse(schedulePayload));
      }),
    );

    renderPage(schedulePayload, false);
    await waitForSchedules();
    fireEvent.click(screen.getByRole('button', { name: /Submit ingestion request/ }));

    await waitFor(() =>
      expect(screen.getByText('Ingestion trigger inbox is not configured or unavailable.')).toBeTruthy(),
    );
    expect(screen.queryByText('Submitted — waiting for staging runner pickup')).toBeNull();
    expect(screen.getByRole('link', { name: 'View filtered jobs' })).toBeTruthy();
  });

  it('renders trigger errors safely without backend details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path.includes('/api/monitoring/ingestion-jobs/trigger') && init?.method === 'POST') {
          return Promise.resolve(jsonResponse({
            error: {
              code: 'SOURCE_NOT_SCHEDULABLE',
              message: 'Source is not schedulable.',
              details: { rawPath: '/srv/akasha/ingestion-inbox/secret-request.json' },
            },
          }, 400));
        }
        if (path.includes('/api/config')) {
          return Promise.resolve(jsonResponse(appConfigPayload()));
        }
        return Promise.resolve(jsonResponse(schedulePayload));
      }),
    );

    renderPage(schedulePayload, false);
    await waitForSchedules();
    fireEvent.click(screen.getByRole('button', { name: /Submit ingestion request/ }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText('Source is not schedulable.')).toBeTruthy();
    expect(screen.queryByText(/srv\/akasha/)).toBeNull();
    expect(screen.queryByText(/secret-request/)).toBeNull();
  });
});
