import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import IngestionSchedules from '@/pages/monitoring/IngestionSchedules';
import type { IngestionScheduleResponse } from '@/types/api';

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

function renderPage(payload: IngestionScheduleResponse = schedulePayload) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(payload)));
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
    expect(screen.getByText('bangalore-60km')).toBeTruthy();
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
});
