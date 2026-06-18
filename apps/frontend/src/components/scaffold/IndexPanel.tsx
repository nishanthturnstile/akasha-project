import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, CalendarDays, Layers, Lock, Plus, Sprout, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';
import { useFieldStatistics, useFieldTrend } from '@/lib/queries';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions, FieldTrendPoint, Plot } from '@/types/api';

type AnalyticsTab = 'crop-info' | 'chart' | 'activities';

interface IndexPanelProps {
  selectedPlot: Plot | null;
  selectedDate: string | null;
  sourceId: string | undefined;
  displayMode: string;
  supportedIndices: string[];
  cloudMask: CloudMaskOptions;
  sourceMaskMethod?: string | null;
  sourceMetricsProvisional?: boolean;
  /** Inclusive lower bound (YYYY-MM-DD) carried from the timeline calendar range. */
  periodFrom?: string | null;
  /** Inclusive upper bound (YYYY-MM-DD) carried from the timeline calendar range. */
  periodTo?: string | null;
  /** Prefer LISS-4 high-resolution source when available (default true). */
  preferHighRes?: boolean;
  onPreferHighResChange?: (value: boolean) => void;
}

const TAB_ITEMS: { value: AnalyticsTab; label: string }[] = [
  { value: 'crop-info', label: 'Crop info' },
  { value: 'chart', label: 'Chart' },
  { value: 'activities', label: 'Activities' },
];

const HISTORICAL_YEARS = [2025, 2024, 2023, 2022];

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
  if (normalized === 'NDWI' && supported.includes('NDWI_GREEN_NIR')) return 'NDWI_GREEN_NIR';
  if (supported.includes('NDVI')) return 'NDVI';
  return supported[0] ?? 'NDVI';
}

function indexLabel(index: string): string {
  return index === 'NDWI_GREEN_NIR' ? 'NDWI' : index;
}

export function IndexPanel({
  selectedPlot,
  selectedDate,
  sourceId,
  displayMode,
  supportedIndices,
  cloudMask,
  sourceMaskMethod,
  sourceMetricsProvisional = false,
  periodFrom,
  periodTo,
  preferHighRes = true,
  onPreferHighResChange,
}: IndexPanelProps) {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('crop-info');

  const analyticsIndices = useMemo(() => supportedIndices.filter(Boolean), [supportedIndices]);
  const desiredIndex = preferredIndex(displayMode, analyticsIndices);
  const [indexType, setIndexType] = useState(desiredIndex);
  const activeIndexType = analyticsIndices.includes(indexType) ? indexType : desiredIndex;

  useEffect(() => {
    setIndexType(desiredIndex);
  }, [desiredIndex]);

  const trendStart = periodFrom ?? startDateFor(selectedDate);
  const trendEnd = periodTo ?? selectedDate ?? undefined;

  const statisticsQ = useFieldStatistics(selectedPlot?.id, {
    sourceId,
    acquisitionDate: selectedDate,
    indexType: activeIndexType,
    cloudMask,
    preferHighRes,
  });
  const trendQ = useFieldTrend(selectedPlot?.id, {
    sourceId,
    indexType: activeIndexType,
    startDate: trendStart,
    endDate: trendEnd,
    cloudMask,
  });

  const statsResponse = statisticsQ.data;
  const stats = statsResponse?.statistics;
  const warnings = statsResponse?.metadata.warnings ?? [];
  const metricsProvisional =
    statsResponse?.metricsProvisional ??
    statsResponse?.metadata.metricsProvisional ??
    sourceMetricsProvisional;
  const responseMaskMethod = statsResponse?.maskMethod ?? statsResponse?.metadata.maskMethod ?? sourceMaskMethod;
  const maskedPixels = statsResponse?.maskedPixels ?? statsResponse?.pixelCounts.maskedPixels;
  const analyticsCopy = metricsProvisional
    ? 'Akasha provisional-mask analytics'
    : 'Akasha masked-raster analytics';
  const enhanced = statsResponse?.enhanced ?? false;
  const resolutionMeters = statsResponse?.resolutionMeters ?? null;
  const provenanceNote = statsResponse?.provenanceNote ?? null;

  return (
    <section
      className="glass w-[320px] max-w-[84vw] overflow-hidden opacity-95"
      data-testid="index-panel"
      aria-label="Field analytics"
    >
      <header className="contour flex items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="size-4 text-primary" strokeWidth={ 1.75 } />
          <h2 className="font-display text-base font-semibold text-foreground">Analytics</h2>
        </div>
        { onPreferHighResChange != null && (
          <div className="flex items-center gap-1.5">
            <label
              htmlFor="analytics-pref-highres"
              className="cursor-pointer text-[11px] text-muted-foreground"
            >
              Hi-res
            </label>
            <Switch
              id="analytics-pref-highres"
              checked={ preferHighRes }
              onCheckedChange={ onPreferHighResChange }
              data-testid="analytics-prefer-high-res"
            />
          </div>
        ) }
      </header>

      { !selectedPlot ? (
        <div className="px-4 py-3">
          <div
            className="rounded-md border border-dashed border-border/80 p-3 text-[12px] leading-5 text-muted-foreground"
            data-testid="index-panel-no-field"
          >
            Select a field to view cloud-masked statistics and trend analytics.
          </div>
        </div>
      ) : (
        <Tabs
          value={ activeTab }
          onValueChange={ (next) => setActiveTab(next as AnalyticsTab) }
          className="px-4 pb-3 pt-2"
        >
          <TabsList
            className="grid w-full grid-cols-3"
            data-testid="index-panel-tabs"
            aria-label="Field analytics tabs"
          >
            { TAB_ITEMS.map((tab) => (
              <TabsTrigger
                key={ tab.value }
                value={ tab.value }
                data-testid={ `index-panel-tab-${tab.value}` }
              >
                { tab.label }
              </TabsTrigger>
            )) }
          </TabsList>

          <div className="max-h-[calc(100vh-260px)] overflow-y-auto pr-1">
            <TabsContent
              value="crop-info"
              data-testid="index-panel-content-crop-info"
              className="space-y-2"
            >
              <CropInfoTab seasonLabel={ selectedDate ?? null } />
            </TabsContent>

            <TabsContent
              value="chart"
              data-testid="index-panel-content-chart"
              className="space-y-3"
            >
              <ChartTab
                indices={ analyticsIndices }
                activeIndex={ activeIndexType }
                onSelectIndex={ setIndexType }
                stats={ stats }
                loading={ statisticsQ.isLoading }
                error={
                  statisticsQ.isError
                    ? statisticsQ.error instanceof Error
                      ? statisticsQ.error.message
                      : 'Unable to load statistics.'
                    : null
                }
                trendPoints={ trendQ.data?.points ?? [] }
                trendLoading={ trendQ.isLoading }
                trendError={
                  trendQ.isError
                    ? trendQ.error instanceof Error
                      ? trendQ.error.message
                      : 'Unable to load trend.'
                    : null
                }
                selectedDate={ selectedDate }
                analyticsCopy={ analyticsCopy }
                fallbackReason={ trendQ.data?.fallbackReason ?? null }
                formula={ statsResponse?.metadata.formula }
                bands={
                  statsResponse?.metadata.bands ?? trendQ.data?.metadata.bands ?? null
                }
                warnings={ warnings }
                periodFrom={ trendStart ?? null }
                periodTo={ trendEnd ?? null }
                sourceMaskMethod={ responseMaskMethod }
                sourceMetricsProvisional={ metricsProvisional }
                maskedPixels={ maskedPixels }
                enhanced={ enhanced }
                resolutionMeters={ resolutionMeters }
                provenanceNote={ provenanceNote }
              />
            </TabsContent>

            <TabsContent
              value="activities"
              data-testid="index-panel-content-activities"
              className="space-y-3"
            >
              <ActivitiesTab />
            </TabsContent>
          </div>
        </Tabs>
      ) }
    </section>
  );
}

function CropInfoTab({ seasonLabel }: { seasonLabel: string | null }) {
  return (
    <div className="space-y-2 pt-1">
      <CropInfoCard
        testId="crop-info-card-crop-rotation"
        title="Crop rotation"
        icon={ <Sprout className="size-3.5 text-primary" strokeWidth={ 1.75 } /> }
      >
        <p className="text-[11px] text-muted-foreground">
          Season · { seasonLabel ? `as of ${seasonLabel}` : 'no scene selected' }
        </p>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 px-2 text-[11px]"
            data-testid="crop-info-add-crop"
            disabled
          >
            <Plus className="size-3" strokeWidth={ 1.75 } /> Add crop
          </Button>
          <span className="text-[11px] text-muted-foreground">Show all</span>
        </div>
      </CropInfoCard>

      <CropInfoCard
        testId="crop-info-card-sown-area"
        title="Sown area detected"
        locked
      >
        <p className="text-[11px] leading-4 text-muted-foreground">
          Sown-area detection is available on the Essential or Professional plan.
        </p>
      </CropInfoCard>

      <CropInfoCard
        testId="crop-info-card-management-guide"
        title="Crop management guide"
      >
        <p className="text-[11px] leading-4 text-muted-foreground">
          Browse Akasha crop-management notes for each supported crop.
        </p>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-0 text-[11px] text-primary"
          data-testid="crop-info-guide-link"
          disabled
        >
          Go to guide
        </Button>
      </CropInfoCard>

      <CropInfoCard
        testId="crop-info-card-growth-stages"
        title="Growth stages"
      >
        <p className="text-[11px] leading-4 text-muted-foreground">
          Select a crop to view its growth stages.
        </p>
      </CropInfoCard>

      <CropInfoCard
        testId="crop-info-card-current-risks"
        title="Current risks"
        locked
      >
        <p className="text-[11px] leading-4 text-muted-foreground">
          Risk diagnostics are available on the Essential or Professional plan.
        </p>
      </CropInfoCard>

      <CropInfoCard
        testId="crop-info-card-ndvi-split"
        title="NDVI value split"
        locked
      >
        <p className="text-[11px] leading-4 text-muted-foreground">
          Vegetation-class split is available on the Essential or Professional plan.
        </p>
      </CropInfoCard>
    </div>
  );
}

function CropInfoCard({
  title,
  children,
  testId,
  icon,
  locked = false,
}: {
  title: string;
  children: React.ReactNode;
  testId: string;
  icon?: React.ReactNode;
  locked?: boolean;
}) {
  return (
    <div
      data-testid={ testId }
      className={ cn(
        'rounded-md border border-border/70 bg-background/40 p-2.5',
        locked && 'opacity-80',
      ) }
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          { icon }
          <p className="text-[12px] font-medium text-foreground">{ title }</p>
        </div>
        { locked && (
          <Lock
            className="size-3 text-muted-foreground"
            strokeWidth={ 1.75 }
            aria-label="Plan-gated feature"
          />
        ) }
      </div>
      <div className="space-y-1.5">{ children }</div>
    </div>
  );
}

interface ChartTabProps {
  indices: string[];
  activeIndex: string;
  onSelectIndex: (next: string) => void;
  stats: {
    mean: number | null;
    stddev: number | null;
    min: number | null;
    max: number | null;
    validPixelPercent: number | null;
    cloudMaskedPercent: number | null;
    coveragePercent: number | null;
  } | undefined;
  loading: boolean;
  error: string | null;
  trendPoints: FieldTrendPoint[];
  trendLoading: boolean;
  trendError: string | null;
  selectedDate: string | null;
  analyticsCopy: string;
  fallbackReason: string | null;
  formula?: string | null;
  bands: string[] | null | undefined;
  warnings: string[];
  periodFrom: string | null;
  periodTo: string | null;
  sourceMaskMethod?: string | null;
  sourceMetricsProvisional?: boolean;
  maskedPixels?: number | null;
  /** Provenance from LISS-4 best-resolution resolver. */
  enhanced?: boolean;
  resolutionMeters?: number | null;
  provenanceNote?: string | null;
}

function ChartTab({
  indices,
  activeIndex,
  onSelectIndex,
  stats,
  loading,
  error,
  trendPoints,
  trendLoading,
  trendError,
  selectedDate,
  analyticsCopy,
  fallbackReason,
  formula,
  bands,
  warnings,
  periodFrom,
  periodTo,
  sourceMaskMethod,
  sourceMetricsProvisional = false,
  maskedPixels,
  enhanced = false,
  resolutionMeters,
  provenanceNote,
}: ChartTabProps) {
  const maskMethod = sourceMaskMethod ?? null;
  const maskMetricLabel = sourceMetricsProvisional ? 'Masked' : 'Cloud';

  return (
    <div className="space-y-3 pt-1">
      <div className="flex flex-wrap gap-1.5" aria-label="Analytics index">
        { indices.map((index) => (
          <Button
            key={ index }
            type="button"
            size="sm"
            variant={ index === activeIndex ? 'primary' : 'ghost' }
            className="h-7 px-2 text-[11px]"
            onClick={ () => onSelectIndex(index) }
            data-testid={ `analytics-index-${index}` }
          >
            { indexLabel(index) }
          </Button>
        )) }
      </div>

      <div className="rounded-md border border-border/80 bg-background/50 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-[11px] uppercase text-muted-foreground">
            { selectedDate ?? 'Latest date' }
          </p>
          { loading && (
            <span
              className="text-[11px] text-muted-foreground"
              data-testid="analytics-stats-loading"
            >
              Loading…
            </span>
          ) }
        </div>

        { enhanced && (
          <div
            className="mb-2 flex items-center gap-1 rounded-pill border border-primary/30 bg-primary/10 px-2 py-0.5 w-fit text-[11px] font-medium text-primary"
            data-testid="analytics-enhanced-badge"
          >
            <Zap className="size-3 shrink-0" strokeWidth={ 1.75 } />
            Enhanced { resolutionMeters != null ? `${resolutionMeters} m` : '' } (LISS-4)
          </div>
        ) }

        { error && (
          <div className="flex gap-2 text-[12px] leading-5 text-destructive">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            <span>{ error }</span>
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
              <Metric label={ maskMetricLabel } value={ fmt(stats.cloudMaskedPercent, '%') } compact />
              <Metric label="Cover" value={ fmt(stats.coveragePercent, '%') } compact />
            </div>
          </>
        ) }
      </div>

      <div data-testid="analytics-chart-section">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[11px] uppercase text-muted-foreground">Trend</p>
          { trendLoading && (
            <span
              className="text-[11px] text-muted-foreground"
              data-testid="analytics-trend-loading"
            >
              Loading…
            </span>
          ) }
        </div>
        { trendError ? (
          <div className="rounded-md border border-destructive/30 p-3 text-[12px] leading-5 text-destructive">
            { trendError }
          </div>
        ) : (
          <FieldTrendChart points={ trendPoints } indexType={ activeIndex } />
        ) }

        {/* Multi-year series toggles (current year active, prior years plan-locked). */ }
        <div
          className="mt-2 flex flex-wrap items-center gap-1.5"
          data-testid="analytics-year-toggles"
          aria-label="Multi-year series"
        >
          <span className="inline-flex h-6 items-center gap-1 rounded-pill border border-primary/40 bg-primary/15 px-2 text-[11px] font-medium text-primary">
            <Layers className="size-3" strokeWidth={ 1.75 } />
            { activeIndex } · current
          </span>
          { HISTORICAL_YEARS.map((year) => (
            <span
              key={ year }
              className="inline-flex h-6 items-center gap-1 rounded-pill border border-border/60 bg-card/40 px-2 text-[11px] text-muted-foreground"
              data-testid={ `analytics-year-${year}` }
            >
              <Lock className="size-3" strokeWidth={ 1.75 } />
              { activeIndex } { year }
            </span>
          )) }
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2" data-testid="analytics-date-bounds">
          <DateField label="Start date" value={ periodFrom } />
          <DateField label="End date" value={ periodTo } />
        </div>

        {/* Weather overlay placeholder. */ }
        <div
          className="mt-2 flex items-center justify-between rounded-md border border-border/70 bg-background/40 px-2 py-1.5"
          data-testid="analytics-weather-overlay"
        >
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <CalendarDays className="size-3" strokeWidth={ 1.75 } />
            <span>Weather overlay</span>
          </div>
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <Lock className="size-3" strokeWidth={ 1.75 } /> Plan-gated
          </span>
        </div>

        <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
          { analyticsCopy }
          { fallbackReason ? ` · ${fallbackReason}` : '' }
        </p>
      </div>

      <div className="space-y-1 text-[11px] leading-4 text-muted-foreground">
        <p>{ formula ?? `${activeIndex} formula unavailable` }</p>
        <p>Bands: { bands && bands.length > 0 ? bands.join(', ') : 'n/a' }</p>
        { maskMethod && (
          <p data-testid="analytics-mask-method">
            { sourceMetricsProvisional ? 'Provisional mask' : 'Mask' }: { maskMethod }
          </p>
        ) }
        { typeof maskedPixels === 'number' && Number.isFinite(maskedPixels) && (
          <p data-testid="analytics-masked-pixels">Masked pixels: { maskedPixels }</p>
        ) }
        { (activeIndex === 'NDMI' || provenanceNote) && (
          <p data-testid="analytics-ndmi-note" className="text-amber-300">
            { provenanceNote ?? 'Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band.' }
          </p>
        ) }
        { warnings.map((warning) => (
          <p key={ warning } className="text-amber-300">{ warning }</p>
        )) }
      </div>
    </div>
  );
}

function ActivitiesTab() {
  return (
    <div className="space-y-3 pt-1" data-testid="activities-tab">
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-medium text-foreground">Activities</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 px-2 text-[11px]"
          data-testid="activities-add-trigger"
          disabled
        >
          <Plus className="size-3" strokeWidth={ 1.75 } /> Add
        </Button>
      </div>
      <div
        className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border/80 p-4 text-center"
        data-testid="activities-empty-state"
      >
        <p className="text-[12px] text-muted-foreground">No activities added to this field.</p>
        <Button
          type="button"
          size="sm"
          variant="primary"
          className="h-8 px-3 text-[12px]"
          data-testid="activities-add-button"
          disabled
        >
          <Plus className="size-3.5" strokeWidth={ 1.75 } /> Add activity
        </Button>
      </div>
    </div>
  );
}

function DateField({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-border/70 bg-background/40 px-2 py-1.5">
      <p className="text-[10px] uppercase text-muted-foreground">{ label }</p>
      <p className="font-mono tnum text-[12px] text-foreground">{ value ?? '—' }</p>
    </div>
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
