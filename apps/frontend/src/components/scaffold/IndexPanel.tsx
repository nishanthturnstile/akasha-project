import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, Info, Layers, Lock, Pencil, Plus, Satellite, Sprout, X, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FieldTrendChart } from '@/components/monitoring/FieldTrendChart';
import { NdviValueSplit } from '@/components/analytics/NdviValueSplit';
import { useFieldMonitoringEvidence, useFieldStatistics, useFieldTrend, useSeasons, useUpdateVegetationCycleGrowthStages } from '@/lib/queries';
import { radarEvidenceDescription } from '@/lib/radarEvidence';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions, FieldStatisticsPipelineMetadata, FieldTrendPoint, NdviValueSplit as NdviValueSplitData, Plot, SarSupport, VegetationCycleGrowthStage, VegetationCycleResponse } from '@/types/api';

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
  /** Vegetation cycle data for the selected field. */
  vegetationData?: VegetationCycleResponse[];
  /** Season IDs the selected field belongs to. */
  seasonIds?: string[];
  /** Called when user clicks "Show all" on the crop rotation card. */
  onShowAllCrops?: (seasonId?: string) => void;
  radarEvidenceVisible?: boolean;
  onRadarEvidenceVisibleChange?: (visible: boolean) => void;
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
  vegetationData,
  seasonIds,
  onShowAllCrops,
  radarEvidenceVisible = false,
  onRadarEvidenceVisibleChange,
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
  const ndviStatisticsQ = useFieldStatistics(
    analyticsIndices.includes('NDVI') ? selectedPlot?.id : null,
    {
      sourceId,
      acquisitionDate: selectedDate,
      indexType: 'NDVI',
      cloudMask,
      preferHighRes,
    },
  );
  const trendQ = useFieldTrend(selectedPlot?.id, {
    sourceId,
    indexType: activeIndexType,
    startDate: trendStart,
    endDate: trendEnd,
    cloudMask,
  });
  const evidenceQ = useFieldMonitoringEvidence(selectedPlot?.id, {
    sourceId,
    indexType: activeIndexType,
    targetDate: selectedDate,
    includeRadar: true,
    enabled: Boolean(onRadarEvidenceVisibleChange),
  });
  const monitoringEvidence = evidenceQ.data;
  const radarEvidence = monitoringEvidence?.radar;

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
  const sarSupport = statsResponse?.sarSupport ?? null;

  return (
    <section
      className={ className }
      data-testid="index-panel"
      aria-label="Field analytics"
    >
      { !selectedPlot ? (
        <div className="px-4 py-2">
          <div
            className="rounded-md border border-dashed border-border/80 p-2 text-xs leading-4 text-muted-foreground"
            data-testid="index-panel-no-field"
          >
            Select a field to view cloud-masked statistics and trend analytics.
          </div>
        </div>
      ) : (
        <Tabs
          value={ activeTab }
          onValueChange={ (next) => setActiveTab(next as AnalyticsTab) }
          className="px-4 pb-2 pt-1.5"
        >
          { monitoringEvidence?.optical && (
            monitoringEvidence.optical.status !== 'usable' || radarEvidence?.status === 'AVAILABLE'
          ) && (
            <div
              className="mb-2 rounded-md border border-info/30 bg-info/10 p-2.5 text-[11px] leading-4"
              data-testid="field-monitoring-radar-evidence"
            >
              <div className="flex items-start gap-2">
                <Satellite className="mt-0.5 size-3.5 shrink-0 text-info" strokeWidth={ 1.75 } />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-foreground">
                    { monitoringEvidence.optical.status === 'usable'
                      ? 'Radar field evidence'
                      : 'Radar support for an optical gap' }
                  </p>
                  <p className="mt-0.5 text-muted-foreground">
                    { radarEvidence?.status === 'AVAILABLE'
                      ? radarEvidenceDescription(radarEvidence.sourceId, radarEvidence.acquisitionDate, radarEvidence.displayedPolarization)
                      : radarEvidence?.reason ?? radarEvidence?.triggerReason ?? 'Radar evidence is unavailable.' }
                  </p>
                  { radarEvidence?.status === 'AVAILABLE' && (
                    <div className="mt-1.5 space-y-1.5">
                      { radarEvidence.change?.status === 'AVAILABLE' && radarEvidence.change.referenceDate && (
                        <div className="rounded border border-info/20 bg-background/30 px-2 py-1" data-testid="radar-temporal-change">
                          <p className="font-medium text-foreground">
                            Compared with { radarEvidence.change.referenceDate }
                          </p>
                          <p className="text-muted-foreground">
                            { radarEvidence.change.bands.map((band) => (
                              `${band.polarization} ${band.medianDeltaDb >= 0 ? '+' : ''}${band.medianDeltaDb.toFixed(2)} dB`
                            )).join(' · ') }
                          </p>
                        </div>
                      ) }
                      { radarEvidence.baseline?.status === 'INSUFFICIENT_OBSERVATIONS' && (
                        <p className="text-muted-foreground" data-testid="radar-baseline-status">
                          { radarEvidence.baseline.priorObservationCount } comparable prior observation{ radarEvidence.baseline.priorObservationCount === 1 ? '' : 's' } available; { radarEvidence.baseline.requiredPriorObservations } required for a field baseline.
                        </p>
                      ) }
                      { radarEvidence.baseline?.status === 'AVAILABLE' && (
                        <div className="rounded border border-info/20 bg-background/30 px-2 py-1" data-testid="radar-baseline-status">
                          <p className="font-medium text-foreground">
                            Field baseline ({ radarEvidence.baseline.priorObservationCount } prior passes)
                          </p>
                          <p className="text-muted-foreground">
                            { radarEvidence.baseline.bands
                                .flatMap((band) => band.robustDeviation === null
                                  ? []
                                  : [`${band.polarization} ${band.robustDeviation >= 0 ? '+' : ''}${band.robustDeviation.toFixed(2)}`])
                                .join(' · ') } relative deviation
                          </p>
                        </div>
                      ) }
                      { radarEvidence.comparison?.status === 'METADATA_INCOMPLETE' && (
                        <p className="text-muted-foreground" data-testid="radar-comparison-status">
                          This pass can be viewed, but its acquisition metadata is incomplete for temporal comparison.
                        </p>
                      ) }
                      { radarEvidence.comparison?.status === 'NO_COMPARABLE_HISTORY' && (
                        <p className="text-muted-foreground" data-testid="radar-comparison-status">
                          No earlier pass with compatible acquisition geometry is available.
                        </p>
                      ) }
                      { radarEvidence.baseline?.status === 'DEGENERATE_BASELINE' && (
                        <p className="text-muted-foreground" data-testid="radar-baseline-status">
                          The historical spread is too small to calculate a reliable field-relative deviation.
                        </p>
                      ) }
                      <p className="text-muted-foreground">
                        Radar change can reflect crop structure, surface condition, or acquisition effects. It is not NDVI or a diagnosis.
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-muted-foreground">
                          { radarEvidence.coveragePercent?.toFixed(1) }% coverage · { radarEvidence.quality?.confidence ?? 'unknown' } confidence
                        </span>
                        <Button
                          type="button"
                          size="sm"
                          variant={ radarEvidenceVisible ? 'primary' : 'ghost' }
                          className="h-6 px-2 text-[11px]"
                          onClick={ () => onRadarEvidenceVisibleChange?.(!radarEvidenceVisible) }
                          disabled={ !onRadarEvidenceVisibleChange }
                          data-testid="toggle-radar-evidence"
                        >
                          { radarEvidenceVisible ? 'Show optical' : 'Show radar layer' }
                        </Button>
                      </div>
                    </div>
                  ) }
                </div>
              </div>
            </div>
          ) }
          <TabsList
            className="grid w-full grid-cols-3 h-8 gap-0 rounded-none border-0 bg-transparent p-0"
            data-testid="index-panel-tabs"
            aria-label="Field analytics tabs"
          >
            { TAB_ITEMS.map((tab) => (
              <TabsTrigger
                key={ tab.value }
                value={ tab.value }
                data-testid={ `index-panel-tab-${tab.value}` }
                className="h-8 px-0 rounded-none border-0 bg-transparent text-sm text-muted-foreground shadow-none data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
              >
                <span className={ cn('inline-block pb-0.5 border-b-2', activeTab === tab.value ? 'border-primary' : 'border-transparent') }>
                  { tab.label }
                </span>
              </TabsTrigger>
            )) }
          </TabsList>

          <div className="pr-1">
            <TabsContent
              value="crop-info"
              data-testid="index-panel-content-crop-info"
              className="mt-1.5 space-y-1.5"
            >
              <CropInfoTab
                vegetationData={ vegetationData ?? [] }
                seasonIds={ seasonIds }
                onShowAllCrops={ onShowAllCrops }
                valueSplit={ ndviStatisticsQ.data?.valueSplit ?? null }
                selectedDate={ selectedDate }
              />
            </TabsContent>

            <TabsContent
              value="chart"
              data-testid="index-panel-content-chart"
              className="mt-1.5 space-y-3"
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
                sarSupport={ sarSupport }
              />
            </TabsContent>

            <TabsContent
              value="activities"
              data-testid="index-panel-content-activities"
              className="mt-1.5 space-y-3"
            >
              <ActivitiesTab />
            </TabsContent>
          </div>
        </Tabs>
      ) }
    </section>
  );
}

function CropInfoTab({
  vegetationData,
  seasonIds,
  onShowAllCrops,
  valueSplit,
  selectedDate,
}: {
  vegetationData: VegetationCycleResponse[];
  seasonIds?: string[];
  onShowAllCrops?: (seasonId?: string) => void;
  valueSplit: NdviValueSplitData | null;
  selectedDate: string | null;
}) {
  const seasonsQ = useSeasons();
  const seasonNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const s of seasonsQ.data ?? []) map[s.id] = s.name;
    return map;
  }, [seasonsQ.data]);

  const seasonIdsFromField = (seasonIds?.length ? seasonIds : [
    ...new Set(vegetationData.map((v) => v.seasonId)),
  ]).filter(Boolean);

  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    if (vegetationData.length > 0) return new Set([vegetationData[0].id]);
    return new Set();
  });

  const [selectedCropId, setSelectedCropId] = useState<string | null>(() =>
    vegetationData.length > 0 ? vegetationData[0].id : null,
  );
  const selectedCycle = vegetationData.find((cycle) => cycle.id === selectedCropId) ?? vegetationData[0] ?? null;

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))] gap-2 pt-0.5">
      {/* ── Card 1: Crop Rotation ── */ }
      <div
        data-testid="crop-info-card-crop-rotation"
        className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background/40 p-2.5"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sprout className="size-4 text-primary" strokeWidth={ 1.75 } />
            <span className="text-sm font-semibold text-foreground">Crop rotation</span>
            <Info className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
          </div>
          <button type="button" onClick={ () => onShowAllCrops?.() } className="text-xs font-medium text-primary hover:underline">Show all</button>
        </div>

        <div className="space-y-1.5">
          { seasonIdsFromField.length === 0 && vegetationData.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">No crops added yet.</p>
          ) : (
            seasonIdsFromField.map((sid) => {
              const cycles = vegetationData
                .filter((v) => v.seasonId === sid)
                .sort((a, b) => {
                  if (b.year !== a.year) return b.year - a.year;
                  const dateA = a.sowingDate ? new Date(a.sowingDate).getTime() : 0;
                  const dateB = b.sowingDate ? new Date(b.sowingDate).getTime() : 0;
                  return dateB - dateA;
                });
              const sname = cycles.find((c) => c.seasonName)?.seasonName ?? seasonNameMap[sid] ?? sid;
              return (
                <div key={ sid } className="rounded-md border border-border/60 bg-background/50">
                  <div className="flex items-center justify-between px-2.5 py-1 bg-muted/30 border-b border-border/40">
                    <span className="text-xs font-semibold text-foreground">Season : { sname }</span>
                    { cycles.length > 0 && onShowAllCrops && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-6 gap-1 text-[11px] text-primary hover:text-primary"
                        onClick={ (e) => { e.stopPropagation(); onShowAllCrops(sid); } }
                      >
                        <Plus className="size-3" strokeWidth={ 1.75 } /> Add crop
                      </Button>
                    ) }
                  </div>
                  { cycles.length > 0 ? (
                    <div className="p-1 space-y-0.5">
                      { cycles.map((cycle) => {
                        const isExpanded = expandedIds.has(cycle.id);
                        const isSelected = cycle.id === selectedCropId;
                        return (
                          <div key={ cycle.id } className="rounded-md border border-border/60 bg-background/60">
                            <div className="flex items-center">
                              <button
                                type="button"
                                onClick={ () => { toggleExpand(cycle.id); setSelectedCropId(cycle.id); } }
                                className="flex flex-1 items-center gap-2 px-2 py-1.5 text-left"
                              >
                                { isExpanded
                                  ? <ChevronDown className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 2 } />
                                  : <ChevronRight className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 2 } />
                                }
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                  <span className="truncate text-[13px] font-medium text-foreground">
                                    { cycle.cropName ?? 'Unknown crop' }
                                  </span>
                                </div>
                              </button>
                              <button
                                type="button"
                                onClick={ (e) => { e.stopPropagation(); setSelectedCropId(cycle.id); setExpandedIds(new Set([cycle.id])); } }
                                className="flex items-center justify-center shrink-0 pr-2"
                                aria-label={ `Select ${cycle.cropName ?? 'crop'}` }
                              >
                                <span
                                  className={ cn(
                                    'flex size-4 items-center justify-center rounded-full border-2 transition-colors',
                                    isSelected
                                      ? 'border-primary'
                                      : 'border-muted-foreground/40',
                                  ) }
                                >
                                  { isSelected && <span className="size-2 rounded-full bg-primary" /> }
                                </span>
                              </button>
                            </div>
                            { isExpanded && (
                              <div className="border-t border-border/50 px-2.5 py-1.5 space-y-0.5">
                                { cycle.varietyName && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Variety:</span><span className="text-xs text-foreground">{ cycle.varietyName }</span></div> }
                                { cycle.sowingDate && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Sowing date:</span><span className="text-xs text-foreground">{ cycle.sowingDate }</span></div> }
                                { cycle.harvestingDate && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Harvesting date:</span><span className="text-xs text-foreground">{ cycle.harvestingDate }</span></div> }
                                { cycle.maturity && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Maturity:</span><span className="text-xs text-foreground">{ cycle.maturity }</span></div> }
                                { cycle.irrigationTypeName && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Irrigation:</span><span className="text-xs text-foreground">{ cycle.irrigationTypeName }</span></div> }
                                { cycle.tillageTypeName && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Tillage:</span><span className="text-xs text-foreground">{ cycle.tillageTypeName }</span></div> }
                                { cycle.targetYield != null && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Target yield:</span><span className="text-xs text-foreground">{ cycle.targetYield } t/ha</span></div> }
                                { cycle.actualYield != null && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Actual yield:</span><span className="text-xs text-foreground">{ cycle.actualYield } t/ha</span></div> }
                                { cycle.fertilizer && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Fertilizer:</span><span className="text-xs text-foreground">{ cycle.fertilizer }</span></div> }
                                { cycle.hybrid && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Hybrid:</span><span className="text-xs text-foreground">{ cycle.hybrid }</span></div> }
                                { cycle.notes && <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-muted-foreground shrink-0">Notes:</span><span className="text-xs text-foreground">{ cycle.notes }</span></div> }
                                { !cycle.notes && onShowAllCrops && (
                                  <button
                                    type="button"
                                    onClick={ (e) => { e.stopPropagation(); onShowAllCrops(sid); } }
                                    className="mt-1 flex w-full items-center gap-1 text-[11px] font-medium text-primary hover:text-primary/80 transition-colors"
                                  >
                                    <Plus className="size-3" strokeWidth={ 2 } />
                                    Notes
                                  </button>
                                ) }
                              </div>
                            ) }
                          </div>
                        );
                      }) }
                    </div>
                  ) : (
                    <div className="flex items-center justify-between px-3 py-2">
                      <span className="text-[13px] text-muted-foreground">No crops added for this season.</span>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 gap-1 text-[11px]"
                        onClick={ () => onShowAllCrops?.(sid) }
                      >
                        <Plus className="size-3" strokeWidth={ 1.75 } /> Add vegetation cycle
                      </Button>
                    </div>
                  ) }
                </div>
              );
            })
          ) }
        </div>
      </div>

      <GrowthStagesCard key={ selectedCycle?.id ?? 'no-cycle' } cycle={ selectedCycle } />

      { valueSplit?.indexType === 'NDVI' && (
        <NdviValueSplit valueSplit={ valueSplit } selectedDate={ selectedDate } />
      ) }

      {/* ── Card 4: Current Risks ── */ }
      <div
        data-testid="crop-info-card-current-risks"
        className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background/40 p-2.5 opacity-80"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="size-4 text-muted-foreground" strokeWidth={ 1.75 } />
            <span className="text-sm font-semibold text-foreground">Current risks</span>
            <Info className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
          </div>
          <Lock className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } aria-label="Plan-gated feature" />
        </div>

        <p className="text-[13px] leading-5 text-muted-foreground">
          Risk information on this field is available in the{ ' ' }
          <span className="font-medium text-primary cursor-default">Essential</span>
          { ' or ' }
          <span className="font-medium text-primary cursor-default">Professional</span>
          { ' ' }plans.
        </p>
      </div>
    </div>
  );
}

function GrowthStagesCard({ cycle }: { cycle: VegetationCycleResponse | null }) {
  const updateStages = useUpdateVegetationCycleGrowthStages();
  const [editing, setEditing] = useState(false);
  const [draftStages, setDraftStages] = useState<VegetationCycleGrowthStage[]>(
    cycle?.growthStages ?? [],
  );
  const [activeSeq, setActiveSeq] = useState<number | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const swipeStartX = useRef<number | null>(null);

  const stages = cycle?.growthStages ?? [];
  const todayIso = new Date().toISOString().slice(0, 10);
  const savedStages = stages.filter((stage) => stage.startDate);
  const lastStartedStage = [...savedStages]
    .filter((stage) => (stage.startDate ?? '') <= todayIso)
    .sort((left, right) => right.seq - left.seq)[0] ?? null;
  const currentStage = (() => {
    if (!lastStartedStage) return null;
    if (lastStartedStage.startDate === todayIso) return lastStartedStage;

    const nextStage = stages.find((stage) => stage.seq > lastStartedStage.seq);
    if (nextStage && !nextStage.startDate) return nextStage;
    return lastStartedStage;
  })();
  const displayedSeq = selectedSeq ?? currentStage?.seq ?? null;
  const selectedStage = stages.find((stage) => stage.seq === displayedSeq) ?? null;
  const selectedIndex = selectedStage ? stages.findIndex((stage) => stage.seq === selectedStage.seq) : -1;

  const openEditor = (seq?: number) => {
    if (!cycle) return;
    const nextStages = cycle.growthStages ?? [];
    setDraftStages(nextStages);
    setActiveSeq(seq ?? nextStages.find((stage) => !stage.startDate)?.seq ?? nextStages[0]?.seq ?? null);
    setEditing(true);
  };

  const closeEditor = () => {
    setDraftStages(cycle?.growthStages ?? []);
    setActiveSeq(null);
    setEditing(false);
  };

  const applyStageDate = (seq: number) => {
    if (!cycle) return;
    const stage = draftStages.find((item) => item.seq === seq);
    const savedStage = stages.find((item) => item.seq === seq);
    if (!stage || (!stage.startDate && !savedStage?.startDate)) return;
    updateStages.mutate(
      {
        cycleId: cycle.id,
        payload: {
          stages: [{ seq, startDate: stage.startDate }],
        },
      },
      {
        onSuccess: () => {
          setSelectedSeq(seq);
          setActiveSeq(null);
        },
      },
    );
  };

  const cancelStageDate = (seq: number) => {
    const savedStage = stages.find((stage) => stage.seq === seq);
    setDraftStages((current) => current.map((stage) => (
      stage.seq === seq ? { ...stage, startDate: savedStage?.startDate ?? null } : stage
    )));
    setActiveSeq(null);
  };

  const moveSelectedStage = (offset: number) => {
    if (stages.length === 0) return;
    const nextIndex = Math.min(Math.max(selectedIndex + offset, 0), stages.length - 1);
    setSelectedSeq(stages[nextIndex].seq);
  };

  const handleRailPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest('button')) return;
    swipeStartX.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleRailPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest('button')) return;
    if (swipeStartX.current === null) return;
    const deltaX = event.clientX - swipeStartX.current;
    swipeStartX.current = null;
    if (Math.abs(deltaX) < 32) return;
    if (selectedIndex < 0) {
      setSelectedSeq(deltaX < 0 ? stages[0].seq : stages[stages.length - 1].seq);
      return;
    }
    moveSelectedStage(deltaX < 0 ? 1 : -1);
  };

  const formatStartDate = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  const shiftDate = (value: string, days: number) => {
    const date = new Date(`${value}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().slice(0, 10);
  };

  return (
    <Dialog.Root open={ editing } onOpenChange={ (open) => { if (open) setEditing(true); else closeEditor(); } }>
      <div
        data-testid="crop-info-card-growth-stages"
        className="flex flex-col gap-1.5 rounded-lg border border-border/70 bg-background/40 p-2.5"
      >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sprout className="size-4 text-primary" strokeWidth={ 1.75 } />
          <span className="text-sm font-semibold text-foreground">Growth Stages</span>
          <Info className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
        </div>
        { cycle && (
          <Dialog.Trigger asChild>
            <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={ () => openEditor() }>
              Edit
            </button>
          </Dialog.Trigger>
        ) }
      </div>

      { !cycle ? (
        <p className="text-xs text-muted-foreground">Select a crop to view its growth stages.</p>
      ) : stages.length === 0 ? (
        <p className="text-xs text-muted-foreground">No growth stages are configured for this crop.</p>
      ) : (
        <>
          <div
            className="relative pb-0.5 touch-pan-y"
            data-testid="growth-stages-timeline"
            onPointerDown={ handleRailPointerDown }
            onPointerUp={ handleRailPointerUp }
          >
            <div
              className="relative grid w-full px-1 pt-1.5"
              style={ { gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` } }
            >
              <div className="absolute left-3 right-3 top-2.75 h-0.5 bg-border/80" />
            { stages.map((stage) => (
                <button
                  key={ stage.id ?? `${stage.seq}-${stage.name}` }
                  type="button"
                  aria-label={`Select ${stage.name}`}
                  aria-pressed={ selectedSeq === stage.seq }
                  title={ stage.startDate ? `${stage.name} · ${stage.startDate}` : stage.name }
                  onClick={ () => setSelectedSeq(stage.seq) }
                  className="relative z-10 flex min-w-13 flex-1 cursor-pointer flex-col items-center gap-1 text-center"
                >
                  <span
                    className={ cn(
                      'pointer-events-none size-3.5 rounded-full border-2 transition-colors',
                      displayedSeq === stage.seq
                        ? 'border-primary bg-background ring-2 ring-primary/30'
                        : stage.startDate
                          ? 'border-primary bg-primary'
                          : 'border-border bg-background',
                    ) }
                  />
                </button>
            )) }
            </div>
          </div>
          { selectedStage ? (
            <div className="mt-2 flex items-center justify-center gap-2 rounded-md border border-border/70 bg-muted/35 px-2 py-2.5" data-testid="growth-stage-selected-info">
              <button
                type="button"
                aria-label="Previous growth stage"
                disabled={ selectedIndex <= 0 }
                onClick={ () => moveSelectedStage(-1) }
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronLeft className="size-4" />
              </button>
              <div className="min-w-0 flex-1 text-center">
                <div className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground" data-testid="growth-stage-selected-crop">
                  { selectedStage.cropId === cycle?.cropType ? (cycle.cropName ?? 'Selected crop') : 'Selected crop' }
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Start date:{ ' ' }
                  { selectedStage.startDate ? (
                    <span className="font-medium text-primary">{ formatStartDate(selectedStage.startDate) }</span>
                  ) : (
                    <Dialog.Trigger asChild>
                      <button type="button" onClick={ () => openEditor(selectedStage.seq) } className="font-medium text-primary hover:underline">+ Add</button>
                    </Dialog.Trigger>
                  ) }
                </div>
                <div className="mt-0.5 truncate text-sm font-semibold text-foreground" title={ selectedStage.name }>
                  { selectedStage.name }
                </div>
              </div>
              <button
                type="button"
                aria-label="Next growth stage"
                disabled={ selectedIndex < 0 || selectedIndex >= stages.length - 1 }
                onClick={ () => moveSelectedStage(1) }
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
          ) : (
            <Dialog.Trigger asChild>
              <button type="button" onClick={ () => openEditor() } className="mt-2 w-full rounded-md border border-dashed border-border/70 bg-background/50 px-3 py-2 text-center text-xs leading-4 text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary">
                No start date for the growth stage
                <span className="ml-1 text-primary">+ Add</span>
              </button>
            </Dialog.Trigger>
          ) }
        </>
      ) }

        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-modal bg-background/70 backdrop-blur-sm" />
          <Dialog.Content
            aria-label="Edit growth stages"
            className="fixed left-1/2 top-1/2 z-modal flex max-h-[82vh] w-[min(35.5rem,calc(100vw-1rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border bg-popover text-popover-foreground shadow-e3"
          >
            <div className="relative border-b border-border/70 px-5 pb-3 pt-4 text-center sm:px-8">
              <Dialog.Title className="font-display text-lg font-semibold text-popover-foreground">Edit growth stages</Dialog.Title>
              <Dialog.Description className="mx-auto mt-2 max-w-md text-xs leading-5 text-muted-foreground">
                Set the start date for each stage. Changes apply only to this vegetation cycle.
              </Dialog.Description>
              <Dialog.Close asChild>
                <button type="button" aria-label="Close" className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground">
                  <X className="size-5" />
                </button>
              </Dialog.Close>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 sm:px-6">
              <div className="relative space-y-1.5 pl-11">
                <div className="absolute bottom-4 left-4.75 top-4 w-0.5 bg-border/80" />
                { [...draftStages].sort((a, b) => b.seq - a.seq).map((stage) => {
                  const isActive = activeSeq === stage.seq;
                  const previousStage = draftStages
                    .filter((item) => item.seq < stage.seq && item.startDate)
                    .sort((left, right) => right.seq - left.seq)[0] ?? null;
                  const nextStage = draftStages
                    .filter((item) => item.seq > stage.seq && item.startDate)
                    .sort((left, right) => left.seq - right.seq)[0] ?? null;
                  return (
                    <div key={ stage.id ?? `${stage.seq}-${stage.name}` } className={ cn(
                      'relative rounded-lg border bg-muted px-3 py-2.5 text-card-foreground shadow-e1',
                      stage.startDate ? 'border-primary/50' : 'border-border',
                    ) }>
                      <span className={ cn(
                        'absolute -left-9.75 top-3 flex size-7 items-center justify-center rounded-full border text-xs font-semibold',
                        stage.startDate
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-muted text-foreground',
                      ) }>
                        { stage.seq }
                      </span>
                      <div className="flex items-start gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium leading-5 text-card-foreground">{ stage.name }</p>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            Duration: { stage.duration ?? 'Not specified'}
                          </p>
                          { stage.startDate && !isActive && (
                            <p className="mt-1 text-[11px] font-medium text-primary">
                              Start date: { formatStartDate(stage.startDate) }
                            </p>
                          ) }
                          { isActive && (
                            <DatePicker
                              value={ stage.startDate ?? '' }
                              onChange={ (value) => setDraftStages((current) => current.map((item) => item.seq === stage.seq ? { ...item, startDate: value || null } : item)) }
                              placeholder="Select start date"
                              minDate={ previousStage?.startDate ? shiftDate(previousStage.startDate, 1) : undefined }
                              maxDate={ nextStage?.startDate ? shiftDate(nextStage.startDate, -1) : undefined }
                              className="mt-2"
                            />
                          ) }
                        </div>
                        <button type="button" aria-label={`Edit ${stage.name} start date`} onClick={ () => setActiveSeq(isActive ? null : stage.seq) } className={ cn('shrink-0 rounded-md p-1.5 transition-colors', isActive ? 'bg-primary/15 text-primary' : 'text-primary/80 hover:bg-primary/10 hover:text-primary') }>
                          <Pencil className="size-4" />
                        </button>
                      </div>
                      { isActive && (
                        <div className="mt-1.5 flex items-center justify-end gap-2 border-t border-border/70 pt-1.5">
                          <button type="button" onClick={ () => cancelStageDate(stage.seq) } className="rounded-md px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground">
                            Cancel
                          </button>
                          <Button type="button" size="sm" disabled={ updateStages.isPending || (!stage.startDate && !stages.find((item) => item.seq === stage.seq)?.startDate) } onClick={ () => applyStageDate(stage.seq) } className="h-7 px-3 text-[11px] uppercase tracking-wide">
                            { updateStages.isPending ? 'Saving...' : 'Apply' }
                          </Button>
                        </div>
                      ) }
                      { isActive && updateStages.isError && <p className="mt-2 text-xs text-destructive">Unable to save this stage date.</p> }
                    </div>
                  );
                }) }
              </div>
            </div>

            <div className="flex justify-end border-t border-border/70 px-4 py-2 sm:px-6">
              <Dialog.Close asChild>
                <button type="button" onClick={ closeEditor } className="rounded-md px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground">Close</button>
              </Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </div>
    </Dialog.Root>
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
  sarSupport?: SarSupport | null;
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
  sarSupport,
}: ChartTabProps) {
  const maskMethod = sourceMaskMethod ?? null;
  const maskMetricLabel = sourceMetricsProvisional ? 'Masked' : 'Cloud / masked';

  return (
    <div className="space-y-2 pt-0.5">
      <div className="flex flex-wrap gap-1.5" aria-label="Analytics index">
        { indices.map((index) => (
          <Button
            key={ index }
            type="button"
            size="sm"
            variant={ index === activeIndex ? 'primary' : 'ghost' }
            className="h-6 px-1.5 text-[11px]"
            onClick={ () => onSelectIndex(index) }
            data-testid={ `analytics-index-${index}` }
          >
            { indexLabel(index) }
          </Button>
        )) }
      </div>

      <div
        className="rounded-md border border-border/80 bg-background/50 p-2.5"
        data-testid="analytics-statistics-summary"
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
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

        { sarSupport?.cloudGap && (
          <div
            className="mb-2 flex items-start gap-1.5 rounded-md border border-info/30 bg-info/10 px-2 py-1.5 text-[11px] leading-4 text-info"
            data-testid="analytics-sar-support"
          >
            <Info className="mt-0.5 size-3 shrink-0" strokeWidth={ 1.75 } />
            <span>
              { sarSupport.available
                ? `EOS-04 SAR support available (${sarSupport.confidence} confidence${sarSupport.daysFromOpticalDate != null ? `, ${Math.abs(sarSupport.daysFromOpticalDate)} day offset` : ''}).`
                : `EOS-04 SAR support unavailable: ${sarSupport.reason ?? sarSupport.status}.` }
            </span>
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
            <div className="mt-1.5 grid grid-cols-3 gap-1.5">
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
          <p data-testid="analytics-ndmi-note" className="text-warning">
            { provenanceNote ?? 'Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band.' }
          </p>
        ) }
        { warnings.map((warning) => (
          <p key={ warning } className="text-warning">{ warning }</p>
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
      className="rounded-md border border-primary/20 bg-primary/5 p-3 shadow-e1"
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
        <p key={ warning } className="mt-1 text-[11px] leading-4 text-warning" data-testid="analytics-pipeline-warning">
          { warning }
        </p>
      )) }
    </div>
  );
}

function ActivitiesTab() {
  return (
    <div className="space-y-2 pt-0.5" data-testid="activities-tab">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-foreground">Activities</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-6 px-1.5 text-[11px]"
          data-testid="activities-add-trigger"
          disabled
        >
          <Plus className="size-3" strokeWidth={ 1.75 } /> Add
        </Button>
      </div>
      <div
        className="flex flex-col items-center gap-1.5 rounded-md border border-dashed border-border/80 p-3 text-center"
        data-testid="activities-empty-state"
      >
        <p className="text-xs text-muted-foreground">No activities added to this field.</p>
        <Button
          type="button"
          size="sm"
          variant="primary"
          className="h-7 px-2.5 text-xs"
          data-testid="activities-add-button"
          disabled
        >
          <Plus className="size-3" strokeWidth={ 1.75 } /> Add activity
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
