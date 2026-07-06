import { useMemo } from 'react';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';
import { Button } from '@/components/ui/button';
import { useFieldStatistics, useFieldTrend } from '@/lib/queries';
import type { CloudMaskOptions, Field } from '@/types/api';

interface ChartTabProps {
  field: Field;
  sourceId: string | undefined;
  selectedDate: string | null;
  indexType: string;
  indices: string[];
  onIndexTypeChange: (next: string) => void;
  cloudMask: CloudMaskOptions;
  periodFrom?: string | null;
  periodTo?: string | null;
}

function fmt(value: number | null | undefined, suffix = ''): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a';
  return `${value.toFixed(2)}${suffix}`;
}

function indexLabel(index: string): string {
  return index === 'NDWI_GREEN_NIR' ? 'NDWI' : index;
}

function startDateFor(endDate: string | null): string | undefined {
  if (!endDate) return undefined;
  const date = new Date(`${endDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 180);
  return date.toISOString().slice(0, 10);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function Metric({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}) {
  return (
    <div className="rounded bg-muted/30 px-2 py-1.5" data-testid={ testId }>
      <p className="text-[10px] uppercase text-muted-foreground">{ label }</p>
      <p className="text-[15px] font-semibold text-foreground">{ value }</p>
    </div>
  );
}

export default function ChartTab({
  field,
  sourceId,
  selectedDate,
  indexType,
  indices,
  onIndexTypeChange,
  cloudMask,
  periodFrom,
  periodTo,
}: ChartTabProps) {
  const trendStart = periodFrom ?? startDateFor(selectedDate);
  const trendEnd = periodTo ?? selectedDate ?? undefined;
  const trendSourceId = sourceId && (trendStart || trendEnd) ? sourceId : undefined;

  const statisticsQ = useFieldStatistics(field.id, {
    sourceId,
    acquisitionDate: selectedDate,
    indexType,
    cloudMask,
    preferHighRes: true,
  });
  const trendQ = useFieldTrend(field.id, {
    sourceId: trendSourceId,
    indexType,
    startDate: trendStart,
    endDate: trendEnd,
    cloudMask,
  });

  const stats = statisticsQ.data?.statistics;
  const provider = statisticsQ.data?.provider ?? trendQ.data?.provider ?? null;
  const providerLabel = provider === 'pipeline' ? 'Pipeline' : provider === 'native' ? 'Native' : null;
  const unavailableReason = useMemo(() => {
    if (!sourceId) return 'Select an imagery source to load field analytics.';
    if (!selectedDate) return 'Select an acquisition date to load field statistics.';
    return null;
  }, [selectedDate, sourceId]);

  return (
    <div className="space-y-3 pt-1" data-testid="analytics-chart-tab">
      <div className="flex flex-wrap gap-1.5" aria-label="Analytics index">
        { indices.map((index) => (
          <Button
            key={ index }
            type="button"
            size="sm"
            variant={ index === indexType ? 'primary' : 'ghost' }
            className="h-7 px-2 text-[11px]"
            onClick={ () => onIndexTypeChange(index) }
            data-testid={ `analytics-index-${index}` }
          >
            { indexLabel(index) }
          </Button>
        )) }
      </div>

      { providerLabel && (
        <div
          className="w-fit rounded-pill border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary"
          data-testid="analytics-provider"
        >
          { providerLabel } analytics
        </div>
      ) }

      <section className="rounded-md border border-border/80 bg-background/50 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[11px] uppercase text-muted-foreground">
            Statistics · { selectedDate ?? 'no date' }
          </p>
          { statisticsQ.isLoading && (
            <span className="text-[11px] text-muted-foreground" data-testid="analytics-stats-loading">
              Loading…
            </span>
          ) }
        </div>

        { unavailableReason ? (
          <div
            className="rounded-md border border-dashed border-border/80 p-3 text-[13px] leading-5 text-muted-foreground"
            data-testid="analytics-unavailable"
          >
            { unavailableReason }
          </div>
        ) : statisticsQ.isError ? (
          <div className="rounded-md border border-destructive/30 p-3 text-[13px] leading-5 text-destructive" data-testid="analytics-stats-error">
            { errorMessage(statisticsQ.error, 'Unable to load statistics.') }
          </div>
        ) : stats ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Metric label="Mean" value={ fmt(stats.mean) } testId="analytics-stat-mean" />
              <Metric label="Std dev" value={ fmt(stats.stddev) } testId="analytics-stat-stddev" />
              <Metric label="Min" value={ fmt(stats.min) } testId="analytics-stat-min" />
              <Metric label="Max" value={ fmt(stats.max) } testId="analytics-stat-max" />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-1.5">
              <Metric label="Valid" value={ fmt(stats.validPixelPercent, '%') } testId="analytics-stat-valid" />
              <Metric label="Cloud / masked" value={ fmt(stats.cloudMaskedPercent, '%') } testId="analytics-stat-cloud" />
              <Metric label="Cover" value={ fmt(stats.coveragePercent, '%') } testId="analytics-stat-coverage" />
            </div>
          </>
        ) : !statisticsQ.isLoading ? (
          <div
            className="rounded-md border border-dashed border-border/80 p-3 text-[13px] leading-5 text-muted-foreground"
            data-testid="analytics-stats-empty"
          >
            Statistics are unavailable for this field and date.
          </div>
        ) : null }
      </section>

      <section data-testid="analytics-trend-section">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[11px] uppercase text-muted-foreground">Trend</p>
          { trendQ.isLoading && (
            <span className="text-[11px] text-muted-foreground" data-testid="analytics-trend-loading">
              Loading…
            </span>
          ) }
        </div>
        { !trendSourceId ? (
          <div
            className="rounded-md border border-dashed border-border/80 p-3 text-[13px] leading-5 text-muted-foreground"
            data-testid="analytics-trend-unavailable"
          >
            Select a source and date range to load trend analytics.
          </div>
        ) : trendQ.isError ? (
          <div className="rounded-md border border-destructive/30 p-3 text-[13px] leading-5 text-destructive" data-testid="analytics-trend-error">
            { errorMessage(trendQ.error, 'Unable to load trend.') }
          </div>
        ) : (
          <FieldTrendChart points={ trendQ.data?.points ?? [] } indexType={ indexType } />
        ) }

        <div className="mt-3 grid grid-cols-2 gap-2" data-testid="analytics-date-bounds">
          <div className="rounded-md border border-border/70 bg-background/40 px-2 py-1.5">
            <p className="text-[10px] uppercase text-muted-foreground">Start date</p>
            <p className="font-mono tnum text-[13px] text-foreground">{ trendStart ?? '—' }</p>
          </div>
          <div className="rounded-md border border-border/70 bg-background/40 px-2 py-1.5">
            <p className="text-[10px] uppercase text-muted-foreground">End date</p>
            <p className="font-mono tnum text-[13px] text-foreground">{ trendEnd ?? '—' }</p>
          </div>
        </div>
      </section>

      <div className="space-y-1 text-[11px] leading-4 text-muted-foreground">
        <p>{ statisticsQ.data?.metadata.formula ?? trendQ.data?.metadata.formula ?? `${indexType} formula unavailable` }</p>
        <p>
          Bands:{ ' ' }
          { (statisticsQ.data?.metadata.bands ?? trendQ.data?.metadata.bands ?? []).join(', ') || 'n/a' }
        </p>
        { trendQ.data?.fallbackReason && <p>{ trendQ.data.fallbackReason }</p> }
      </div>
    </div>
  );
}
