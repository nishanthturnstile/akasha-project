import type {
  ApiErrorShape,
  AppConfig,
  DefaultLayer,
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

async function request<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: 'application/json' } });
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Unable to reach the Akasha service.', 0);
  }

  if (!res.ok) {
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
    throw new ApiError(code, message, res.status, details);
  }

  return (await res.json()) as T;
}

export const getConfig = (): Promise<AppConfig> => request<AppConfig>('/api/config');

export const getSources = (): Promise<Source[]> => request<Source[]>('/api/sources');

export const getDates = (sourceId: string): Promise<SceneDate[]> =>
  request<SceneDate[]>(`/api/sources/${encodeURIComponent(sourceId)}/dates`);

export const getDefaultLayer = (): Promise<DefaultLayer> =>
  request<DefaultLayer>('/api/layers/default');

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
