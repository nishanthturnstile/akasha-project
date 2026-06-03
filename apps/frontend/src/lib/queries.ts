import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlot,
  deletePlot,
  getFieldScenes,
  getConfig,
  getDates,
  getDefaultLayer,
  getPlots,
  getSources,
  importPlotsGeoJson,
  syncFieldProvider,
  updatePlot,
} from '@/lib/api';
import type { PlotUpdatePayload } from '@/types/api';

export const queryKeys = {
  config: ['config'] as const,
  sources: ['sources'] as const,
  dates: (sourceId: string) => ['dates', sourceId] as const,
  defaultLayer: ['layers', 'default'] as const,
  plots: ['plots'] as const,
  fieldScenes: (plotId: string, provider = 'auto') => ['fields', plotId, 'scenes', provider] as const,
};

interface UpdatePlotVariables {
  plotId: string;
  payload: PlotUpdatePayload;
}

interface DeletePlotOptions {
  onDeleted?: (plotId: string) => void;
}

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config, queryFn: getConfig });
}

export function useSources() {
  return useQuery({ queryKey: queryKeys.sources, queryFn: getSources });
}

export function useDates(sourceId: string | undefined) {
  return useQuery({
    queryKey: sourceId ? queryKeys.dates(sourceId) : (['dates', 'none'] as const),
    queryFn: () => getDates(sourceId as string),
    enabled: Boolean(sourceId),
  });
}

export function useDefaultLayer() {
  return useQuery({ queryKey: queryKeys.defaultLayer, queryFn: getDefaultLayer });
}

export function usePlots() {
  return useQuery({ queryKey: queryKeys.plots, queryFn: getPlots });
}

export function useCreatePlot() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createPlot,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plots }),
  });
}

export function useUpdatePlot() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ plotId, payload }: UpdatePlotVariables) => updatePlot(plotId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plots }),
  });
}

export function useDeletePlot(options: DeletePlotOptions = {}) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deletePlot,
    onSuccess: (_data, plotId) => {
      options.onDeleted?.(plotId);
      return queryClient.invalidateQueries({ queryKey: queryKeys.plots });
    },
  });
}

export function useImportPlotsGeoJson() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: importPlotsGeoJson,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plots }),
  });
}

export function useFieldScenes(plotId: string | null | undefined, provider: 'auto' | 'eos' | 'native' = 'auto') {
  return useQuery({
    queryKey: plotId ? queryKeys.fieldScenes(plotId, provider) : (['fields', 'none', 'scenes', provider] as const),
    queryFn: () => getFieldScenes(plotId as string, { provider }),
    enabled: Boolean(plotId),
  });
}

export function useSyncFieldProvider() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: syncFieldProvider,
    onSuccess: (_data, plotId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.plots });
      void queryClient.invalidateQueries({ queryKey: ['fields', plotId, 'scenes'] });
    },
  });
}
