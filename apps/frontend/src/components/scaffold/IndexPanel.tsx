import { useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';
import { useFieldStatistics, useFieldTrend } from '@/lib/queries';
import type { CloudMaskOptions, FieldScene, Plot } from '@/types/api';

interface IndexPanelProps {
  selectedPlot: Plot | null;
  selectedDate: string | null;
  sourceId: string | undefined;
  displayMode: string;
  supportedIndices: string[];
  cloudMask: CloudMaskOptions;
  selectedScene?: FieldScene | null;
}

const PLANNED_SECTIONS = [
  'Crop info',
  'Activities',
  'Crop rotation',
  'Growth stages',
  'Current risks',
  'NDVI value split',
];

function fmt(value: number | null | undefined, suffix = ''): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'n/a';
  return `${value.toFixed(2)}${suffix}`;
}

function startDateFor(endDate: string | null): string | undefined {
  if (!endDate) return undefined;
  const date = new Date(`${endDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 180);
  return date.toISOString().slice(0, 10);
}

function preferredIndex(displayMode: string, supported: string[]): string {
  const normalized = displayMode.toUpperCase();
  if (supported.includes(normalized)) return normalized;
  if (supported.includes('NDVI')) return 'NDVI';
  return supported[0] ?? 'NDVI';
}

export function IndexPanel({
  selectedPlot,
  selectedDate,
  sourceId,
  displayMode,
  supportedIndices,
  cloudMask,
  selectedScene,
}: IndexPanelProps) {
  const analyticsIndices = useMemo(
    () => supportedIndices.filter((index) => index !== 'NDWI_GREEN_NIR'),
    [supportedIndices],
  );
  const desiredIndex = preferredIndex(displayMode, analyticsIndices);
  const [indexType, setIndexType] = useState(desiredIndex);
  const activeIndexType = analyticsIndices.includes(indexType) ? indexType : desiredIndex;

  const startDate = useMemo(() => startDateFor(selectedDate), [selectedDate]);
  const statisticsQ = useFieldStatistics(selectedPlot?.id, {
    sourceId,
    acquisitionDate: selectedDate,
    indexType: activeIndexType,
    cloudMask,
  });
  const trendQ = useFieldTrend(selectedPlot?.id, {
    sourceId,
    indexType: activeIndexType,
    startDate,
    endDate: selectedDate ?? undefined,
    cloudMask,
  });

  const stats = statisticsQ.data?.statistics;
  const warnings = statisticsQ.data?.metadata.warnings ?? [];
  const providerCopy =
    trendQ.data?.provider === 'eos'
      ? 'Provider-backed trial analytics'
      : 'Akasha masked-raster fallback';

  return (
    <section
      className="glass w-[300px] max-w-[84vw] overflow-hidden opacity-95"
      data-testid="index-panel"
      aria-label="Field analytics"
    >
      <header className="contour flex items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="size-4 text-primary" strokeWidth={ 1.75 } />
          <h2 className="font-display text-base font-semibold text-foreground">Analytics</h2>
        </div>
        { selectedScene?.metricsProvisional && (
          <span className="rounded border border-amber-500/30 px-1.5 py-0.5 text-[10px] uppercase text-amber-300">
            provisional
          </span>
        ) }
      </header>

      <div className="flex max-h-[calc(100vh-220px)] flex-col gap-3 overflow-y-auto px-4 py-3">
        { !selectedPlot && (
          <div className="rounded-md border border-dashed border-border/80 p-3 text-[12px] leading-5 text-muted-foreground">
            Select a field to view cloud-masked statistics and trend analytics.
          </div>
        ) }

        { selectedPlot && (
          <>
            <div className="flex flex-wrap gap-1.5" aria-label="Analytics index">
              { analyticsIndices.map((index) => (
                <Button
                  key={ index }
                  type="button"
                  size="sm"
                  variant={ index === activeIndexType ? 'primary' : 'ghost' }
                  className="h-7 px-2 text-[11px]"
                  onClick={ () => setIndexType(index) }
                  data-testid={ `analytics-index-${index}` }
                >
                  { index }
                </Button>
              )) }
            </div>

            <div className="rounded-md border border-border/80 bg-background/50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[11px] uppercase text-muted-foreground">
                  { selectedDate ?? 'Latest date' }
                </p>
                { statisticsQ.isLoading && <Loader2 className="size-3.5 animate-spin text-primary" /> }
              </div>

              { statisticsQ.isError && (
                <div className="flex gap-2 text-[12px] leading-5 text-destructive">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span>{ statisticsQ.error instanceof Error ? statisticsQ.error.message : 'Unable to load statistics.' }</span>
                </div>
              ) }

              { stats && (
                <>
                  <div className="grid grid-cols-2 gap-2">
                    <Metric label="Mean" value={ fmt(stats.mean, '') } />
                    <Metric label="Std dev" value={ fmt(stats.stddev, '') } />
                    <Metric label="Min" value={ fmt(stats.min, '') } />
                    <Metric label="Max" value={ fmt(stats.max, '') } />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-1.5">
                    <Metric label="Valid" value={ fmt(stats.validPixelPercent, '%') } compact />
                    <Metric label="Cloud" value={ fmt(stats.cloudMaskedPercent, '%') } compact />
                    <Metric label="Cover" value={ fmt(stats.coveragePercent, '%') } compact />
                  </div>
                </>
              ) }
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] uppercase text-muted-foreground">Trend</p>
                { trendQ.isLoading && <Loader2 className="size-3.5 animate-spin text-primary" /> }
              </div>
              { trendQ.isError ? (
                <div className="rounded-md border border-destructive/30 p-3 text-[12px] leading-5 text-destructive">
                  { trendQ.error instanceof Error ? trendQ.error.message : 'Unable to load trend.' }
                </div>
              ) : (
                <FieldTrendChart points={ trendQ.data?.points ?? [] } indexType={ activeIndexType } />
              ) }
              <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
                { providerCopy }
                { trendQ.data?.fallbackReason ? ` · ${trendQ.data.fallbackReason}` : '' }
              </p>
            </div>

            <div className="space-y-1 text-[11px] leading-4 text-muted-foreground">
              <p>{ statisticsQ.data?.metadata.formula ?? `${activeIndexType} formula unavailable` }</p>
              <p>
                Bands: { statisticsQ.data?.metadata.bands?.join(', ') ?? trendQ.data?.metadata.bands?.join(', ') ?? 'n/a' }
              </p>
              { warnings.map((warning) => (
                <p key={ warning } className="text-amber-300">{ warning }</p>
              )) }
            </div>

            <div className="grid grid-cols-2 gap-1.5">
              { PLANNED_SECTIONS.map((section) => (
                <div
                  key={ section }
                  className="rounded border border-border/70 px-2 py-1.5 text-[11px] text-muted-foreground"
                >
                  <span className="block text-foreground/80">{ section }</span>
                  <span>Planned</span>
                </div>
              )) }
            </div>
          </>
        ) }
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div className={ compact ? 'rounded bg-muted/30 px-2 py-1' : 'rounded bg-muted/30 px-2 py-1.5' }>
      <p className="text-[10px] uppercase text-muted-foreground">{ label }</p>
      <p className={ compact ? 'text-[12px] font-medium text-foreground' : 'text-[15px] font-semibold text-foreground' }>
        { value }
      </p>
    </div>
  );
}
