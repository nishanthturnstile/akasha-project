import type { WeatherSeries } from '@/types/api';

interface WeatherSeriesChartProps {
  series: WeatherSeries;
}

function fmt(value: number | null | undefined, unit: string, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toFixed(digits)} ${unit}`
    : 'n/a';
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(new Date(value));
}

export function WeatherSeriesChart({ series }: WeatherSeriesChartProps) {
  const plotted = series.points
    .filter((point): point is { date: string; value: number } => typeof point.value === 'number')
    .sort((a, b) => a.date.localeCompare(b.date));

  if (!series.available || plotted.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed border-border/80 px-3 py-4 text-[12px] text-muted-foreground"
        data-testid={ `weather-chart-empty-${series.id}` }
      >
        { series.unavailableReason ?? `No ${series.label.toLowerCase()} values are available.` }
      </div>
    );
  }

  const width = 300;
  const height = 136;
  const padding = { top: 12, right: 12, bottom: 26, left: 42 };
  const values = plotted.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const xFor = (index: number) =>
    padding.left +
    (index / Math.max(1, plotted.length - 1)) * (width - padding.left - padding.right);
  const yFor = (value: number) =>
    padding.top + ((max - value) / span) * (height - padding.top - padding.bottom);
  const d = plotted
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(2)} ${yFor(point.value).toFixed(2)}`)
    .join(' ');
  const summary = plotted.map((point) => `${point.date}: ${fmt(point.value, series.unit)}`).join(', ');

  return (
    <div className="rounded-md border border-border/80 bg-background/50 p-2" data-testid={ `weather-chart-${series.id}` }>
      <p className="sr-only">{ `${series.label} weather values: ${summary}` }</p>
      <svg
        role="img"
        aria-label={ `${series.label} weather chart` }
        viewBox={ `0 0 ${width} ${height}` }
        className="h-36 w-full overflow-visible"
      >
        <line
          x1={ padding.left }
          x2={ width - padding.right }
          y1={ height - padding.bottom }
          y2={ height - padding.bottom }
          className="stroke-border"
          strokeWidth="1"
        />
        <line
          x1={ padding.left }
          x2={ padding.left }
          y1={ padding.top }
          y2={ height - padding.bottom }
          className="stroke-border"
          strokeWidth="1"
        />
        <text x="2" y={ yFor(max) + 4 } className="fill-muted-foreground text-[9px]">
          { fmt(max, series.unit, 0) }
        </text>
        <text x="2" y={ yFor(min) + 4 } className="fill-muted-foreground text-[9px]">
          { fmt(min, series.unit, 0) }
        </text>
        <path d={ d } fill="none" className="stroke-primary" strokeWidth="2.25" strokeLinecap="round" />
        { plotted.map((point, index) => (
          <g key={ `${point.date}-${index}` }>
            <circle
              cx={ xFor(index) }
              cy={ yFor(point.value) }
              r="3.4"
              className="fill-background stroke-primary"
              strokeWidth="2"
            />
            <title>{ `${point.date}: ${fmt(point.value, series.unit)}` }</title>
          </g>
        )) }
        { plotted.length > 1 && (
          <>
            <text
              x={ padding.left }
              y={ height - 7 }
              textAnchor="start"
              className="fill-muted-foreground text-[9px]"
            >
              { dateLabel(plotted[0].date) }
            </text>
            <text
              x={ width - padding.right }
              y={ height - 7 }
              textAnchor="end"
              className="fill-muted-foreground text-[9px]"
            >
              { dateLabel(plotted[plotted.length - 1].date) }
            </text>
          </>
        ) }
      </svg>
    </div>
  );
}
