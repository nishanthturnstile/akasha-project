import type {
  ApiErrorShape,
  AppConfig,
  DefaultLayer,
  Plot,
  PlotCreatePayload,
  PlotGeometry,
  PlotImportResponse,
  PlotUpdatePayload,
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
