import type {
  ApiErrorShape,
  AppConfig,
  DefaultLayer,
  FieldIndexExportOptions,
  FieldReportExportOptions,
  FieldSceneListResponse,
  FieldStatisticsRequest,
  FieldStatisticsResponse,
  FieldTrendResponse,
  FileDownload,
  FieldLeaderboardFilters,
  FieldLeaderboardResponse,
  WeatherForecastResponse,
  WeatherHistoryResponse,
  WeatherProviderChoice,
  WeatherSeriesId,
  WeatherSoilMoistureResponse,
  VegetationZoningRequest,
  ZoningExportFormat,
  ZoningMap,
  ZoningMapListResponse,
  ReportTemplate,
  ReportTemplatePayload,
  ReportTemplateUpdatePayload,
  CloudMaskOptions,
  Plot,
  PlotCreatePayload,
  PlotGeometry,
  PlotImportResponse,
  PlotUpdatePayload,
  ProviderSyncResponse,
  SceneDate,
  Source,
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
    throw await toApiError(res);
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

export const getDates = (sourceId: string): Promise<SceneDate[]> =>
  request<SceneDate[]>(`/api/sources/${encodeURIComponent(sourceId)}/dates`);

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

export const syncFieldProvider = (plotId: string): Promise<ProviderSyncResponse> =>
  request<ProviderSyncResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/providers/eos/sync`,
    { method: 'POST' },
  );

export const getFieldScenes = (
  plotId: string,
  options: { provider?: 'auto' | 'eos' | 'native'; startDate?: string; endDate?: string } = {},
): Promise<FieldSceneListResponse> => {
  const params = new URLSearchParams();
  if (options.provider) params.set('provider', options.provider);
  if (options.startDate) params.set('startDate', options.startDate);
  if (options.endDate) params.set('endDate', options.endDate);
  const query = params.toString();
  return request<FieldSceneListResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/scenes${query ? `?${query}` : ''}`,
  );
};

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
    provider?: 'auto' | 'eos' | 'native';
    startDate?: string;
    endDate?: string;
    cloudMask?: CloudMaskOptions;
  },
): Promise<FieldTrendResponse> => {
  const params = new URLSearchParams({
    indexType: options.indexType,
  });
  if (options.provider) params.set('provider', options.provider);
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

export const getFieldWeatherForecast = (
  plotId: string,
  options: { provider?: WeatherProviderChoice; days?: number } = {},
): Promise<WeatherForecastResponse> => {
  const params = new URLSearchParams();
  if (options.provider) params.set('provider', options.provider);
  if (options.days) params.set('days', String(options.days));
  const query = params.toString();
  return request<WeatherForecastResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/weather/forecast${query ? `?${query}` : ''}`,
  );
};

export const getFieldWeatherHistory = (
  plotId: string,
  options: {
    provider?: WeatherProviderChoice;
    startDate?: string;
    endDate?: string;
    parameters?: WeatherSeriesId[];
  } = {},
): Promise<WeatherHistoryResponse> => {
  const params = new URLSearchParams();
  if (options.provider) params.set('provider', options.provider);
  if (options.startDate) params.set('startDate', options.startDate);
  if (options.endDate) params.set('endDate', options.endDate);
  options.parameters?.forEach((parameter) => params.append('parameters', parameter));
  const query = params.toString();
  return request<WeatherHistoryResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/weather/history${query ? `?${query}` : ''}`,
  );
};

export const getFieldWeatherSoilMoisture = (
  plotId: string,
  options: {
    provider?: WeatherProviderChoice;
    startDate?: string;
    endDate?: string;
  } = {},
): Promise<WeatherSoilMoistureResponse> => {
  const params = new URLSearchParams();
  if (options.provider) params.set('provider', options.provider);
  if (options.startDate) params.set('startDate', options.startDate);
  if (options.endDate) params.set('endDate', options.endDate);
  const query = params.toString();
  return request<WeatherSoilMoistureResponse>(
    `/api/fields/${encodeURIComponent(plotId)}/weather/soil-moisture${query ? `?${query}` : ''}`,
  );
};

export const createVegetationZoning = (
  plotId: string,
  payload: VegetationZoningRequest,
): Promise<ZoningMap> =>
  request<ZoningMap>(
    `/api/fields/${encodeURIComponent(plotId)}/zoning/vegetation`,
    { method: 'POST', body: payload },
  );

export const listZoningMaps = (plotId: string): Promise<ZoningMapListResponse> =>
  request<ZoningMapListResponse>(`/api/fields/${encodeURIComponent(plotId)}/zoning/maps`);

export const getZoningMap = (plotId: string, mapId: string): Promise<ZoningMap> =>
  request<ZoningMap>(
    `/api/fields/${encodeURIComponent(plotId)}/zoning/maps/${encodeURIComponent(mapId)}`,
  );

export const exportZoningMap = (
  plotId: string,
  mapId: string,
  format: ZoningExportFormat,
): Promise<FileDownload> =>
  requestDownload(
    `/api/fields/${encodeURIComponent(plotId)}/zoning/maps/${encodeURIComponent(mapId)}/export.${format}`,
    `zoning_${mapId}.${format === 'shp' ? 'zip' : 'geojson'}`,
  );

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
  if (options.provider) params.set('provider', options.provider);
  if (options.sceneToken) params.set('sceneToken', options.sceneToken);
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
  if (options.provider) params.set('provider', options.provider);
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
  displayMode = 'RGB',
): string {
  return `/api/tiles/${encodeURIComponent(sourceId)}/${encodeURIComponent(
    acquisitionDate,
  )}/${encodeURIComponent(displayMode)}/{z}/{x}/{y}.png`;
}

export function withCloudMaskParams(
  tileUrlTemplate: string,
  mask: { clouds: boolean; cloudShadows: boolean; cirrus: boolean },
): string {
  const [path] = tileUrlTemplate.split('?', 1);
  const params = new URLSearchParams({
    clouds: String(mask.clouds),
    cloudShadows: String(mask.cloudShadows),
    cirrus: String(mask.cirrus),
  });
  return `${path}?${params.toString()}`;
}
