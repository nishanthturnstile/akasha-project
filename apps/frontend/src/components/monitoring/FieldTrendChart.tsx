import type { FieldTrendPoint } from '@/types/api';

interface FieldTrendChartProps {
  points: FieldTrendPoint[];
  indexType: string;
}

function fmt(value: number | null | undefined, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(new Date(value));
}

export function FieldTrendChart({ points, indexType }: FieldTrendChartProps) {
  const plotted = points
    .filter((point): point is FieldTrendPoint & { mean: number } => typeof point.mean === 'number')
    .sort((a, b) => a.acquisitionDate.localeCompare(b.acquisitionDate));

  if (plotted.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed border-border/80 px-3 py-4 text-[12px] text-muted-foreground"
        data-testid="field-trend-empty"
      >
        No trend values are available for this field and date range.
      </div>
    );
  }

  const width = 248;
  const height = 128;
  const padding = { top: 12, right: 12, bottom: 26, left: 34 };
  const isNdvi = indexType.toUpperCase() === 'NDVI';
  const values = plotted.map((point) => point.mean);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  // NDVI: pin visible domain to [0, 1] for crop-vigor interpretation.
  // Other indices: auto-scale to data range.
  const yMin = isNdvi ? 0 : dataMin;
  const yMax = isNdvi ? 1 : dataMax;
  const span = yMax - yMin || 1;
  const xFor = (index: number) =>
    padding.left +
    (index / Math.max(1, plotted.length - 1)) * (width - padding.left - padding.right);
  // For NDVI, visually clamp values outside [0,1] to the boundary; data is not modified.
  const yFor = (value: number) => {
    const v = isNdvi ? Math.max(0, Math.min(1, value)) : value;
    return padding.top + ((yMax - v) / span) * (height - padding.top - padding.bottom);
  };
  const d = plotted
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(2)} ${yFor(point.mean).toFixed(2)}`)
    .join(' ');
  const summary = plotted
    .map((point) => `${point.acquisitionDate}: ${fmt(point.mean)}`)
    .join(', ');

  return (
    <div className="rounded-md border border-border/80 bg-background/50 p-2" data-testid="field-trend-chart">
      <p className="sr-only">{ `${indexType} trend values: ${summary}` }</p>
      <svg
        role="img"
        aria-label={ `${indexType} trend chart` }
        viewBox={ `0 0 ${width} ${height}` }
        className="h-32 w-full overflow-visible"
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
        <text x="2" y={ yFor(yMax) + 4 } className="fill-muted-foreground text-[9px]" data-testid="trend-y-max">
          { fmt(yMax, 2) }
        </text>
        <text x="2" y={ yFor(yMin) + 4 } className="fill-muted-foreground text-[9px]" data-testid="trend-y-min">
          { fmt(yMin, 2) }
        </text>
        <path d={ d } fill="none" className="stroke-primary" strokeWidth="2.25" strokeLinecap="round" />
        { plotted.map((point, index) => (
          <g key={ `${point.acquisitionDate}-${index}` }>
            <circle
              cx={ xFor(index) }
              cy={ yFor(point.mean) }
              r="3.4"
              className="fill-background stroke-primary"
              strokeWidth="2"
            />
            <title>{ `${point.acquisitionDate}: ${fmt(point.mean)}` }</title>
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
              { dateLabel(plotted[0].acquisitionDate) }
            </text>
            <text
              x={ width - padding.right }
              y={ height - 7 }
              textAnchor="end"
              className="fill-muted-foreground text-[9px]"
            >
              { dateLabel(plotted[plotted.length - 1].acquisitionDate) }
            </text>
          </>
        ) }
      </svg>
    </div>
  );
}
