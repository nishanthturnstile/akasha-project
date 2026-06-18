import type {
  ApiErrorShape,
  AppConfig,
  DefaultLayer,
  FieldIndexExportOptions,
  FieldReportExportOptions,
  FieldStatisticsRequest,
  FieldStatisticsResponse,
  FieldTrendResponse,
  FileDownload,
  FieldLeaderboardFilters,
  FieldLeaderboardResponse,
  FieldActivity,
  FieldActivityPayload,
  FieldActivityUpdatePayload,
  ActivityFilters,
  ReportTemplate,
  ReportTemplatePayload,
  ReportTemplateUpdatePayload,
  ScoutTask,
  ScoutTaskPayload,
  ScoutTaskUpdatePayload,
  UploadedDataset,
  FieldGroup,
  FieldGroupPayload,
  FieldIndexOverlayImage,
  FieldIndexPointResponse,
  ImageCorners,
  ConnectionStatus,
  FieldRiskSummaryResponse,
  AccountMe,
  ApiKeyMetadata,
  NotificationItem,
  AssistantStatus,
  CloudMaskOptions,
  ImagerySourceMonitoringResponse,
  Plot,
  PlotCreatePayload,
  PlotGeometry,
  PlotImportResponse,
  PlotUpdatePayload,
  SceneDate,
  Source,
  Season,
  SeasonCreatePayload,
  SeasonUpdatePayload,
  Field,
  FieldCreatePayload,
  FieldUpdatePayload,
  SignupPayload,
} from '@/types/api';

/**
 * Error thrown for any non-2xx `/api/*` response. Carries the BFF error envelope's
 * `code`/`message` so the UI can show a calm, non-internal message.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
}

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

interface GeoJsonFeature {
  [key: string]: unknown;
  type: 'Feature';
  geometry: PlotGeometry;
  properties?: Record<string, unknown> | null;
}

interface GeoJsonFeatureCollection {
  [key: string]: unknown;
  type: 'FeatureCollection';
  features: GeoJsonFeature[];
}

export type PlotGeoJsonImportPayload = PlotGeometry | GeoJsonFeature | GeoJsonFeatureCollection;

function isBodyInit(body: unknown): body is BodyInit {
  return (
    typeof body === 'string' ||
    body instanceof Blob ||
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body) ||
    (typeof ReadableStream !== 'undefined' && body instanceof ReadableStream)
  );
}

function buildRequestInit(options: RequestOptions = {}): RequestInit {
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    if (isBodyInit(options.body)) {
      body = options.body;
    } else {
      body = JSON.stringify(options.body);
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
    }
  }

  return {
    method: options.method ?? 'GET',
    headers,
    body,
    credentials: 'same-origin',
  };
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = 'REQUEST_FAILED';
  let message = `Request failed (${res.status}).`;
  let details: unknown;
  try {
    const body = (await res.json()) as Partial<ApiErrorShape>;
    const err = body?.error;
    if (err) {
      if (typeof err.code === 'string') code = err.code;
      if (typeof err.message === 'string') message = err.message;
      details = err.details;
    }
  } catch {
    // Non-JSON error body — keep sanitized defaults.
  }
  return new ApiError(code, message, res.status, details);
}

async function fetchApi(path: string, options: RequestOptions = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, buildRequestInit(options));
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Unable to reach the Akasha service.', 0);
  }

  if (!res.ok) {
    const error = await toApiError(res);
    if (error.status === 401) {
      unauthorizedHandler?.();
    }
    throw error;
  }

  return res;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await fetchApi(path, options);
  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/geo+json, application/json;q=0.9');
  }

  const res = await fetchApi(path, { ...options, headers });
  const blob = await res.blob();
  if (blob.type) {
    return blob;
  }
  return new Blob([blob], { type: res.headers.get('Content-Type') ?? 'application/geo+json' });
}

function parseOverlayCorners(header: string | null): ImageCorners | null {
  if (!header) return null;
  try {
    const parsed = JSON.parse(header) as unknown;
    if (!Array.isArray(parsed) || parsed.length !== 4) return null;
    const corners = parsed.map((corner) => {
      if (!Array.isArray(corner) || corner.length < 2) return null;
      const lng = Number(corner[0]);
      const lat = Number(corner[1]);
      return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
    });
    if (corners.some((corner) => corner === null)) return null;
    return corners as ImageCorners;
  } catch {
    return null;
  }
}

function parseOverlayStretch(header: string | null): [number, number] | null {
  if (!header) return null;
  const [lo, hi] = header.split(',').map((part) => Number(part.trim()));
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  return [lo, hi];
}

function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const quoted = header.match(/filename="([^"]+)"/i);
  if (quoted?.[1]) return quoted[1];
  const plain = header.match(/filename=([^;]+)/i);
  return plain?.[1]?.trim() || fallback;
}

async function requestDownload(
  path: string,
  fallbackFilename: string,
  options: RequestOptions = {},
): Promise<FileDownload> {
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/octet-stream, text/csv;q=0.9, application/geo+json;q=0.8');
  }

  const res = await fetchApi(path, { ...options, headers });
  const blob = await res.blob();
  return {
    blob: blob.type
      ? blob
      : new Blob([blob], { type: res.headers.get('Content-Type') ?? 'application/octet-stream' }),
    filename: filenameFromContentDisposition(
      res.headers.get('Content-Disposition'),
      fallbackFilename,
    ),
  };
}

export const getConfig = (): Promise<AppConfig> => request<AppConfig>('/api/config');

export const getSources = (): Promise<Source[]> => request<Source[]>('/api/sources');

const SOURCE_DATE_LOOKBACK_DAYS = 92;

export const getDates = (sourceId: string): Promise<SceneDate[]> =>
  request<SceneDate[]>(
    `/api/sources/${encodeURIComponent(sourceId)}/dates?lookbackDays=${SOURCE_DATE_LOOKBACK_DAYS}`,
  );

export const getImagerySourceMonitoring = (): Promise<ImagerySourceMonitoringResponse> =>
  request<ImagerySourceMonitoringResponse>('/api/monitoring/imagery-sources');

export const getDefaultLayer = (): Promise<DefaultLayer> =>
  request<DefaultLayer>('/api/layers/default');

export const getPlots = (): Promise<Plot[]> => request<Plot[]>('/api/plots');

export const createPlot = (payload: PlotCreatePayload): Promise<Plot> =>
  request<Plot>('/api/plots', { method: 'POST', body: payload });

export const updatePlot = (plotId: string, payload: PlotUpdatePayload): Promise<Plot> =>
  request<Plot>(`/api/plots/${encodeURIComponent(plotId)}`, { method: 'PATCH', body: payload });

export const deletePlot = (plotId: string): Promise<void> =>
  request<void>(`/api/plots/${encodeURIComponent(plotId)}`, { method: 'DELETE' });

export const importPlotsGeoJson = (
  payload: PlotGeoJsonImportPayload,
): Promise<PlotImportResponse> =>
  request<PlotImportResponse>('/api/plots/import/geojson', { method: 'POST', body: payload });

export const exportAllPlotsGeoJson = (): Promise<Blob> =>
  requestBlob('/api/plots/export.geojson');

export const exportPlotGeoJson = (plotId: string): Promise<Blob> =>
  requestBlob(`/api/plots/${encodeURIComponent(plotId)}/export.geojson`);

// --------------------------------------------------------------------------
// Seasons API
// --------------------------------------------------------------------------
export const listSeasons = (): Promise<Season[]> => request<Season[]>('/api/seasons');

export const createSeason = (payload: SeasonCreatePayload): Promise<Season> =>
  request<Season>('/api/seasons', { method: 'POST', body: payload });

export const getSeason = (seasonId: string): Promise<Season> =>
  request<Season>(`/api/seasons/${encodeURIComponent(seasonId)}`);

export const updateSeason = (seasonId: string, payload: SeasonUpdatePayload): Promise<Season> =>
  request<Season>(`/api/seasons/${encodeURIComponent(seasonId)}`, { method: 'PATCH', body: payload });

export const deleteSeason = (seasonId: string): Promise<void> =>
  request<void>(`/api/seasons/${encodeURIComponent(seasonId)}`, { method: 'DELETE' });

// --------------------------------------------------------------------------
// Fields API
// --------------------------------------------------------------------------
export const listFields = (): Promise<Field[]> => request<Field[]>('/api/fields');

export const createField = (payload: FieldCreatePayload): Promise<Field> =>
  request<Field>('/api/fields', { method: 'POST', body: payload });

export const getField = (fieldId: string): Promise<Field> =>
  request<Field>(`/api/fields/${encodeURIComponent(fieldId)}`);

export const updateField = (fieldId: string, payload: FieldUpdatePayload): Promise<Field> =>
  request<Field>(`/api/fields/${encodeURIComponent(fieldId)}`, { method: 'PATCH', body: payload });

export const deleteField = (fieldId: string): Promise<void> =>
  request<void>(`/api/fields/${encodeURIComponent(fieldId)}`, { method: 'DELETE' });

export const getFieldStatistics = (
  plotId: string,
  payload: FieldStatisticsRequest,
): Promise<FieldStatisticsResponse> =>
  request<FieldStatisticsResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/indices/statistics`,
    { method: 'POST', body: payload },
  );

export const getFieldTrend = (
  plotId: string,
  options: {
    indexType: string;
    sourceId?: string;
    startDate?: string;
    endDate?: string;
    cloudMask?: CloudMaskOptions;
  },
): Promise<FieldTrendResponse> => {
  const params = new URLSearchParams({
    indexType: options.indexType,
  });
  if (options.sourceId) params.set('sourceId', options.sourceId);
  if (options.startDate) params.set('startDate', options.startDate);
  if (options.endDate) params.set('endDate', options.endDate);
  if (options.cloudMask) {
    params.set('clouds', String(options.cloudMask.clouds));
    params.set('cloudShadows', String(options.cloudMask.cloudShadows));
    params.set('cirrus', String(options.cloudMask.cirrus));
  }
  return request<FieldTrendResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/analytics/trend?${params.toString()}`,
  );
};

export const getFieldIndexOverlayImage = async (
  plotId: string,
  options: { sourceId: string; acquisitionDate: string; indexType: string; preferHighRes?: boolean },
  fallbackCoordinates: ImageCorners,
): Promise<FieldIndexOverlayImage> => {
  const params = new URLSearchParams({
    sourceId: options.sourceId,
    acquisitionDate: options.acquisitionDate,
  });
  if (options.preferHighRes !== undefined) {
    params.set('preferHighRes', String(options.preferHighRes));
  }
  const sourceUrl = `/api/fields/${encodeURIComponent(plotId)}/overlay/${encodeURIComponent(
    options.indexType,
  )}.png?${params.toString()}`;
  const headers = new Headers({ Accept: 'image/png' });
  const res = await fetchApi(sourceUrl, { headers });
  const blob = await res.blob();
  const typedBlob = blob.type ? blob : new Blob([blob], { type: 'image/png' });
  const resolvedResStr = res.headers.get('X-Akasha-Resolved-Resolution');
  const resolvedResNum = resolvedResStr != null ? Number(resolvedResStr) : null;
  return {
    url: URL.createObjectURL(typedBlob),
    sourceUrl,
    coordinates: parseOverlayCorners(res.headers.get('X-Akasha-Overlay-Corners')) ?? fallbackCoordinates,
    stretch: parseOverlayStretch(res.headers.get('X-Akasha-Overlay-Stretch')),
    resolvedSourceId: res.headers.get('X-Akasha-Resolved-Source') ?? null,
    resolutionMeters: resolvedResNum != null && Number.isFinite(resolvedResNum) ? resolvedResNum : null,
    enhanced: res.headers.get('X-Akasha-Enhanced') === 'true',
    basisDate: res.headers.get('X-Akasha-Basis-Date') ?? null,
  };
};

export const getFieldIndexPoint = (
  plotId: string,
  options: {
    sourceId: string;
    acquisitionDate: string;
    indexType: string;
    lng: number;
    lat: number;
    preferHighRes?: boolean;
  },
): Promise<FieldIndexPointResponse> => {
  const params = new URLSearchParams({
    sourceId: options.sourceId,
    acquisitionDate: options.acquisitionDate,
    indexType: options.indexType,
    lng: String(options.lng),
    lat: String(options.lat),
  });
  if (options.preferHighRes !== undefined) {
    params.set('preferHighRes', String(options.preferHighRes));
  }
  return request<FieldIndexPointResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/indices/point?${params.toString()}`,
  );
};

function appendLeaderboardParams(params: URLSearchParams, filters: FieldLeaderboardFilters = {}) {
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    params.set(key, String(value));
  });
}

export const getFieldLeaderboard = (
  filters: FieldLeaderboardFilters = {},
): Promise<FieldLeaderboardResponse> => {
  const params = new URLSearchParams();
  appendLeaderboardParams(params, filters);
  const query = params.toString();
  return request<FieldLeaderboardResponse>(
    `/api/reports/field-leaderboard${query ? `?${query}` : ''}`,
  );
};

export const exportFieldLeaderboardCsv = (
  filters: FieldLeaderboardFilters = {},
  options: { templateId?: string; columns?: string[] } = {},
): Promise<FileDownload> => {
  const params = new URLSearchParams();
  appendLeaderboardParams(params, filters);
  if (options.templateId) params.set('templateId', options.templateId);
  options.columns?.forEach((column) => params.append('columns', column));
  const query = params.toString();
  return requestDownload(
    `/api/reports/field-leaderboard/export.csv${query ? `?${query}` : ''}`,
    'field-leaderboard.csv',
  );
};

export const listReportTemplates = (): Promise<ReportTemplate[]> =>
  request<ReportTemplate[]>('/api/reports/templates');

export const getReportTemplate = (templateId: string): Promise<ReportTemplate> =>
  request<ReportTemplate>(`/api/reports/templates/${encodeURIComponent(templateId)}`);

export const createReportTemplate = (payload: ReportTemplatePayload): Promise<ReportTemplate> =>
  request<ReportTemplate>('/api/reports/templates', { method: 'POST', body: payload });

export const updateReportTemplate = (
  templateId: string,
  payload: ReportTemplateUpdatePayload,
): Promise<ReportTemplate> =>
  request<ReportTemplate>(
    `/api/reports/templates/${encodeURIComponent(templateId)}`,
    { method: 'PATCH', body: payload },
  );

function appendParams(params: URLSearchParams, values: object = {}) {
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    params.set(key, String(value));
  });
}

export const listActivities = (filters: ActivityFilters = {}): Promise<FieldActivity[]> => {
  const params = new URLSearchParams();
  appendParams(params, filters);
  const query = params.toString();
  return request<FieldActivity[]>(`/api/activities${query ? `?${query}` : ''}`);
};

export const createFieldActivity = (
  plotId: string,
  payload: FieldActivityPayload,
): Promise<FieldActivity> =>
  request<FieldActivity>(`/api/fields/${encodeURIComponent(plotId)}/activities`, {
    method: 'POST',
    body: payload,
  });

export const updateFieldActivity = (
  activityId: string,
  payload: FieldActivityUpdatePayload,
): Promise<FieldActivity> =>
  request<FieldActivity>(`/api/activities/${encodeURIComponent(activityId)}`, {
    method: 'PATCH',
    body: payload,
  });

export const exportActivitiesCsv = (filters: ActivityFilters = {}): Promise<FileDownload> => {
  const params = new URLSearchParams();
  appendParams(params, filters);
  const query = params.toString();
  return requestDownload(`/api/activities/export.csv${query ? `?${query}` : ''}`, 'field-activities.csv');
};

export const listScoutTasks = (filters: { status?: string; search?: string; plotId?: string } = {}): Promise<ScoutTask[]> => {
  const params = new URLSearchParams();
  appendParams(params, filters);
  const query = params.toString();
  return request<ScoutTask[]>(`/api/scout-tasks${query ? `?${query}` : ''}`);
};

export const createScoutTask = (payload: ScoutTaskPayload): Promise<ScoutTask> =>
  request<ScoutTask>('/api/scout-tasks', { method: 'POST', body: payload });

export const updateScoutTask = (
  taskId: string,
  payload: ScoutTaskUpdatePayload,
): Promise<ScoutTask> =>
  request<ScoutTask>(`/api/scout-tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    body: payload,
  });

export const listDatasets = (): Promise<UploadedDataset[]> =>
  request<UploadedDataset[]>('/api/datasets');

export const uploadDataset = (
  file: File,
  datasetType?: UploadedDataset['datasetType'],
): Promise<UploadedDataset> => {
  const form = new FormData();
  form.set('file', file);
  if (datasetType) form.set('datasetType', datasetType);
  return request<UploadedDataset>('/api/datasets/upload', { method: 'POST', body: form });
};

export const getJohnDeereConnection = (): Promise<ConnectionStatus> =>
  request<ConnectionStatus>('/api/connections/john-deere');

export const getFieldRiskSummary = (
  plotId: string,
  options: { indexType?: string; sourceId?: string } = {},
): Promise<FieldRiskSummaryResponse> => {
  const params = new URLSearchParams();
  if (options.indexType) params.set('indexType', options.indexType);
  if (options.sourceId) params.set('sourceId', options.sourceId);
  const query = params.toString();
  return request<FieldRiskSummaryResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/risk/summary${query ? `?${query}` : ''}`,
  );
};

export const getAccountMe = (): Promise<AccountMe> => request<AccountMe>('/api/account/me');

export const login = (payload: {
  username: string;
  password: string;
  rememberMe?: boolean;
}): Promise<AccountMe> =>
  request<AccountMe>('/api/auth/login', { method: 'POST', body: payload });

export const signup = (payload: SignupPayload): Promise<AccountMe> =>
  request<AccountMe>('/api/auth/signup', { method: 'POST', body: payload });

export const logout = (): Promise<void> =>
  request<void>('/api/auth/logout', { method: 'POST' });

export const refreshSession = (): Promise<AccountMe> =>
  request<AccountMe>('/api/auth/refresh', { method: 'POST' });

export const changePassword = (payload: {
  currentPassword: string;
  newPassword: string;
}): Promise<{ changed: boolean }> =>
  request<{ changed: boolean }>('/api/account/password', { method: 'PATCH', body: payload });

export const completeOnboarding = (): Promise<AccountMe> =>
  request<AccountMe>('/api/account/onboarding-complete', { method: 'POST' });

export const getAccountSettings = (): Promise<Record<string, unknown>> =>
  request<Record<string, unknown>>('/api/account/settings');

export const listApiKeys = (): Promise<ApiKeyMetadata[]> =>
  request<ApiKeyMetadata[]>('/api/account/api-keys');

export const createApiKey = (name: string): Promise<ApiKeyMetadata> =>
  request<ApiKeyMetadata>('/api/account/api-keys', { method: 'POST', body: { name } });

export const revokeApiKey = (keyId: string): Promise<void> =>
  request<void>(`/api/account/api-keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' });

export const listNotifications = (unreadOnly = false): Promise<NotificationItem[]> =>
  request<NotificationItem[]>(`/api/notifications${unreadOnly ? '?unreadOnly=true' : ''}`);

export const getNotificationUnreadCount = (): Promise<{ unreadCount: number }> =>
  request<{ unreadCount: number }>('/api/notifications/unread-count');

export const markNotificationRead = (notificationId: string): Promise<NotificationItem> =>
  request<NotificationItem>(`/api/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'POST',
  });

export const markAllNotificationsRead = (): Promise<{ updatedCount: number }> =>
  request<{ updatedCount: number }>('/api/notifications/read-all', { method: 'POST' });

export const getAssistantStatus = (): Promise<AssistantStatus> =>
  request<AssistantStatus>('/api/assistant/status');

export const listFieldGroups = (): Promise<FieldGroup[]> =>
  request<FieldGroup[]>('/api/field-groups');

export const createFieldGroup = (payload: FieldGroupPayload): Promise<FieldGroup> =>
  request<FieldGroup>('/api/field-groups', { method: 'POST', body: payload });

export const updateFieldGroup = (groupId: string, payload: FieldGroupPayload): Promise<FieldGroup> =>
  request<FieldGroup>(`/api/field-groups/${encodeURIComponent(groupId)}`, {
    method: 'PATCH',
    body: payload,
  });

export const deleteFieldGroup = (groupId: string): Promise<void> =>
  request<void>(`/api/field-groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' });

export const assignFieldGroupFields = (groupId: string, plotIds: string[]): Promise<FieldGroup> =>
  request<FieldGroup>(`/api/field-groups/${encodeURIComponent(groupId)}/fields`, {
    method: 'POST',
    body: { plotIds },
  });

export const exportFieldIndex = (
  plotId: string,
  options: FieldIndexExportOptions,
): Promise<FileDownload> => {
  const params = new URLSearchParams({
    format: options.format,
    sourceId: options.sourceId,
    acquisitionDate: options.acquisitionDate,
    indexType: options.indexType,
  });
  if (options.cloudMask) {
    params.set('clouds', String(options.cloudMask.clouds));
    params.set('cloudShadows', String(options.cloudMask.cloudShadows));
    params.set('cirrus', String(options.cloudMask.cirrus));
  }
  const suffix = options.format === 'geotiff' ? 'tiff' : options.format;
  return requestDownload(
    `/api/fields/${encodeURIComponent(plotId)}/exports/index?${params.toString()}`,
    `field_${options.acquisitionDate}_${options.indexType}.${suffix}`,
  );
};

export const exportFieldReportCsv = (
  plotId: string,
  options: FieldReportExportOptions,
): Promise<FileDownload> => {
  const params = new URLSearchParams({
    sourceId: options.sourceId,
    indexType: options.indexType,
  });
  if (options.startDate) params.set('startDate', options.startDate);
  if (options.endDate) params.set('endDate', options.endDate);
  if (options.cloudMask) {
    params.set('clouds', String(options.cloudMask.clouds));
    params.set('cloudShadows', String(options.cloudMask.cloudShadows));
    params.set('cirrus', String(options.cloudMask.cirrus));
  }
  return requestDownload(
    `/api/fields/${encodeURIComponent(plotId)}/exports/report.csv?${params.toString()}`,
    `field_${options.indexType}_analytics.csv`,
  );
};

/** Compose the same-origin tile template for an arbitrary source/date/display-mode selection. */
export function composeTileTemplate(
  sourceId: string,
  acquisitionDate: string,
  displayMode = 'FCC',
): string {
  return `/api/tiles/${encodeURIComponent(sourceId)}/${encodeURIComponent(
    acquisitionDate,
  )}/${encodeURIComponent(displayMode)}/{z}/{x}/{y}.png`;
}
