import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  queryKeys,
  useCreatePlot,
  useDeletePlot,
  useImportPlotsGeoJson,
  usePlots,
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

  return { Provider, invalidateSpy };
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
