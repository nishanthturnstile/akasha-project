import { ApiError } from '@/lib/api';
import type { Plot } from '@/types/api';

export function selectedPlotLabel(selectedPlotId: string | null, plots: Plot[] | undefined): string {
  if (!selectedPlotId) return 'No field selected';
  return plots?.find((plot) => plot.id === selectedPlotId)?.name ?? selectedPlotId;
}

export function formatNumber(value: number | null | undefined, unit = '', digits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a';
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`;
}

export function weatherErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return 'Weather provider rate limit was reached. Try again shortly.';
    }
    if (error.status === 503 || error.code === 'PROVIDER_UNAVAILABLE') {
      return error.message || 'Weather provider is unavailable for this field.';
    }
    if (error.code === 'FIELD_PROVIDER_NOT_SYNCED') {
      return 'Sync the selected field before loading weather data.';
    }
    return error.message;
  }
  return 'Weather data could not be loaded.';
}

export function defaultWeatherDateRange(): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(end.getUTCDate() - 30);
  return {
    startDate: start.toISOString().slice(0, 10),
    endDate: end.toISOString().slice(0, 10),
  };
}
