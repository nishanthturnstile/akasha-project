import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  composeTileTemplate,
  assignFieldGroupFields,
  completeOnboarding,
  createFieldActivity,
  createFieldGroup,
  createApiKey,
  createPlot,
  createReportTemplate,
  createScoutTask,
  deletePlot,
  discoverFields,
  exportAllPlotsGeoJson,
  exportActivitiesCsv,
  exportFieldIndex,
  exportFieldReportCsv,
  exportFieldLeaderboardCsv,
  exportPlotGeoJson,
  getConfig,
  getAccountMe,
  getAssistantStatus,
  getDates,
  getFieldLeaderboard,
  getFieldRiskSummary,
  getFieldStatistics,
  getImagerySourceMonitoring,
  getDefaultLayer,
  getJohnDeereConnection,
  listApiKeys,
  listActivities,
  listDatasets,
  listFieldGroups,
  listScoutTasks,
  listReportTemplates,
  listNotifications,
  getPlots,
  getSources,
  importPlotsGeoJson,
  markNotificationRead,
  normalizeAppDomainApiUrl,
  signup,
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
    const payload = { appName: 'Akasha', adminIngestionLiveTriggerEnabled: false };
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

  it('requests all source dates exposed by the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal('fetch', fetchMock);

    await getDates('resourcesat-2a-liss3-boa');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/sources/resourcesat-2a-liss3-boa/dates',
      expect.anything(),
    );
  });

  it('requests field-aware dates through the same-origin BFF route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal('fetch', fetchMock);

    await getDates('sentinel-2-l2a', { fieldId: 'field 1', indexType: 'NDVI' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/fields/field%201/dates?sourceId=sentinel-2-l2a&indexType=NDVI&pageSize=120',
      expect.anything(),
    );
  });

  it('requests default-layer metadata for the selected source', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ sourceId: 'sentinel-2-l2a' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getDefaultLayer('sentinel-2-l2a');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/layers/default?sourceId=sentinel-2-l2a',
      expect.anything(),
    );
  });

  it('fetches imagery source monitoring through the same-origin BFF route', async () => {
    const payload = {
      generatedAt: '2026-06-16T00:00:00Z',
      status: 'ok',
      statusReasons: [],
      staleAfterDays: 30,
      coverageThresholdPercent: 95,
      usablePixelThresholdPercent: 70,
      sources: [],
      storage: { status: 'ok', bucket: 'akasha-cogs', byPrefix: [] },
      ingestionLedger: {
        status: 'ok',
        statusCounts: {},
        failureCountsByKind: {},
        lastFailures: [],
        bySource: [],
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(getImagerySourceMonitoring()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/monitoring/imagery-sources',
      expect.objectContaining({ method: 'GET' }),
    );
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
      expect(composeTileTemplate('eos-04-sar-mrs-l2b', '2026-04-26', 'VV_GRAYSCALE')).toBe(
        '/api/tiles/eos-04-sar-mrs-l2b/2026-04-26/VV_GRAYSCALE/{z}/{x}/{y}.png',
      );
    });
  });

  describe('pipeline URL safety', () => {
    it('accepts only app-domain API proxy URLs and strips same-origin hosts', () => {
      expect(normalizeAppDomainApiUrl('/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_1')).toBe(
        '/api/pipeline/tiles/{z}/{x}/{y}.png?proxyId=px_1',
      );
      expect(
        normalizeAppDomainApiUrl(
          `${window.location.origin}/api/pipeline/field-index/stats?proxyId=px_2`,
        ),
      ).toBe('/api/pipeline/field-index/stats?proxyId=px_2');
      expect(normalizeAppDomainApiUrl('https://ingestion.internal/tiles/layer/{z}/{x}/{y}.png')).toBeNull();
      expect(normalizeAppDomainApiUrl('/api/pipeline/tiles/1/2/3.png?op=tile&exp=1&sig=abc')).toBeNull();
      expect(normalizeAppDomainApiUrl('/tiles/not-app-domain/{z}/{x}/{y}.png')).toBeNull();
    });

    it('sanitizes pipeline URLs from field statistics before caching in UI state', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          plotId: 'plot-1',
          provider: 'native',
          scope: 'field',
          indexType: 'NDVI',
          sourceId: 'sentinel-2-l2a',
          acquisitionDate: '2026-01-15',
          cloudMask: { clouds: true, cloudShadows: true, cirrus: true },
          statistics: {
            min: 0.12,
            max: 0.86,
            mean: 0.54,
            stddev: 0.08,
            validPixelPercent: 92.5,
            cloudMaskedPercent: 4.2,
            coveragePercent: 100,
          },
          pixelCounts: {
            totalPixels: 3736,
            nodataPixels: 0,
            coveragePixels: 3736,
            maskedPixels: 280,
            validPixels: 3456,
          },
          metadata: {
            formula: '(NIR-RED)/(NIR+RED)',
            bands: ['NIR', 'RED'],
            warnings: [],
            pipeline: {
              enabled: true,
              status: 'AVAILABLE',
              source: 'sentinel-2-l2a',
              providerRoute: 'earthsearch:sentinel-2-l2a',
              selectedSceneDate: '2026-01-13',
              tileUrl: 'https://ingestion.internal/tiles/layer_1/{z}/{x}/{y}.png?op=tile&exp=1&kid=default&sig=abc',
              statsUrl: '/api/pipeline/field-index/stats?proxyId=px_1',
              quality: { status: 'GOOD', reason: 'Field cloud cover within threshold', warnings: [] },
            },
          },
        }),
      });
      vi.stubGlobal('fetch', fetchMock);

      const response = await getFieldStatistics('plot-1', {
        sourceId: 'sentinel-2-l2a',
        acquisitionDate: '2026-01-15',
        indexType: 'NDVI',
      });

      expect(response.provider).toBe('native');
      expect(response.scope).toBe('field');
      expect(response.metadata.pipeline?.tileUrl).toBeUndefined();
      expect(response.metadata.pipeline?.statsUrl).toBe('/api/pipeline/field-index/stats?proxyId=px_1');
      const serialized = JSON.stringify(response);
      expect(serialized).not.toContain('ingestion.internal');
      expect(serialized).not.toContain('sig=');
      expect(serialized).not.toContain('kid=');
      expect(serialized).not.toContain('exp=');
      expect(serialized).not.toContain('op=tile');
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

  it('preserves AbortError so TanStack Query treats cancellation as cancellation', async () => {
    const aborted = new DOMException('Aborted', 'AbortError');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(aborted));
    await expect(discoverFields({ seasonId: 'season-1' })).rejects.toBe(aborted);
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

    it('returns GeoJSON blobs for exports without exposing storage URLs', async () => {
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
        sourceId: 'resourcesat-2a-liss3-boa',
        acquisitionDate: '2026-06-01',
        indexType: 'NDVI',
        cloudMask: { clouds: true, cloudShadows: false, cirrus: false },
      });
      await exportFieldReportCsv('plot-1', {
        sourceId: 'resourcesat-2a-liss3-boa',
        indexType: 'NDVI',
        startDate: '2026-06-01',
        endDate: '2026-06-01',
        cloudMask: { clouds: true, cloudShadows: false, cirrus: false },
      });

      expect(file.filename).toBe('North_NDVI.csv');
      expect(fetchMock).toHaveBeenNthCalledWith(
        1,
        '/api/fields/plot-1/exports/index?format=csv&sourceId=resourcesat-2a-liss3-boa&acquisitionDate=2026-06-01&indexType=NDVI&clouds=true&cloudShadows=false&cirrus=false',
        expect.objectContaining({ method: 'GET' }),
      );
      expect(String(fetchMock.mock.calls[1][0])).toContain('/api/fields/plot-1/exports/report.csv?');
      expect(String(fetchMock.mock.calls[1][0])).toContain('cloudShadows=false');
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
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ fieldIds: ['plot 1'] }),
        }),
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

    it('uses same-origin account notification and assistant routes', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ([]),
      });
      vi.stubGlobal('fetch', fetchMock);

      await getAccountMe();
      await signup({ email: 'new@example.test', password: 'password123', displayName: 'New User' });
      await completeOnboarding();
      await listApiKeys();
      await createApiKey('Demo');
      await listNotifications();
      await markNotificationRead('note 1');
      await getAssistantStatus();

      expect(fetchMock).toHaveBeenCalledWith('/api/account/me', expect.anything());
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/signup',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            email: 'new@example.test',
            password: 'password123',
            displayName: 'New User',
          }),
        }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/account/onboarding-complete',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(fetchMock).toHaveBeenCalledWith('/api/account/api-keys', expect.anything());
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/notifications/note%201/read',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(fetchMock).toHaveBeenCalledWith('/api/assistant/status', expect.anything());
    });
  });
});
