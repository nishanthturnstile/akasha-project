import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  queryKeys,
  useCompleteOnboarding,
  useCreateReportTemplate,
  useCreatePlot,
  useDeletePlot,
  useImportPlotsGeoJson,
  useSignup,
  useIngestionSources,
  useIngestionSourceProducts,
  usePlots,
  useFieldLeaderboard,
  useTriggerIngestionJob,
  useUpdateReportTemplate,
  useUpdatePlot,
} from '@/lib/queries';
import type { Plot, PlotGeometry } from '@/types/api';

const geometry: PlotGeometry = {
  type: 'Polygon',
  coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12.01], [77, 12]]],
};

const plot: Plot = {
  id: 'plot-1',
  name: 'North field',
  geometry,
  areaHa: 1,
  createdAt: null,
  updatedAt: null,
};

const account = {
  user: {
    id: 'user-1',
    username: 'new@example.test',
    email: 'new@example.test',
    displayName: 'New User',
    onboardingCompleted: false,
  },
  currentTeam: { id: 'team-1', name: "New User's Team", role: 'owner' },
  memberships: [{ teamId: 'team-1', teamName: "New User's Team", role: 'owner' }],
  authMode: 'enabled',
};

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

  const Provider = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={ queryClient }>{ children }</QueryClientProvider>
  );

  return { Provider, invalidateSpy, queryClient };
}

describe('plot query hooks', () => {
  it('fetches plots', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([plot])));
    const { Provider } = wrapper();
    const { result } = renderHook(() => usePlots(), { wrapper: Provider });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([plot]);
  });

  it('invalidates plots after create, update, delete, and import mutations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === '/api/plots' && init?.method === 'POST') {
          return Promise.resolve(jsonResponse(plot, 201));
        }
        if (path === '/api/plots/plot-1' && init?.method === 'PATCH') {
          return Promise.resolve(jsonResponse(plot));
        }
        if (path === '/api/plots/plot-1' && init?.method === 'DELETE') {
          return Promise.resolve({ ok: true, status: 204, json: async () => undefined });
        }
        if (path === '/api/plots/import/geojson') {
          return Promise.resolve(
            jsonResponse({ imported: [plot], rejected: [], importedCount: 1, rejectedCount: 0 }),
          );
        }
        return Promise.resolve(jsonResponse([plot]));
      }),
    );
    const { Provider, invalidateSpy } = wrapper();

    const create = renderHook(() => useCreatePlot(), { wrapper: Provider });
    const update = renderHook(() => useUpdatePlot(), { wrapper: Provider });
    const deletedIds: string[] = [];
    const remove = renderHook(() => useDeletePlot({ onDeleted: (id) => deletedIds.push(id) }), {
      wrapper: Provider,
    });
    const importHook = renderHook(() => useImportPlotsGeoJson(), { wrapper: Provider });

    await create.result.current.mutateAsync({ name: 'North field', geometry });
    await update.result.current.mutateAsync({ plotId: 'plot-1', payload: { status: 'active' } });
    await remove.result.current.mutateAsync('plot-1');
    await importHook.result.current.mutateAsync({ type: 'Feature', geometry, properties: {} });

    expect(deletedIds).toEqual(['plot-1']);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.plots });
    expect(invalidateSpy).toHaveBeenCalledTimes(4);
  });
});

describe('report query hooks', () => {
  it('fetches leaderboard using filter-scoped query keys', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ rows: [], metadata: {} }));
    vi.stubGlobal('fetch', fetchMock);
    const { Provider } = wrapper();

    const { result } = renderHook(
      () => useFieldLeaderboard({ indexType: 'NDVI', cropType: 'Paddy' }),
      { wrapper: Provider },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/reports/field-leaderboard?indexType=NDVI&cropType=Paddy',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('invalidates report templates after create and update', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) === '/api/reports/templates' && init?.method === 'POST') {
          return Promise.resolve(jsonResponse({ id: 'template-1', name: 'Summary', columns: [] }, 201));
        }
        if (String(input) === '/api/reports/templates/template-1' && init?.method === 'PATCH') {
          return Promise.resolve(jsonResponse({ id: 'template-1', name: 'Updated', columns: [] }));
        }
        return Promise.resolve(jsonResponse([]));
      }),
    );
    const { Provider, invalidateSpy } = wrapper();
    const create = renderHook(() => useCreateReportTemplate(), { wrapper: Provider });
    const update = renderHook(() => useUpdateReportTemplate(), { wrapper: Provider });

    await create.result.current.mutateAsync({ name: 'Summary', columns: ['field'] });
    await update.result.current.mutateAsync({
      templateId: 'template-1',
      payload: { name: 'Updated' },
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.reportTemplates });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.reportTemplate('template-1') });
  });
});

describe('auth query hooks', () => {
  it('caches account data after signup and onboarding completion', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === '/api/account/onboarding-complete') {
          return Promise.resolve(
            jsonResponse({
              ...account,
              user: { ...account.user, onboardingCompleted: true },
            }),
          );
        }
        return Promise.resolve(jsonResponse(account));
      }),
    );
    const { Provider, queryClient } = wrapper();
    const signupHook = renderHook(() => useSignup(), { wrapper: Provider });
    const completeHook = renderHook(() => useCompleteOnboarding(), { wrapper: Provider });

    const signedUp = await signupHook.result.current.mutateAsync({
      email: 'new@example.test',
      password: 'password123',
      displayName: 'New User',
    });
    const completed = await completeHook.result.current.mutateAsync();

    expect(signedUp.user.onboardingCompleted).toBe(false);
    expect(completed.user.onboardingCompleted).toBe(true);
    expect(queryClient.getQueryData(queryKeys.accountMe)).toEqual(completed);
  });
});

describe('ingestion trigger query hooks', () => {
  it('fetches simplified ingestion sources from the satellite-centric endpoint', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === '/api/monitoring/ingestion-sources') {
        return Promise.resolve(jsonResponse({
          status: 'ok',
          generatedAt: '2026-06-25T12:00:00Z',
          liveTriggerEnabled: true,
          sources: [
            {
              sourceId: 'resourcesat-2a-liss3-boa',
              label: 'ResourceSat-2A LISS-3 BOA',
              provider: 'ISRO/NRSC Bhoonidhi',
              kind: 'optical',
              active: true,
              gatedReason: null,
              aoiId: 'bangalore-60km',
              cadenceDays: 7,
              lastRunAt: '2026-06-20T01:00:00Z',
              lastSuccessAt: '2026-06-20T01:30:00Z',
              lastFailureAt: null,
              nextDueAt: '2026-06-27T01:00:00Z',
              isDue: false,
              isOverdue: false,
              latestCompositeDate: '2026-06-18',
              lastJob: null,
            },
          ],
        }));
      }
      return Promise.resolve(jsonResponse({ status: 'ok' }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const { Provider } = wrapper();

    const { result } = renderHook(() => useIngestionSources(), { wrapper: Provider });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/monitoring/ingestion-sources',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(result.current.data?.sources[0].sourceId).toBe('resourcesat-2a-liss3-boa');
  });

  it('fetches per-source product rows lazily when enabled', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).includes('/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products')) {
        return Promise.resolve(jsonResponse({
          status: 'ok',
          generatedAt: '2026-06-25T12:00:00Z',
          sourceId: 'resourcesat-2a-liss3-boa',
          products: [
            {
              productId: 'RA319MAR2026048153009900065PSANSTUCSRHTDF',
              sceneKey: 'resourcesat-2a-liss3-boa:BOA:99:65:2026-03-19T00:00:00Z',
              acquisitionDate: '2026-03-19',
              status: 'downloaded',
              bytes: 1048576,
              updatedAt: '2026-06-20T01:30:00Z',
              error: null,
            },
          ],
        }));
      }
      return Promise.resolve(jsonResponse({ status: 'ok' }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const { Provider } = wrapper();

    const disabled = renderHook(
      () => useIngestionSourceProducts('resourcesat-2a-liss3-boa', { enabled: false }),
      { wrapper: Provider },
    );
    expect(disabled.result.current.fetchStatus).toBe('idle');
    expect(fetchMock).not.toHaveBeenCalled();

    const enabled = renderHook(
      () => useIngestionSourceProducts('resourcesat-2a-liss3-boa', { enabled: true, limit: 10 }),
      { wrapper: Provider },
    );

    await waitFor(() => expect(enabled.result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products?limit=10',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(enabled.result.current.data?.products[0].productId).toContain('RA319');
  });

  it('posts trigger requests and invalidates ingestion monitoring queries on success', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/monitoring/ingestion-jobs/trigger' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({
          status: 'submitted',
          jobRequestId: 'ingest-ui-20260626-abcdef12',
          dryRun: true,
          jobsUrl: '/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa',
          message: 'Submitted',
        }));
      }
      return Promise.resolve(jsonResponse({ status: 'ok' }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const { Provider, invalidateSpy } = wrapper();
    const triggerHook = renderHook(() => useTriggerIngestionJob(), { wrapper: Provider });

    await triggerHook.result.current.mutateAsync({
      sourceId: 'resourcesat-2a-liss3-boa',
      aoiId: 'bangalore-60km',
      dryRun: true,
      confirmLive: false,
      windowDays: 12,
      maxDownloads: 1,
      notes: 'dry-run smoke',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/monitoring/ingestion-jobs/trigger',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          sourceId: 'resourcesat-2a-liss3-boa',
          aoiId: 'bangalore-60km',
          dryRun: true,
          confirmLive: false,
          windowDays: 12,
          maxDownloads: 1,
          notes: 'dry-run smoke',
        }),
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.ingestionJobs() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.ingestionSchedules });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.imagerySourceMonitoring });
  });
});
