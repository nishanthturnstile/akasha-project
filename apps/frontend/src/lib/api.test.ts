import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, composeTileTemplate, getConfig, getSources } from '@/lib/api';

describe('api client error mapping', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses a successful JSON payload from the same-origin endpoint', async () => {
    const payload = { appName: 'Akasha' };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    });
    vi.stubGlobal('fetch', fetchMock);

    const cfg = await getConfig();
    expect(cfg).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith('/api/config', expect.anything());
  });

  it('maps the BFF error envelope to ApiError code/message/status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({
          error: { code: 'RASTER_BACKEND_UNAVAILABLE', message: 'TiTiler is not configured.' },
        }),
      }),
    );

    await expect(getSources()).rejects.toMatchObject({
      code: 'RASTER_BACKEND_UNAVAILABLE',
      status: 503,
    });
  });

  describe('composeTileTemplate', () => {
    it('uses the requested display mode in the source/date tile route', () => {
      expect(composeTileTemplate('sentinel-1-grd', '2026-04-26', 'VV_GRAYSCALE')).toBe(
        '/api/tiles/sentinel-1-grd/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });
  });

  it('wraps the thrown value as an ApiError instance', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: 'NOT_FOUND', message: 'Missing.' } }),
      }),
    );
    let caught: unknown;
    try {
      await getSources();
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).message).toBe('Missing.');
  });

  it('uses sanitized defaults for a non-JSON error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        },
      }),
    );
    await expect(getConfig()).rejects.toMatchObject({ code: 'REQUEST_FAILED', status: 500 });
  });

  it('throws NETWORK_ERROR when fetch itself rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(getConfig()).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 });
  });
});
