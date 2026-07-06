import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ChartTab from './ChartTab';
import type { Field, FieldStatisticsResponse, FieldTrendResponse } from '@/types/api';

const FIELD: Field = {
  id: 'field-1',
  userId: 'user-1',
  name: 'Pipeline field',
  areaHa: 4.2,
  geometry: {
    type: 'Polygon',
    coordinates: [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12]]],
  },
  groupId: null,
  seasonIds: [],
  vegetationData: [],
  createdAt: null,
  updatedAt: null,
};

function renderChart(options: {
  sourceId?: string | null;
  selectedDate?: string | null;
} = {}) {
  const resolvedSourceId = Object.prototype.hasOwnProperty.call(options, 'sourceId')
    ? options.sourceId ?? undefined
    : 'sentinel-2-l2a';
  const selectedDate = Object.prototype.hasOwnProperty.call(options, 'selectedDate')
    ? options.selectedDate ?? null
    : '2026-03-20';
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <ChartTab
        field={ FIELD }
        sourceId={ resolvedSourceId }
        selectedDate={ selectedDate }
        indexType="NDVI"
        indices={ ['NDVI', 'MSAVI'] }
        onIndexTypeChange={ vi.fn() }
        cloudMask={ { clouds: true, cloudShadows: true, cirrus: false } }
        periodFrom="2026-01-01"
        periodTo="2026-03-20"
      />
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => payload,
  };
}

function pipelineStatistics(): FieldStatisticsResponse {
  return {
    plotId: 'field-1',
    provider: 'pipeline',
    scope: 'field',
    indexType: 'NDVI',
    sourceId: 'sentinel-2-l2a',
    acquisitionDate: '2026-03-20',
    cloudMask: { clouds: true, cloudShadows: true, cirrus: false },
    statistics: {
      min: 0.12,
      max: 0.86,
      mean: 0.62,
      stddev: 0.08,
      validPixelPercent: 94,
      cloudMaskedPercent: 3,
      coveragePercent: 98,
    },
    pixelCounts: {
      totalPixels: 100,
      nodataPixels: 2,
      coveragePixels: 98,
      maskedPixels: 3,
      validPixels: 94,
    },
    metadata: {
      formula: '(NIR - RED) / (NIR + RED)',
      bands: ['B8', 'B4'],
    },
  };
}

function pipelineTrend(): FieldTrendResponse {
  return {
    plotId: 'field-1',
    provider: 'pipeline',
    scope: 'pipeline',
    sourceId: 'sentinel-2-l2a',
    indexType: 'NDVI',
    startDate: '2026-01-01',
    endDate: '2026-03-20',
    points: [
      { acquisitionDate: '2026-01-10', mean: 0.44 },
      { acquisitionDate: '2026-03-20', mean: 0.62 },
    ],
    metadata: {
      formula: '(NIR - RED) / (NIR + RED)',
      bands: ['B8', 'B4'],
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChartTab', () => {
  it('renders Sentinel-2 pipeline statistics and trend from local BFF endpoints', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/fields/field-1/indices/statistics') {
          return Promise.resolve(jsonResponse(pipelineStatistics()));
        }
        if (path.startsWith('/api/fields/field-1/analytics/trend')) {
          return Promise.resolve(jsonResponse(pipelineTrend()));
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );

    renderChart();

    expect((await screen.findByTestId('analytics-provider')).textContent).toContain('Pipeline analytics');
    expect(screen.getByTestId('analytics-stat-mean').textContent).toContain('0.62');
    expect(screen.getByTestId('analytics-stat-valid').textContent).toContain('94.00%');
    expect(screen.getByTestId('field-trend-chart')).toBeTruthy();

    const calls = (globalThis.fetch as unknown as {
      mock: { calls: Array<[RequestInfo | URL, RequestInit | undefined]> };
    }).mock.calls;
    expect(calls.some(([input]) => String(input) === '/api/fields/field-1/indices/statistics')).toBe(true);
    expect(calls.some(([input]) => String(input).startsWith('/api/fields/field-1/analytics/trend'))).toBe(true);
    expect(calls.every(([input]) => String(input).startsWith('/api/'))).toBe(true);
  });

  it('renders an unavailable state before source/date inputs are available', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    renderChart({ sourceId: undefined, selectedDate: null });

    expect(screen.getByTestId('analytics-unavailable').textContent).toContain(
      'Select an imagery source',
    );
    expect(screen.getByTestId('analytics-trend-unavailable')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders a typed statistics error without hiding the trend section', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === '/api/fields/field-1/indices/statistics') {
          return Promise.resolve(
            jsonResponse(
              { error: { code: 'INGESTION_OVERLAY_UNAVAILABLE', message: 'Pipeline unavailable' } },
              false,
              503,
            ),
          );
        }
        if (path.startsWith('/api/fields/field-1/analytics/trend')) {
          return Promise.resolve(jsonResponse({ ...pipelineTrend(), points: [] }));
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );

    renderChart();

    await waitFor(() => {
      expect(screen.getByTestId('analytics-stats-error').textContent).toContain(
        'Pipeline unavailable',
      );
    });
    expect(screen.getByTestId('analytics-trend-section')).toBeTruthy();
  });
});
