import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  composeTileTemplate,
  createPlot,
  deletePlot,
  exportAllPlotsGeoJson,
  exportFieldIndex,
  exportFieldReportCsv,
  exportPlotGeoJson,
  getConfig,
  getFieldWeatherForecast,
  getFieldWeatherHistory,
  getFieldWeatherSoilMoisture,
  getPlots,
  getSources,
  importPlotsGeoJson,
  updatePlot,
} from '@/lib/api';
import type { PlotGeometry } from '@/types/api';

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

  describe('plot field functions', () => {
    const geometry: PlotGeometry = {
      type: 'Polygon',
      coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12.01], [77, 12]]],
    };

    it('fetches plots from the same-origin plot route', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
      });
      vi.stubGlobal('fetch', fetchMock);

      await expect(getPlots()).resolves.toEqual([]);
      expect(fetchMock).toHaveBeenCalledWith('/api/plots', expect.objectContaining({ method: 'GET' }));
    });

    it('sends JSON bodies for create, update, and import', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ id: 'plot-1', name: 'Field', geometry, areaHa: 1 }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await createPlot({ name: 'Field', geometry, cropType: 'Paddy' });
      await updatePlot('plot-1', { status: 'active' });
      await importPlotsGeoJson({ type: 'Feature', geometry, properties: { name: 'Imported' } });

      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/plots',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'Field', geometry, cropType: 'Paddy' }),
        }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/plots/plot-1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ status: 'active' }),
        }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        3,
        '/api/plots/import/geojson',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('handles 204 delete responses', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        json: async () => {
          throw new Error('delete should not parse JSON');
        },
      });
      vi.stubGlobal('fetch', fetchMock);

      await expect(deletePlot('plot-1')).resolves.toBeUndefined();
      expect(fetchMock).toHaveBeenCalledWith('/api/plots/plot-1', expect.objectContaining({ method: 'DELETE' }));
    });

    it('returns GeoJSON blobs for exports without exposing provider URLs', async () => {
      const blob = new Blob(['{"type":"FeatureCollection","features":[]}'], {
        type: 'application/geo+json',
      });
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/geo+json' }),
        blob: async () => blob,
      });
      vi.stubGlobal('fetch', fetchMock);

      await expect(exportAllPlotsGeoJson()).resolves.toBe(blob);
      await expect(exportPlotGeoJson('plot-1')).resolves.toBe(blob);
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/plots/export.geojson',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/plots/plot-1/export.geojson',
        expect.objectContaining({ method: 'GET' }),
      );
    });

    it('downloads selected-field exports with cloud mask params and response filename', async () => {
      const blob = new Blob(['csv'], { type: 'text/csv' });
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({
          'Content-Type': 'text/csv',
          'Content-Disposition': 'attachment; filename="North_NDVI.csv"',
        }),
        blob: async () => blob,
      });
      vi.stubGlobal('fetch', fetchMock);

      const file = await exportFieldIndex('plot-1', {
        format: 'csv',
        sourceId: 'sentinel-2-l2a',
        acquisitionDate: '2026-06-01',
        indexType: 'NDVI',
        provider: 'native',
        cloudMask: { clouds: true, cloudShadows: false, cirrus: true },
      });
      await exportFieldReportCsv('plot-1', {
        sourceId: 'sentinel-2-l2a',
        indexType: 'NDVI',
        startDate: '2026-06-01',
        endDate: '2026-06-01',
        cloudMask: { clouds: true, cloudShadows: false, cirrus: true },
      });

      expect(file.filename).toBe('North_NDVI.csv');
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/fields/plot-1/exports/index?format=csv&sourceId=sentinel-2-l2a&acquisitionDate=2026-06-01&indexType=NDVI&provider=native&clouds=true&cloudShadows=false&cirrus=true',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(String(fetchMock.mock.calls[1][0])).toContain('/api/fields/plot-1/exports/report.csv?');
      expect(String(fetchMock.mock.calls[1][0])).toContain('cloudShadows=false');
    });

    it('fetches selected-field weather from same-origin routes with encoded query params', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ plotId: 'plot 1', provider: 'eos', metadata: {} }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await getFieldWeatherForecast('plot 1', { provider: 'auto', days: 5 });
      await getFieldWeatherHistory('plot 1', {
        startDate: '2026-06-01',
        endDate: '2026-06-10',
        parameters: ['dailyPrecipitation', 'globalRadiation'],
      });
      await getFieldWeatherSoilMoisture('plot 1', {
        startDate: '2026-06-01',
        endDate: '2026-06-10',
      });

      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/fields/plot%201/weather/forecast?provider=auto&days=5',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(String(fetchMock.mock.calls[1][0])).toBe(
        '/api/fields/plot%201/weather/history?startDate=2026-06-01&endDate=2026-06-10&parameters=dailyPrecipitation&parameters=globalRadiation',
      );
      expect(String(fetchMock.mock.calls[2][0])).toBe(
        '/api/fields/plot%201/weather/soil-moisture?startDate=2026-06-01&endDate=2026-06-10',
      );
    });
  });
});
