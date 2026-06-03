import { useState } from 'react';
import { WeatherSeriesChart } from '@/components/weather/WeatherSeriesChart';
import { useMapView } from '@/state/mapViewContext';
import {
  useFieldWeatherHistory,
  useFieldWeatherSoilMoisture,
  usePlots,
} from '@/lib/queries';
import {
  defaultWeatherDateRange,
  formatNumber,
  selectedPlotLabel,
  weatherErrorMessage,
} from '@/pages/weather/weatherPageUtils';
import type { WeatherSeriesId } from '@/types/api';

const WEATHER_PARAMETERS: { id: WeatherSeriesId; label: string }[] = [
  { id: 'accumulatedPrecipitation', label: 'Accumulated precipitation' },
  { id: 'dailyPrecipitation', label: 'Daily precipitation' },
  { id: 'dailyTemperature', label: 'Daily temperature' },
  { id: 'sumActiveTemperatures', label: 'Sum active temperatures' },
  { id: 'evapotranspiration', label: 'Evapotranspiration' },
  { id: 'relativeHumidity', label: 'Relative humidity' },
  { id: 'globalRadiation', label: 'Global radiation' },
];

function latestNonNullValue(points: { value: number | null }[]): number | null {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const value = points[index]?.value;
    if (typeof value === 'number') return value;
  }
  return null;
}

function EmptyState() {
  return (
    <section className="rounded-xl border border-dashed border-border/80 bg-card/80 p-6 text-sm text-muted-foreground">
      <h1 className="text-lg font-semibold text-foreground">Weather Analytics</h1>
      <p className="mt-2">Select a field to view historical weather charts.</p>
    </section>
  );
}

export default function WeatherAnalyticsPage() {
  const { selectedPlotId } = useMapView();
  const plotsQ = usePlots();
  const [range, setRange] = useState(defaultWeatherDateRange);
  const [selectedParameter, setSelectedParameter] = useState<WeatherSeriesId>('dailyPrecipitation');
  const historyQ = useFieldWeatherHistory(selectedPlotId, {
    startDate: range.startDate,
    endDate: range.endDate,
  });
  const soilQ = useFieldWeatherSoilMoisture(selectedPlotId, {
    startDate: range.startDate,
    endDate: range.endDate,
  });

  if (!selectedPlotId) {
    return <EmptyState />;
  }

  const fieldName = selectedPlotLabel(selectedPlotId, plotsQ.data);
  const selectedSeries = historyQ.data?.series.find((series) => series.id === selectedParameter);
  const latestValue = selectedSeries ? latestNonNullValue(selectedSeries.points) : null;
  const errorMessage = historyQ.isError ? weatherErrorMessage(historyQ.error) : null;

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-auto bg-background p-4" data-testid="weather-analytics-page">
      <header className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Weather</p>
        <h1 className="mt-1 text-2xl font-semibold text-foreground">Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">Selected field: { fieldName }</p>
      </header>

      <section className="grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4 md:grid-cols-[1fr_1fr_auto]">
        <label className="text-sm text-muted-foreground">
          Start date
          <input
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
            type="date"
            value={ range.startDate }
            onChange={ (event) => setRange((current) => ({ ...current, startDate: event.target.value })) }
          />
        </label>
        <label className="text-sm text-muted-foreground">
          End date
          <input
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
            type="date"
            value={ range.endDate }
            onChange={ (event) => setRange((current) => ({ ...current, endDate: event.target.value })) }
          />
        </label>
        <div className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground">
          Comparison mode
          <span className="mt-1 block text-xs">Planned: compare two fields or seasons after reports exist.</span>
        </div>
      </section>

      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold text-foreground">Parameters</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          { WEATHER_PARAMETERS.map((parameter) => (
            <button
              key={ parameter.id }
              type="button"
              onClick={ () => setSelectedParameter(parameter.id) }
              className={
                parameter.id === selectedParameter
                  ? 'rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground'
                  : 'rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground'
              }
            >
              { parameter.label }
            </button>
          )) }
        </div>
      </section>

      { historyQ.isLoading && <div className="glass scan-sweep h-24 rounded-xl" data-testid="weather-history-loading" /> }

      { errorMessage && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100" role="status">
          { errorMessage }
        </div>
      ) }

      { selectedSeries && (
        <article className="rounded-xl border border-border/80 bg-card/90 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">{ selectedSeries.label }</h2>
              <p className="text-sm text-muted-foreground">
                Latest value: { formatNumber(latestValue, selectedSeries.unit) }
              </p>
            </div>
            <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">
              { range.startDate } - { range.endDate }
            </span>
          </div>
          <div className="mt-4">
            <WeatherSeriesChart series={ selectedSeries } />
          </div>
        </article>
      ) }

      { historyQ.data && (
        <section className="grid gap-4 lg:grid-cols-2">
          { historyQ.data.series.map((series) => (
            <article key={ series.id } className="rounded-xl border border-border/80 bg-card/90 p-4">
              <h3 className="font-semibold text-foreground">{ series.label }</h3>
              <WeatherSeriesChart series={ series } />
            </article>
          )) }
        </section>
      ) }

      <aside className="rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold text-foreground">Soil moisture</h2>
        { soilQ.isLoading && <p className="mt-2 text-sm text-muted-foreground">Checking availability...</p> }
        { soilQ.isError && (
          <p className="mt-2 text-sm text-muted-foreground">{ weatherErrorMessage(soilQ.error) }</p>
        ) }
        { soilQ.data && !soilQ.data.available && (
          <p className="mt-2 text-sm text-muted-foreground">
            { soilQ.data.unavailableReason ?? 'Soil-moisture data is unavailable for this provider.' }
          </p>
        ) }
        { soilQ.data?.available && soilQ.data.series && (
          <div className="mt-3">
            <WeatherSeriesChart series={ soilQ.data.series } />
          </div>
        ) }
      </aside>
    </section>
  );
}
