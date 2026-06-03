import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlot,
  deletePlot,
  exportFieldIndex,
  exportFieldReportCsv,
  getFieldScenes,
  getFieldStatistics,
  getFieldTrend,
  getConfig,
  getDates,
  getDefaultLayer,
  getPlots,
  getSources,
  importPlotsGeoJson,
  syncFieldProvider,
  updatePlot,
} from '@/lib/api';
import type {
  CloudMaskOptions,
  FieldIndexExportOptions,
  FieldReportExportOptions,
  PlotUpdatePayload,
} from '@/types/api';

export const queryKeys = {
  config: ['config'] as const,
  sources: ['sources'] as const,
  dates: (sourceId: string) => ['dates', sourceId] as const,
  defaultLayer: ['layers', 'default'] as const,
  plots: ['plots'] as const,
  fieldScenes: (plotId: string, provider = 'auto') => ['fields', plotId, 'scenes', provider] as const,
  fieldStatistics: (
    plotId: string,
    sourceId: string,
    acquisitionDate: string | null | undefined,
    indexType: string,
    cloudMask: CloudMaskOptions,
  ) =>
    [
      'fields',
      plotId,
      'statistics',
      sourceId,
      acquisitionDate ?? 'latest',
      indexType,
      cloudMask.clouds,
      cloudMask.cloudShadows,
      cloudMask.cirrus,
    ] as const,
  fieldTrend: (
    plotId: string,
    sourceId: string,
    indexType: string,
    startDate: string | undefined,
    endDate: string | undefined,
    provider: string,
    cloudMask: CloudMaskOptions,
  ) =>
    [
      'fields',
      plotId,
      'trend',
      sourceId,
      indexType,
      startDate ?? 'default-start',
      endDate ?? 'default-end',
      provider,
      cloudMask.clouds,
      cloudMask.cloudShadows,
      cloudMask.cirrus,
    ] as const,
};

interface UpdatePlotVariables {
  plotId: string;
  payload: PlotUpdatePayload;
}

interface DeletePlotOptions {
  onDeleted?: (plotId: string) => void;
}

interface FieldIndexExportVariables {
  plotId: string;
  options: FieldIndexExportOptions;
}

interface FieldReportExportVariables {
  plotId: string;
  options: FieldReportExportOptions;
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

export function useFieldStatistics(
  plotId: string | null | undefined,
  options: {
    sourceId: string | undefined;
    acquisitionDate: string | null | undefined;
    indexType: string;
    cloudMask: CloudMaskOptions;
  },
) {
  return useQuery({
    queryKey:
      plotId && options.sourceId
        ? queryKeys.fieldStatistics(
            plotId,
            options.sourceId,
            options.acquisitionDate,
            options.indexType,
            options.cloudMask,
          )
        : (['fields', 'none', 'statistics'] as const),
    queryFn: () =>
      getFieldStatistics(plotId as string, {
        sourceId: options.sourceId as string,
        acquisitionDate: options.acquisitionDate,
        indexType: options.indexType,
        cloudMask: options.cloudMask,
      }),
    enabled: Boolean(plotId && options.sourceId && options.acquisitionDate),
  });
}

export function useFieldTrend(
  plotId: string | null | undefined,
  options: {
    sourceId: string | undefined;
    indexType: string;
    startDate?: string;
    endDate?: string;
    provider?: 'auto' | 'eos' | 'native';
    cloudMask: CloudMaskOptions;
  },
) {
  const provider = options.provider ?? 'auto';
  return useQuery({
    queryKey:
      plotId && options.sourceId
        ? queryKeys.fieldTrend(
            plotId,
            options.sourceId,
            options.indexType,
            options.startDate,
            options.endDate,
            provider,
            options.cloudMask,
          )
        : (['fields', 'none', 'trend'] as const),
    queryFn: () =>
      getFieldTrend(plotId as string, {
        sourceId: options.sourceId,
        indexType: options.indexType,
        startDate: options.startDate,
        endDate: options.endDate,
        provider,
        cloudMask: options.cloudMask,
      }),
    enabled: Boolean(plotId && options.sourceId),
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

export function useExportFieldIndex() {
  return useMutation({
    mutationFn: ({ plotId, options }: FieldIndexExportVariables) =>
      exportFieldIndex(plotId, options),
  });
}

export function useExportFieldReportCsv() {
  return useMutation({
    mutationFn: ({ plotId, options }: FieldReportExportVariables) =>
      exportFieldReportCsv(plotId, options),
  });
}
