import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  composeTileTemplate,
  assignFieldGroupFields,
  createFieldActivity,
  createFieldGroup,
  createPlot,
  createReportTemplate,
  createScoutTask,
  deletePlot,
  exportAllPlotsGeoJson,
  exportActivitiesCsv,
  exportFieldIndex,
  exportFieldReportCsv,
  exportFieldLeaderboardCsv,
  exportPlotGeoJson,
  getConfig,
  getFieldLeaderboard,
  getFieldRiskSummary,
  getFieldWeatherForecast,
  getFieldWeatherHistory,
  getFieldWeatherSoilMoisture,
  createVegetationZoning,
  exportZoningMap,
  getJohnDeereConnection,
  getZoningMap,
  listActivities,
  listDatasets,
  listFieldGroups,
  listScoutTasks,
  listZoningMaps,
  listReportTemplates,
  getPlots,
  getSources,
  importPlotsGeoJson,
  uploadDataset,
  updateReportTemplate,
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

    it('uses same-origin VRA zoning routes and encoded map ids', async () => {
      const blob = new Blob(['zip'], { type: 'application/zip' });
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        if (String(input).endsWith('/export.shp')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Disposition': 'attachment; filename="zones.zip"' }),
            blob: async () => blob,
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ mapId: 'map 1', maps: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await createVegetationZoning('plot 1', {
        indexType: 'NDVI',
        imageDate: '2026-06-01',
        zoneCount: 3,
        minZoneArea: 0.25,
      });
      await listZoningMaps('plot 1');
      await getZoningMap('plot 1', 'map 1');
      const file = await exportZoningMap('plot 1', 'map 1', 'shp');

      expect(file.filename).toBe('zones.zip');
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/fields/plot%201/zoning/vegetation',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/fields/plot%201/zoning/maps',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        3,
        '/api/fields/plot%201/zoning/maps/map%201',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        4,
        '/api/fields/plot%201/zoning/maps/map%201/export.shp',
        expect.objectContaining({ method: 'GET' }),
      );
    });

    it('uses same-origin report routes and handles CSV downloads', async () => {
      const blob = new Blob(['csv'], { type: 'text/csv' });
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('/export.csv')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Disposition': 'attachment; filename="leaderboard.csv"' }),
            blob: async () => blob,
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ rows: [] }) });
      });
      vi.stubGlobal('fetch', fetchMock);

      await getFieldLeaderboard({ indexType: 'NDVI', cropType: 'Paddy', limit: 10 });
      const file = await exportFieldLeaderboardCsv(
        { indexType: 'NDVI' },
        { columns: ['field', 'latestIndexValue'] },
      );
      await listReportTemplates();
      await createReportTemplate({ name: 'Summary', columns: ['field'] });
      await updateReportTemplate('template 1', { name: 'Updated' });

      expect(file.filename).toBe('leaderboard.csv');
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/reports/field-leaderboard?indexType=NDVI&cropType=Paddy&limit=10',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(String(fetchMock.mock.calls[1][0])).toBe(
        '/api/reports/field-leaderboard/export.csv?indexType=NDVI&columns=field&columns=latestIndexValue',
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        3,
        '/api/reports/templates',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        4,
        '/api/reports/templates',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(fetchMock).toHaveBeenNthCalledWith(
        5,
        '/api/reports/templates/template%201',
        expect.objectContaining({ method: 'PATCH' }),
      );
    });

    it('uses same-origin operations, scout, data-manager, and group routes', async () => {
      const blob = new Blob(['csv'], { type: 'text/csv' });
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('/activities/export.csv')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Disposition': 'attachment; filename="activities.csv"' }),
            blob: async () => blob,
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      });
      vi.stubGlobal('fetch', fetchMock);

      await listActivities({ year: 2026, activityType: 'fertilizer' });
      await createFieldActivity('plot 1', { activityType: 'fertilizer', activityDate: '2026-06-04' });
      await exportActivitiesCsv({ year: 2026 });
      await listScoutTasks({ status: 'new' });
      await createScoutTask({ longitude: 77, latitude: 12 });
      await listDatasets();
      await uploadDataset(new File(['{}'], 'fields.geojson', { type: 'application/geo+json' }), 'geojson');
      await getJohnDeereConnection();
      await listFieldGroups();
      await createFieldGroup({ name: 'North' });
      await assignFieldGroupFields('group 1', ['plot 1']);

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/activities?year=2026&activityType=fertilizer',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/fields/plot%201/activities',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(String(fetchMock.mock.calls[2][0])).toContain('/api/activities/export.csv?year=2026');
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/scout-tasks?status=new',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/datasets/upload',
        expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/field-groups/group%201/fields',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('fetches field risk summary from same-origin route', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ plotId: 'plot 1', fieldWatchLevel: 'unknown' }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await getFieldRiskSummary('plot 1', { indexType: 'NDVI' });

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/fields/plot%201/risk/summary?indexType=NDVI',
        expect.objectContaining({ method: 'GET' }),
      );
    });
  });
});
