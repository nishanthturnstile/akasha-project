import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlot,
  deletePlot,
  exportFieldIndex,
  exportFieldReportCsv,
  getFieldScenes,
  getFieldStatistics,
  getFieldTrend,
  getFieldWeatherForecast,
  getFieldWeatherHistory,
  getFieldWeatherSoilMoisture,
  createVegetationZoning,
  createReportTemplate,
  createFieldActivity,
  createFieldGroup,
  createScoutTask,
  assignFieldGroupFields,
  deleteFieldGroup,
  exportZoningMap,
  exportFieldLeaderboardCsv,
  exportActivitiesCsv,
  getJohnDeereConnection,
  getFieldRiskSummary,
  getFieldLeaderboard,
  getReportTemplate,
  getZoningMap,
  listActivities,
  listDatasets,
  listFieldGroups,
  listScoutTasks,
  listZoningMaps,
  listReportTemplates,
  uploadDataset,
  updateFieldGroup,
  updateFieldActivity,
  updateScoutTask,
  updateReportTemplate,
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
  WeatherProviderChoice,
  WeatherSeriesId,
  VegetationZoningRequest,
  ZoningExportFormat,
  FieldLeaderboardFilters,
  ReportTemplatePayload,
  ReportTemplateUpdatePayload,
  ActivityFilters,
  FieldActivityPayload,
  FieldActivityUpdatePayload,
  FieldGroupPayload,
  ScoutTaskPayload,
  ScoutTaskUpdatePayload,
  UploadedDataset,
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
  fieldWeatherForecast: (plotId: string, provider: WeatherProviderChoice, days: number) =>
    ['fields', plotId, 'weather', 'forecast', provider, days] as const,
  fieldWeatherHistory: (
    plotId: string,
    provider: WeatherProviderChoice,
    startDate: string | undefined,
    endDate: string | undefined,
    parameters: readonly WeatherSeriesId[] | undefined,
  ) =>
    [
      'fields',
      plotId,
      'weather',
      'history',
      provider,
      startDate ?? 'default-start',
      endDate ?? 'default-end',
      ...(parameters ?? []),
    ] as const,
  fieldWeatherSoilMoisture: (
    plotId: string,
    provider: WeatherProviderChoice,
    startDate: string | undefined,
    endDate: string | undefined,
  ) =>
    [
      'fields',
      plotId,
      'weather',
      'soil-moisture',
      provider,
      startDate ?? 'default-start',
      endDate ?? 'default-end',
    ] as const,
  zoningMaps: (plotId: string) => ['fields', plotId, 'zoning', 'maps'] as const,
  zoningMap: (plotId: string, mapId: string) =>
    ['fields', plotId, 'zoning', 'maps', mapId] as const,
  fieldLeaderboard: (filters: FieldLeaderboardFilters) =>
    ['reports', 'field-leaderboard', filters] as const,
  reportTemplates: ['reports', 'templates'] as const,
  reportTemplate: (templateId: string) => ['reports', 'templates', templateId] as const,
  fieldRiskSummary: (plotId: string, indexType: string) =>
    ['fields', plotId, 'risk', 'summary', indexType] as const,
  activities: (filters: ActivityFilters) => ['operations', 'activities', filters] as const,
  scoutTasks: (filters: Record<string, unknown>) => ['operations', 'scout-tasks', filters] as const,
  datasets: ['data-manager', 'datasets'] as const,
  fieldGroups: ['field-groups'] as const,
  connection: (provider: string) => ['connections', provider] as const,
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

interface CreateVegetationZoningVariables {
  plotId: string;
  payload: VegetationZoningRequest;
}

interface ZoningExportVariables {
  plotId: string;
  mapId: string;
  format: ZoningExportFormat;
}

interface LeaderboardExportVariables {
  filters?: FieldLeaderboardFilters;
  templateId?: string;
  columns?: string[];
}

interface UpdateReportTemplateVariables {
  templateId: string;
  payload: ReportTemplateUpdatePayload;
}

interface CreateActivityVariables {
  plotId: string;
  payload: FieldActivityPayload;
}

interface UpdateActivityVariables {
  activityId: string;
  payload: FieldActivityUpdatePayload;
}

interface UpdateScoutTaskVariables {
  taskId: string;
  payload: ScoutTaskUpdatePayload;
}

interface UpdateFieldGroupVariables {
  groupId: string;
  payload: FieldGroupPayload;
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

export function useFieldWeatherForecast(
  plotId: string | null | undefined,
  options: { provider?: WeatherProviderChoice; days?: number } = {},
) {
  const provider = options.provider ?? 'auto';
  const days = options.days ?? 7;
  return useQuery({
    queryKey: plotId
      ? queryKeys.fieldWeatherForecast(plotId, provider, days)
      : (['fields', 'none', 'weather', 'forecast'] as const),
    queryFn: () => getFieldWeatherForecast(plotId as string, { provider, days }),
    enabled: Boolean(plotId),
  });
}

export function useFieldWeatherHistory(
  plotId: string | null | undefined,
  options: {
    provider?: WeatherProviderChoice;
    startDate?: string;
    endDate?: string;
    parameters?: WeatherSeriesId[];
  } = {},
) {
  const provider = options.provider ?? 'auto';
  return useQuery({
    queryKey: plotId
      ? queryKeys.fieldWeatherHistory(
          plotId,
          provider,
          options.startDate,
          options.endDate,
          options.parameters,
        )
      : (['fields', 'none', 'weather', 'history'] as const),
    queryFn: () =>
      getFieldWeatherHistory(plotId as string, {
        provider,
        startDate: options.startDate,
        endDate: options.endDate,
        parameters: options.parameters,
      }),
    enabled: Boolean(plotId && options.startDate && options.endDate),
  });
}

export function useFieldWeatherSoilMoisture(
  plotId: string | null | undefined,
  options: {
    provider?: WeatherProviderChoice;
    startDate?: string;
    endDate?: string;
  } = {},
) {
  const provider = options.provider ?? 'auto';
  return useQuery({
    queryKey: plotId
      ? queryKeys.fieldWeatherSoilMoisture(
          plotId,
          provider,
          options.startDate,
          options.endDate,
        )
      : (['fields', 'none', 'weather', 'soil-moisture'] as const),
    queryFn: () =>
      getFieldWeatherSoilMoisture(plotId as string, {
        provider,
        startDate: options.startDate,
        endDate: options.endDate,
      }),
    enabled: Boolean(plotId && options.startDate && options.endDate),
  });
}

export function useZoningMaps(plotId: string | null | undefined) {
  return useQuery({
    queryKey: plotId ? queryKeys.zoningMaps(plotId) : (['fields', 'none', 'zoning', 'maps'] as const),
    queryFn: () => listZoningMaps(plotId as string),
    enabled: Boolean(plotId),
  });
}

export function useZoningMap(plotId: string | null | undefined, mapId: string | null | undefined) {
  return useQuery({
    queryKey:
      plotId && mapId
        ? queryKeys.zoningMap(plotId, mapId)
        : (['fields', 'none', 'zoning', 'maps', 'none'] as const),
    queryFn: () => getZoningMap(plotId as string, mapId as string),
    enabled: Boolean(plotId && mapId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'processing' || status === 'unknown' ? 5000 : false;
    },
  });
}

export function useCreateVegetationZoning() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ plotId, payload }: CreateVegetationZoningVariables) =>
      createVegetationZoning(plotId, payload),
    onSuccess: (data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.zoningMaps(variables.plotId) });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.zoningMap(variables.plotId, data.mapId),
      });
    },
  });
}

export function useExportZoningMap() {
  return useMutation({
    mutationFn: ({ plotId, mapId, format }: ZoningExportVariables) =>
      exportZoningMap(plotId, mapId, format),
  });
}

export function useFieldLeaderboard(filters: FieldLeaderboardFilters = {}) {
  return useQuery({
    queryKey: queryKeys.fieldLeaderboard(filters),
    queryFn: () => getFieldLeaderboard(filters),
  });
}

export function useExportFieldLeaderboardCsv() {
  return useMutation({
    mutationFn: ({ filters = {}, templateId, columns }: LeaderboardExportVariables) =>
      exportFieldLeaderboardCsv(filters, { templateId, columns }),
  });
}

export function useReportTemplates() {
  return useQuery({ queryKey: queryKeys.reportTemplates, queryFn: listReportTemplates });
}

export function useReportTemplate(templateId: string | null | undefined) {
  return useQuery({
    queryKey: templateId ? queryKeys.reportTemplate(templateId) : (['reports', 'templates', 'none'] as const),
    queryFn: () => getReportTemplate(templateId as string),
    enabled: Boolean(templateId),
  });
}

export function useCreateReportTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReportTemplatePayload) => createReportTemplate(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.reportTemplates }),
  });
}

export function useUpdateReportTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, payload }: UpdateReportTemplateVariables) =>
      updateReportTemplate(templateId, payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reportTemplates });
      void queryClient.invalidateQueries({ queryKey: queryKeys.reportTemplate(data.id) });
    },
  });
}

export function useActivities(filters: ActivityFilters = {}) {
  return useQuery({
    queryKey: queryKeys.activities(filters),
    queryFn: () => listActivities(filters),
  });
}

export function useCreateFieldActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ plotId, payload }: CreateActivityVariables) =>
      createFieldActivity(plotId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['operations', 'activities'] }),
  });
}

export function useUpdateFieldActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, payload }: UpdateActivityVariables) =>
      updateFieldActivity(activityId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['operations', 'activities'] }),
  });
}

export function useExportActivitiesCsv() {
  return useMutation({ mutationFn: exportActivitiesCsv });
}

export function useScoutTasks(filters: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: queryKeys.scoutTasks(filters),
    queryFn: () => listScoutTasks(filters as { status?: string; search?: string; plotId?: string }),
  });
}

export function useCreateScoutTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ScoutTaskPayload) => createScoutTask(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['operations', 'scout-tasks'] }),
  });
}

export function useUpdateScoutTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, payload }: UpdateScoutTaskVariables) =>
      updateScoutTask(taskId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['operations', 'scout-tasks'] }),
  });
}

export function useDatasets() {
  return useQuery({ queryKey: queryKeys.datasets, queryFn: listDatasets });
}

export function useUploadDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, datasetType }: { file: File; datasetType?: UploadedDataset['datasetType'] }) =>
      uploadDataset(file, datasetType),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.datasets }),
  });
}

export function useJohnDeereConnection() {
  return useQuery({ queryKey: queryKeys.connection('john-deere'), queryFn: getJohnDeereConnection });
}

export function useFieldRiskSummary(
  plotId: string | null | undefined,
  options: { indexType?: string } = {},
) {
  const indexType = options.indexType ?? 'NDVI';
  return useQuery({
    queryKey: plotId
      ? queryKeys.fieldRiskSummary(plotId, indexType)
      : (['fields', 'none', 'risk', 'summary'] as const),
    queryFn: () => getFieldRiskSummary(plotId as string, { indexType }),
    enabled: Boolean(plotId),
  });
}

export function useFieldGroups() {
  return useQuery({ queryKey: queryKeys.fieldGroups, queryFn: listFieldGroups });
}

export function useCreateFieldGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FieldGroupPayload) => createFieldGroup(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.fieldGroups }),
  });
}

export function useUpdateFieldGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, payload }: UpdateFieldGroupVariables) =>
      updateFieldGroup(groupId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.fieldGroups }),
  });
}

export function useDeleteFieldGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteFieldGroup,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.fieldGroups }),
  });
}

export function useAssignFieldGroupFields() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, plotIds }: { groupId: string; plotIds: string[] }) =>
      assignFieldGroupFields(groupId, plotIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.fieldGroups }),
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
