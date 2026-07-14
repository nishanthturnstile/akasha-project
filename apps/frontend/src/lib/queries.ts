import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPlot,
  deletePlot,
  exportFieldIndex,
  exportFieldReportCsv,
  getFieldStatistics,
  getFieldTrend,
  createReportTemplate,
  createFieldActivity,
  createFieldGroup,
  createScoutTask,
  assignFieldGroupFields,
  deleteFieldGroup,
  exportFieldLeaderboardCsv,
  exportActivitiesCsv,
  getJohnDeereConnection,
  getFieldRiskSummary,
  createApiKey,
  changePassword,
  getAccountMe,
  getAccountSettings,
  getAssistantStatus,
  getNotificationUnreadCount,
  getFieldLeaderboard,
  getReportTemplate,
  getImagerySourceMonitoring,
  listActivities,
  listApiKeys,
  listDatasets,
  listFieldGroups,
  listNotifications,
  listScoutTasks,
  listReportTemplates,
  uploadDataset,
  markAllNotificationsRead,
  markNotificationRead,
  revokeApiKey,
  updateFieldGroup,
  updateFieldActivity,
  updateScoutTask,
  updateReportTemplate,
  getIngestionSchedules,
  getIngestionSources,
  getIngestionSourceProducts,
  triggerIngestionJob,
  listIngestionJobs,
  getIngestionJob,
  getIngestionJobEvents,
  getConfig,
  getCrops,
  getDates,
  getPredefinedSeasons,
  getBestObservations,
  getDefaultLayer,
  getIrrigationTypes,
  getPlots,
  getSources,
  getTillageTypes,
  getVarieties,
  importPlotsGeoJson,
  login,
  signup,
  logout,
  refreshSession,
  completeOnboarding,
  updatePlot,
  getSeason,
  listSeasons,
  createSeason,
  updateSeason,
  deleteSeason,
  listFields,
  createField,
  updateField,
  deleteField,
} from '@/lib/api';
import type {
  CloudMaskOptions,
  FieldIndexExportOptions,
  FieldReportExportOptions,
  PlotUpdatePayload,
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
  SeasonCreatePayload,
  SeasonUpdatePayload,
  FieldCreatePayload,
  FieldUpdatePayload,
  SignupPayload,
  IngestionJobFilters,
  TriggerIngestionJobRequest,
  BestObservationsParams,
} from '@/types/api';

export const queryKeys = {
  config: ['config'] as const,
  sources: ['sources'] as const,
  dates: (sourceId: string, fieldId?: string, indexType?: string) =>
    ['dates', sourceId, fieldId ?? 'global', indexType ?? 'default'] as const,
  defaultLayer: (sourceId: string) => ['layers', 'default', sourceId] as const,
  crops: ['crops'] as const,
  predefinedSeasons: ['predefined-seasons'] as const,
  irrigationTypes: ['irrigation-types'] as const,
  tillageTypes: ['tillage-types'] as const,
  varieties: (cropId: number) => ['varieties', cropId] as const,
  plots: ['plots'] as const,
  fieldStatistics: (
    plotId: string,
    sourceId: string,
    acquisitionDate: string | null | undefined,
    indexType: string,
    cloudMask: CloudMaskOptions,
    preferHighRes?: boolean,
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
      preferHighRes ?? true,
    ] as const,
  fieldTrend: (
    plotId: string,
    sourceId: string,
    indexType: string,
    startDate: string | undefined,
    endDate: string | undefined,
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
      cloudMask.clouds,
      cloudMask.cloudShadows,
      cloudMask.cirrus,
    ] as const,
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
  accountMe: ['account', 'me'] as const,
  accountSettings: ['account', 'settings'] as const,
  apiKeys: ['account', 'api-keys'] as const,
  notifications: (unreadOnly: boolean) => ['notifications', unreadOnly] as const,
  notificationUnreadCount: ['notifications', 'unread-count'] as const,
  assistantStatus: ['assistant', 'status'] as const,
  imagerySourceMonitoring: ['monitoring', 'imagery-sources'] as const,
  ingestionSchedules: ['monitoring', 'ingestion-schedules'] as const,
  ingestionSources: ['monitoring', 'ingestion-sources'] as const,
  ingestionSourceProducts: (sourceId: string, limit = 25) =>
    ['monitoring', 'ingestion-sources', sourceId, 'products', limit] as const,
  ingestionJobs: (filters?: IngestionJobFilters) =>
    ['monitoring', 'ingestion-jobs', filters ?? {}] as const,
  ingestionJob: (jobId: string) => ['monitoring', 'ingestion-jobs', jobId] as const,
  ingestionJobEvents: (jobId: string) =>
    ['monitoring', 'ingestion-jobs', jobId, 'events'] as const,
  seasons: ['seasons'] as const,
  season: (seasonId: string) => ['seasons', seasonId] as const,
  fields: ['fields'] as const,
  field: (fieldId: string) => ['fields', fieldId] as const,
  bestObservations: (params: BestObservationsParams) =>
    ['observations', 'best', params] as const,
};

interface LoginVariables {
  username: string;
  password: string;
  rememberMe?: boolean;
}

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

export function useDates(
  sourceId: string | undefined,
  options?: { enabled?: boolean; fieldId?: string; indexType?: string },
) {
  return useQuery({
    queryKey: sourceId
      ? queryKeys.dates(sourceId, options?.fieldId, options?.indexType)
      : (['dates', 'none'] as const),
    queryFn: () => getDates(sourceId as string, {
      fieldId: options?.fieldId,
      indexType: options?.indexType,
    }),
    enabled: Boolean(sourceId) && options?.enabled !== false,
  });
}

export function useDefaultLayer(sourceId: string | undefined) {
  return useQuery({
    queryKey: sourceId ? queryKeys.defaultLayer(sourceId) : (['layers', 'default', 'none'] as const),
    queryFn: () => getDefaultLayer(sourceId as string),
    enabled: Boolean(sourceId),
  });
}


export function useCrops() {
  return useQuery({ queryKey: queryKeys.crops, queryFn: getCrops });
}

export function usePredefinedSeasons() {
  return useQuery({ queryKey: queryKeys.predefinedSeasons, queryFn: getPredefinedSeasons });
}

export function useIrrigationTypes() {
  return useQuery({ queryKey: queryKeys.irrigationTypes, queryFn: getIrrigationTypes });
}

export function useTillageTypes() {
  return useQuery({ queryKey: queryKeys.tillageTypes, queryFn: getTillageTypes });
}

export function useVarieties(cropId: number | undefined) {
  return useQuery({
    queryKey: cropId ? queryKeys.varieties(cropId) : (['varieties', 'none'] as const),
    queryFn: () => getVarieties(cropId as number),
    enabled: Boolean(cropId),
  });
}


/**
 * Best-available observations across active sources (Phase 11 / TASK-070).
 * Disabled by default — enable explicitly via `options.enabled = true`.
 */
export function useBestObservations(
  params: BestObservationsParams = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.bestObservations(params),
    queryFn: () => getBestObservations(params),
    enabled: options?.enabled === true,
    staleTime: 60 * 1000,
  });
}


export function useImagerySourceMonitoring() {
  return useQuery({
    queryKey: queryKeys.imagerySourceMonitoring,
    queryFn: getImagerySourceMonitoring,
    staleTime: 60 * 1000,
  });
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

export function useFieldStatistics(
  plotId: string | null | undefined,
  options: {
    sourceId: string | undefined;
    acquisitionDate: string | null | undefined;
    indexType: string;
    cloudMask: CloudMaskOptions;
    preferHighRes?: boolean;
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
          options.preferHighRes,
        )
        : (['fields', 'none', 'statistics'] as const),
    queryFn: () =>
      getFieldStatistics(plotId as string, {
        sourceId: options.sourceId as string,
        acquisitionDate: options.acquisitionDate,
        indexType: options.indexType,
        cloudMask: options.cloudMask,
        preferHighRes: options.preferHighRes,
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
    cloudMask: CloudMaskOptions;
  },
) {
  return useQuery({
    queryKey:
      plotId && options.sourceId
        ? queryKeys.fieldTrend(
          plotId,
          options.sourceId,
          options.indexType,
          options.startDate,
          options.endDate,
          options.cloudMask,
        )
        : (['fields', 'none', 'trend'] as const),
    queryFn: () =>
      getFieldTrend(plotId as string, {
        sourceId: options.sourceId,
        indexType: options.indexType,
        startDate: options.startDate,
        endDate: options.endDate,
        cloudMask: options.cloudMask,
      }),
    enabled: Boolean(plotId && options.sourceId),
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

export function useAccountMe() {
  return useQuery({ queryKey: queryKeys.accountMe, queryFn: getAccountMe });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LoginVariables) => login(payload),
    onSuccess: (account) => queryClient.setQueryData(queryKeys.accountMe, account),
  });
}

export function useSignup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SignupPayload) => signup(payload),
    onSuccess: (account) => queryClient.setQueryData(queryKeys.accountMe, account),
  });
}

export function useLogout() {
  // The cached account/session state is intentionally cleared by the caller
  // AFTER it navigates away from protected routes. Clearing here (on success)
  // refetches `account/me` while the app shell is still mounted, which races
  // with logout teardown and aborts the in-flight logout request.
  return useMutation({
    mutationFn: logout,
  });
}

export function useRefreshSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: refreshSession,
    onSuccess: (account) => queryClient.setQueryData(queryKeys.accountMe, account),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: { currentPassword: string; newPassword: string }) =>
      changePassword(payload),
  });
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: completeOnboarding,
    onSuccess: (account) => queryClient.setQueryData(queryKeys.accountMe, account),
  });
}

export function useAccountSettings() {
  return useQuery({ queryKey: queryKeys.accountSettings, queryFn: getAccountSettings });
}

export function useApiKeys() {
  return useQuery({ queryKey: queryKeys.apiKeys, queryFn: listApiKeys });
}

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createApiKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys }),
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys }),
  });
}

export function useNotifications(unreadOnly = false) {
  return useQuery({
    queryKey: queryKeys.notifications(unreadOnly),
    queryFn: () => listNotifications(unreadOnly),
  });
}

export function useNotificationUnreadCount() {
  return useQuery({
    queryKey: queryKeys.notificationUnreadCount,
    queryFn: getNotificationUnreadCount,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });
}

export function useAssistantStatus() {
  return useQuery({ queryKey: queryKeys.assistantStatus, queryFn: getAssistantStatus });
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

// --------------------------------------------------------------------------
// Seasons hooks
// --------------------------------------------------------------------------
export function useSeason(seasonId: string | null) {
  return useQuery({
    queryKey: queryKeys.season(seasonId ?? '__skip__'),
    queryFn: () => getSeason(seasonId!),
    enabled: !!seasonId,
  });
}

export function useSeasons() {
  return useQuery({ queryKey: queryKeys.seasons, queryFn: listSeasons });
}

export function useCreateSeason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SeasonCreatePayload) => createSeason(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
    },
  });
}

export function useUpdateSeason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ seasonId, payload }: { seasonId: string; payload: SeasonUpdatePayload }) =>
      updateSeason(seasonId, payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
      void queryClient.invalidateQueries({ queryKey: queryKeys.season(data.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
    },
  });
}

export function useDeleteSeason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { seasonId: string; moveFieldsToSeasonId?: string }) =>
      deleteSeason(args.seasonId, args.moveFieldsToSeasonId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
    },
  });
}

// --------------------------------------------------------------------------
// Fields hooks
// --------------------------------------------------------------------------
export function useFields() {
  return useQuery({ queryKey: queryKeys.fields, queryFn: listFields });
}

export function useCreateField() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FieldCreatePayload) => createField(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
    },
  });
}

export function useUpdateField() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ fieldId, payload }: { fieldId: string; payload: FieldUpdatePayload }) =>
      updateField(fieldId, payload),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
      void queryClient.invalidateQueries({ queryKey: queryKeys.field(data.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
    },
  });
}

export function useDeleteField() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteField,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields });
      void queryClient.invalidateQueries({ queryKey: queryKeys.seasons });
    },
  });
}

// --------------------------------------------------------------------------
// Ingestion scheduler monitoring hooks
// --------------------------------------------------------------------------
export function useIngestionSchedules() {
  return useQuery({
    queryKey: queryKeys.ingestionSchedules,
    queryFn: getIngestionSchedules,
  });
}

export function useIngestionSources() {
  return useQuery({
    queryKey: queryKeys.ingestionSources,
    queryFn: getIngestionSources,
  });
}

export function useIngestionSourceProducts(
  sourceId: string,
  options: { enabled?: boolean; limit?: number } = {},
) {
  const limit = options.limit ?? 25;
  return useQuery({
    queryKey: queryKeys.ingestionSourceProducts(sourceId, limit),
    queryFn: () => getIngestionSourceProducts(sourceId, limit),
    enabled: (options.enabled ?? true) && Boolean(sourceId),
  });
}

export function useIngestionJobs(filters?: IngestionJobFilters) {
  return useQuery({
    queryKey: queryKeys.ingestionJobs(filters),
    queryFn: () => listIngestionJobs(filters),
  });
}

export function useTriggerIngestionJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerIngestionJobRequest) => triggerIngestionJob(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.ingestionJobs() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.ingestionSchedules });
      void queryClient.invalidateQueries({ queryKey: queryKeys.ingestionSources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.imagerySourceMonitoring });
    },
  });
}

export function useIngestionJob(jobId: string) {
  return useQuery({
    queryKey: queryKeys.ingestionJob(jobId),
    queryFn: () => getIngestionJob(jobId),
    enabled: Boolean(jobId),
  });
}

export function useIngestionJobEvents(jobId: string) {
  return useQuery({
    queryKey: queryKeys.ingestionJobEvents(jobId),
    queryFn: () => getIngestionJobEvents(jobId),
    enabled: Boolean(jobId),
  });
}
