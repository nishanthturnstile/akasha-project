import { useMapView } from '@/state/mapViewContext';
import { useFieldWeatherForecast, usePlots } from '@/lib/queries';
import { formatNumber, selectedPlotLabel, weatherErrorMessage } from '@/pages/weather/weatherPageUtils';
import { SelectFieldNotice } from '@/components/shell/SelectFieldNotice';

function EmptyState() {
  return (
    <SelectFieldNotice
      title="Weather Forecast"
      message="Select a field to view forecast cards and the weather timeline."
    />
  );
}

function LoadingState() {
  return <div className="glass scan-sweep h-24 rounded-xl" data-testid="weather-forecast-loading" />;
}

export default function WeatherForecastPage() {
  const { selectedPlotId } = useMapView();
  const plotsQ = usePlots();
  const forecastQ = useFieldWeatherForecast(selectedPlotId, { days: 7 });

  if (!selectedPlotId) {
    return <EmptyState />;
  }

  const fieldName = selectedPlotLabel(selectedPlotId, plotsQ.data);
  const errorMessage = forecastQ.isError ? weatherErrorMessage(forecastQ.error) : null;

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 overflow-auto bg-background p-4" data-testid="weather-forecast-page">
      <header className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Weather</p>
        <h1 className="mt-1 text-2xl font-semibold text-foreground">Forecast</h1>
        <p className="mt-1 text-sm text-muted-foreground">Selected field: { fieldName }</p>
      </header>

      { forecastQ.isLoading && <LoadingState /> }

      { errorMessage && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100" role="status">
          { errorMessage }
        </div>
      ) }

      { forecastQ.data && (
        <>
          <div className="grid gap-3 md:grid-cols-5">
            { forecastQ.data.cards.map((card) => (
              <article key={ card.id } className="rounded-xl border border-border/80 bg-card/90 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{ card.label }</p>
                <p className="mt-3 text-2xl font-semibold text-foreground">{ card.summary }</p>
              </article>
            )) }
          </div>

          <article className="rounded-xl border border-border/80 bg-card/90 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Forecast timeline</h2>
                <p className="text-sm text-muted-foreground">
                  { forecastQ.data.startDate } to { forecastQ.data.endDate }
                </p>
              </div>
              <span className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">
                { forecastQ.data.timeline.length } entries
              </span>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Date</th>
                    <th className="py-2 pr-4">Temp</th>
                    <th className="py-2 pr-4">Rain</th>
                    <th className="py-2 pr-4">Humidity</th>
                    <th className="py-2 pr-4">Clouds</th>
                    <th className="py-2 pr-4">Wind</th>
                    <th className="py-2 pr-4">Conditions</th>
                  </tr>
                </thead>
                <tbody>
                  { forecastQ.data.timeline.map((point) => (
                    <tr key={ `${point.date}-${point.startTime ?? ''}` } className="border-t border-border/60">
                      <td className="py-2 pr-4">{ point.date }</td>
                      <td className="py-2 pr-4">
                        { formatNumber(point.temperatureAvgC, 'C') }
                      </td>
                      <td className="py-2 pr-4">{ formatNumber(point.precipitationMm, 'mm') }</td>
                      <td className="py-2 pr-4">{ formatNumber(point.humidityPercent, '%') }</td>
                      <td className="py-2 pr-4">{ formatNumber(point.cloudinessPercent, '%') }</td>
                      <td className="py-2 pr-4">
                        { formatNumber(point.windMps, 'm/s') }
                        { point.windDirection ? ` ${point.windDirection}` : '' }
                      </td>
                      <td className="py-2 pr-4">{ point.conditions ?? 'n/a' }</td>
                    </tr>
                  )) }
                </tbody>
              </table>
            </div>
          </article>
        </>
      ) }
    </section>
  );
}
