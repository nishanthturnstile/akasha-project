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
  getConfig,
  getDates,
  getDefaultLayer,
  getPlots,
  getSources,
  importPlotsGeoJson,
  login,
  signup,
  logout,
  refreshSession,
  completeOnboarding,
  updatePlot,
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
} from '@/types/api';

export const queryKeys = {
  config: ['config'] as const,
  sources: ['sources'] as const,
  dates: (sourceId: string) => ['dates', sourceId] as const,
  defaultLayer: ['layers', 'default'] as const,
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
  seasons: ['seasons'] as const,
  season: (seasonId: string) => ['seasons', seasonId] as const,
  fields: ['fields'] as const,
  field: (fieldId: string) => ['fields', fieldId] as const,
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
export function useSeasons() {
  return useQuery({ queryKey: queryKeys.seasons, queryFn: listSeasons });
}

export function useCreateSeason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SeasonCreatePayload) => createSeason(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.seasons }),
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
    },
  });
}

export function useDeleteSeason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteSeason,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.seasons }),
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
