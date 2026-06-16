import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DownloadMenu } from '@/components/monitoring/DownloadMenu';
import type { Plot } from '@/types/api';

const plot: Plot = {
  id: 'plot-1',
  name: 'North Field',
  geometry: {
    type: 'Polygon',
    coordinates: [[[77, 12], [77.01, 12], [77.01, 12.01], [77, 12]]],
  },
  areaHa: 1,
  createdAt: null,
  updatedAt: null,
};

function renderMenu(overrides: Partial<ComponentProps<typeof DownloadMenu>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <DownloadMenu
        selectedPlot={ plot }
        selectedDate="2026-06-01"
        displayMode="NDVI"
        sourceId="resourcesat-2a-liss3-boa"
        indexType="NDVI"
        cloudMask={ { clouds: true, cloudShadows: false, cirrus: false } }
        { ...overrides }
      />
    </QueryClientProvider>,
  );
}

describe('DownloadMenu', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:akasha'),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('enables native selected-field downloads and keeps unavailable formats disabled', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename="North.csv"',
      }),
      blob: async () => new Blob(['csv'], { type: 'text/csv' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderMenu();
    fireEvent.click(screen.getByTestId('download-menu-toggle'));

    expect((screen.getByTestId('download-index-tiff') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('download-analytics-csv') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('download-field-geojson') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('download-index-shp') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('download-contours-shp') as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByTestId('download-analytics-csv'));
    await waitFor(() => {
      expect(String(fetchMock.mock.calls[0][0])).toContain('/api/fields/plot-1/exports/report.csv');
      expect(String(fetchMock.mock.calls[0][0])).toContain('cloudShadows=false');
    });
  });

  it('disables GeoTIFF when the active layer is not an index scene', () => {
    renderMenu({ displayMode: 'FCC' });
    fireEvent.click(screen.getByTestId('download-menu-toggle'));
    expect((screen.getByTestId('download-index-tiff') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('download-field-geojson') as HTMLButtonElement).disabled).toBe(false);
  });

  it('disables analytics exports for context-only sources', () => {
    renderMenu({ analyticsEnabled: false, displayMode: 'NDVI_CONTEXT' });
    fireEvent.click(screen.getByTestId('download-menu-toggle'));

    const csv = screen.getByTestId('download-analytics-csv') as HTMLButtonElement;
    const geojson = screen.getByTestId('download-field-geojson') as HTMLButtonElement;
    expect(csv.disabled).toBe(true);
    expect(geojson.disabled).toBe(true);
    expect(csv.title).toBe('Analytics are not enabled for this source.');
    expect(geojson.title).toBe('Analytics are not enabled for this source.');
  });

  it('shows sanitized failed export copy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 501,
        json: async () => ({
          error: {
            code: 'EXPORT_FORMAT_UNAVAILABLE',
            message: 'Native export failed.',
          },
        }),
      }),
    );

    renderMenu();
    fireEvent.click(screen.getByTestId('download-menu-toggle'));
    fireEvent.click(screen.getByTestId('download-field-geojson'));

    expect((await screen.findByTestId('download-error')).textContent).toContain('Native export failed.');
  });
});
