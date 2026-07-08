import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BarChart3, CalendarDays, ChevronDown, ChevronRight, Info, Layers, Lock, Plus, Sprout, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';
import { useFieldStatistics, useFieldTrend } from '@/lib/queries';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions, FieldStatisticsPipelineMetadata, FieldTrendPoint, Plot, VegetationCycleResponse } from '@/types/api';

type AnalyticsTab = 'crop-info' | 'chart' | 'activities';

interface IndexPanelProps {
  className?: string;
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
  /** Vegetation cycle data for the selected field. */
  vegetationData?: VegetationCycleResponse[];
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
  className,
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
  vegetationData,
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
  const metadata = statsResponse?.metadata;
  const warnings = metadata?.warnings ?? [];
  const metricsProvisional =
    statsResponse?.metricsProvisional ??
    metadata?.metricsProvisional ??
    sourceMetricsProvisional;
  const responseMaskMethod = statsResponse?.maskMethod ?? metadata?.maskMethod ?? sourceMaskMethod;
  const maskedPixels = statsResponse?.maskedPixels ?? statsResponse?.pixelCounts.maskedPixels;
  const analyticsCopy = metricsProvisional
    ? 'Akasha provisional-mask analytics'
    : 'Akasha masked-raster analytics';
  const enhanced = statsResponse?.enhanced ?? false;
  const resolutionMeters = statsResponse?.resolutionMeters ?? null;
  const provenanceNote = statsResponse?.provenanceNote ?? null;
  const pipeline = metadata?.pipeline ?? null;

  return (
    <section
      className={ cn('glass w-[320px] max-w-[84vw] overflow-hidden opacity-95', className) }
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
            className="rounded-md border border-dashed border-border/80 p-3 text-[13px] leading-5 text-muted-foreground"
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

          <div className="pr-1">
            <TabsContent
              value="crop-info"
              data-testid="index-panel-content-crop-info"
              className="space-y-2"
            >
              <CropInfoTab vegetationData={ vegetationData ?? [] } />
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
                formula={ metadata?.formula }
                bands={
                  metadata?.bands ?? trendQ.data?.metadata.bands ?? null
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
                pipeline={ pipeline }
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

const STAGE_LABELS = ['Seeding', 'Germination', 'Vegetative', 'Branching', 'Flowering', 'Fruiting', 'Ripening', 'Harvest'];

function CropInfoTab({
  vegetationData,
}: {
  vegetationData: VegetationCycleResponse[];
}) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    if (vegetationData.length > 0) return new Set([vegetationData[0].id]);
    return new Set();
  });

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const currentCrop = vegetationData[0];

  return (
    <div className="grid grid-cols-3 gap-3 pt-1">
      {/* ── Card 1: Crop Rotation ── */}
      <div
        data-testid="crop-info-card-crop-rotation"
        className="flex flex-col gap-3 rounded-lg border border-border/70 bg-background/40 p-4"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sprout className="size-4 text-primary" strokeWidth={ 1.75 } />
            <span className="text-[13px] font-semibold text-foreground">Crop rotation</span>
            <Info className="size-3 text-muted-foreground" strokeWidth={ 1.75 } />
          </div>
          <span className="text-[11px] font-medium text-primary cursor-default">Show all</span>
        </div>

        <p className="text-[12px] text-muted-foreground">
          Season: { currentCrop?.seasonName ?? '—' }
        </p>

        <div className="space-y-1">
          { vegetationData.length === 0 ? (
            <p className="text-[12px] text-muted-foreground">No crops added yet.</p>
          ) : (
            vegetationData.map((cycle, idx) => {
              const isExpanded = expandedIds.has(cycle.id);
              const isSelected = idx === 0;
              return (
                <div key={ cycle.id } className="rounded-md border border-border/60 bg-background/60">
                  <button
                    type="button"
                    onClick={ () => toggleExpand(cycle.id) }
                    className="flex w-full items-center gap-2 px-3 py-2 text-left"
                  >
                    { isExpanded
                      ? <ChevronDown className="size-3 shrink-0 text-muted-foreground" strokeWidth={ 2 } />
                      : <ChevronRight className="size-3 shrink-0 text-muted-foreground" strokeWidth={ 2 } />
                    }
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className="truncate text-[12px] font-medium text-foreground">
                        { cycle.cropName ?? 'Unknown crop' }
                      </span>
                      { isSelected && (
                        <span className="size-2 shrink-0 rounded-full bg-primary" />
                      ) }
                    </div>
                  </button>
                  { isExpanded && (
                    <div className="border-t border-border/50 px-3 py-2">
                      <p className="text-[11px] text-muted-foreground">
                        Sowing date: { cycle.sowingDate ?? '—' }
                      </p>
                    </div>
                  ) }
                </div>
              );
            })
          ) }
        </div>

        <Button
          type="button"
          size="sm"
          variant="outline"
          className="mt-auto h-7 gap-1 self-start text-[11px]"
          disabled
        >
          <Plus className="size-3" strokeWidth={ 1.75 } /> Add crop
        </Button>
      </div>

      {/* ── Card 2: Growth Stages ── */}
      <div
        data-testid="crop-info-card-growth-stages"
        className="flex flex-col gap-3 rounded-lg border border-border/70 bg-background/40 p-4"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sprout className="size-4 text-primary" strokeWidth={ 1.75 } />
            <span className="text-[13px] font-semibold text-foreground">Growth Stages</span>
            <Info className="size-3 text-muted-foreground" strokeWidth={ 1.75 } />
          </div>
          <span className="text-[11px] font-medium text-primary cursor-default">Edit</span>
        </div>

        <div className="relative py-2">
          <div className="absolute left-[7px] right-[7px] top-[11px] h-[2px] bg-border" />
          <div className="relative flex justify-between">
            { STAGE_LABELS.map((label, i) => (
              <div key={ label } className="flex flex-col items-center gap-1">
                <div
                  className={ cn(
                    'relative z-10 size-[14px] rounded-full border-2',
                    i === 0
                      ? 'border-primary bg-primary'
                      : 'border-border bg-background',
                  ) }
                />
                <span className={ cn(
                  'text-[9px] leading-tight text-center',
                  i === 0 ? 'text-primary font-medium' : 'text-muted-foreground',
                ) }>
                  { label }
                </span>
              </div>
            )) }
          </div>
        </div>

        <div className="mt-1 rounded-md border border-dashed border-border/70 bg-background/50 px-3 py-2.5 text-center">
          <p className="text-[11px] leading-4 text-muted-foreground">
            Growth stages will become available once crop vegetation begins.
          </p>
        </div>
      </div>

      {/* ── Card 3: Current Risks ── */}
      <div
        data-testid="crop-info-card-current-risks"
        className="flex flex-col gap-3 rounded-lg border border-border/70 bg-background/40 p-4 opacity-80"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="size-4 text-muted-foreground" strokeWidth={ 1.75 } />
            <span className="text-[13px] font-semibold text-foreground">Current risks</span>
            <Info className="size-3 text-muted-foreground" strokeWidth={ 1.75 } />
          </div>
          <Lock className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } aria-label="Plan-gated feature" />
        </div>

        <p className="text-[12px] leading-5 text-muted-foreground">
          Risk information on this field is available in the{' '}
          <span className="font-medium text-primary cursor-default">Essential</span>
          {' or '}
          <span className="font-medium text-primary cursor-default">Professional</span>
          {' '}plans.
        </p>
      </div>
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
  pipeline?: FieldStatisticsPipelineMetadata | null;
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
  pipeline,
}: ChartTabProps) {
  const maskMethod = sourceMaskMethod ?? null;
  const maskMetricLabel = sourceMetricsProvisional ? 'Masked' : 'Cloud / masked';

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
          <div className="flex gap-2 text-[13px] leading-5 text-destructive">
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

      { pipeline && <PipelineProvenance pipeline={ pipeline } /> }

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
          <div className="rounded-md border border-destructive/30 p-3 text-[13px] leading-5 text-destructive">
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

function valueOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function freshnessSummary(pipeline: FieldStatisticsPipelineMetadata): string | null {
  const freshness = pipeline.freshness;
  if (!freshness) return null;
  const stale = freshness.stale === true || freshness.status?.toUpperCase().includes('STALE');
  const label = stale ? 'Stale' : freshness.status ?? 'Fresh';
  const details = [
    freshness.latestProcessedSceneDate ? `latest ${freshness.latestProcessedSceneDate}` : null,
    freshness.staleAfter ? `stale after ${freshness.staleAfter}` : null,
    freshness.aoiId ? `AOI ${freshness.aoiId}` : null,
  ].filter(Boolean);
  return details.length > 0 ? `${label} · ${details.join(' · ')}` : label;
}

function PipelineProvenance({ pipeline }: { pipeline: FieldStatisticsPipelineMetadata }) {
  const qualityWarnings = pipeline.quality?.warnings ?? [];
  const freshnessWarnings = pipeline.freshness?.warnings ?? [];
  const warnings = [...qualityWarnings, ...freshnessWarnings];
  const freshness = freshnessSummary(pipeline);
  const route = pipeline.providerRoute ?? pipeline.source ?? null;
  const qualityStatus = pipeline.quality?.status ?? pipeline.status ?? null;

  return (
    <div
      className="rounded-md border border-primary/20 bg-primary/5 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
      data-testid="analytics-pipeline-provenance"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] text-primary/90">
            Sentinel-2 pipeline
          </p>
          <p className="mt-0.5 text-[13px] font-medium text-foreground">
            { valueOrDash(route) }
          </p>
        </div>
        { qualityStatus && (
          <span
            className="rounded-pill border border-primary/25 bg-background/60 px-2 py-0.5 text-[10px] uppercase text-primary"
            data-testid="analytics-pipeline-status"
          >
            { qualityStatus }
          </span>
        ) }
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px] leading-4">
        <DateField label="Scene" value={ pipeline.selectedSceneDate ?? null } />
        <DateField label="Requested" value={ pipeline.requestedDate ?? null } />
      </div>

      { freshness && (
        <p className="mt-2 text-[11px] leading-4 text-muted-foreground" data-testid="analytics-pipeline-freshness">
          Freshness: { freshness }
        </p>
      ) }
      { pipeline.quality?.reason && (
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground" data-testid="analytics-pipeline-quality">
          Quality: { pipeline.quality.reason }
        </p>
      ) }
      { pipeline.cloudMaskOptionsNote && (
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
          { pipeline.cloudMaskOptionsNote }
        </p>
      ) }
      { warnings.map((warning) => (
        <p key={ warning } className="mt-1 text-[11px] leading-4 text-amber-300" data-testid="analytics-pipeline-warning">
          { warning }
        </p>
      )) }
    </div>
  );
}

function ActivitiesTab() {
  return (
    <div className="space-y-3 pt-1" data-testid="activities-tab">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium text-foreground">Activities</p>
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
        <p className="text-[13px] text-muted-foreground">No activities added to this field.</p>
        <Button
          type="button"
          size="sm"
          variant="primary"
          className="h-8 px-3 text-[13px]"
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
      <p className="font-mono tnum text-[13px] text-foreground">{ value ?? '—' }</p>
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
      <p className={ compact ? 'text-[13px] font-medium text-foreground' : 'text-[15px] font-semibold text-foreground' }>
        { value }
      </p>
    </div>
  );
}
