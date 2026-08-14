// Typed payloads for the same-origin Akasha BFF (`/api/*`).
// These mirror the contracts in docs/prompts/phase-4-frontend-map-layer-ux-emergent-prompt.md.

export interface AoiConfig {
  id: string;
  name: string;
  /** [lng, lat] */
  center: [number, number];
  zoom: number;
  /** [west, south, east, north] */
  bounds: [number, number, number, number];
}

export type BasemapProvider = 'esri' | 'osm' | 'empty';
export type BasemapUsageModel = 'session' | 'tile';
export type BasemapPlacesPreference = 'all' | 'attributed' | 'none';

export interface BasemapConfig {
  provider: BasemapProvider;
  style: string;
  styleFamily: string;
  usageModel: BasemapUsageModel;
  places: BasemapPlacesPreference;
  sessionDurationSeconds: number;
}

export interface AppConfig {
  appName: string;
  aoi: AoiConfig;
  aois?: AoiConfig[];
  /** Backward-compatible field. Esri basemaps are configured through `basemap`. */
  basemapStyleUrl: string;
  basemap: BasemapConfig;
  maxPolygonAreaHa: number;
  maxPolygonVertices: number;
  usablePixelThresholdPercent: number;
  supportedIndices: string[];
  defaultIndex: string;
  defaultSourceId?: string;
  adminIngestionLiveTriggerEnabled: boolean;
  features?: {
    cropMapSplitEnabled: boolean;
    cropMapContrastEnabled: boolean;
    latestImageryEnabled: boolean;
    fieldDiscoveryEnabled?: boolean;
  };
  latestImagery?: LatestImageryPolicy;
}

export type RenderProfileName = 'standard' | 'contrast';

export interface LatestImageryPolicy {
  policyVersion: string;
  sourceId: 'sentinel-2-l2a';
  processingLevel: 'L2A';
  lookbackDays: number;
  maxCloudPercent: number;
  maxViewportDiagonalMeters: number;
  resultLimit: number;
  entitled: boolean;
}

export interface SceneCandidate {
  sceneId: string;
  acquisitionDate: string;
  acquisitionDatetime: string;
  sourceId: string;
  sensor: string;
  processingLevel: string;
  cloudPercent: number;
  coveragePercent: number;
  coverageStatus: 'full' | 'partial';
  usable: boolean;
  bounds: [number, number, number, number];
  unavailableReason?: string | null;
  tileUrlTemplate: string;
  thumbnailUrl: string;
}

export interface LatestImageryResult {
  policyVersion: string;
  searchedAt: string;
  viewportDiagonalMeters: number;
  candidates: SceneCandidate[];
}

export interface IndexRenderProfile {
  sourceId: string;
  sceneId: string;
  indexType: string;
  requestedProfile: RenderProfileName;
  appliedProfile: RenderProfileName;
  profileVersion: string;
  thresholds: number[];
  palette: string[];
  legendLabels: string[];
  fallbackReason?: string | null;
  overlayUrl: string;
  precision: number;
  maskedLabel: string;
  statisticsVersion: string;
  maskProvenance: CloudMaskOptions;
  formulaVersion: string;
  geometryReference: string;
}

export interface ViewerSelection {
  sourceId: string;
  acquisitionDate: string;
  indexType: string;
  cloudMask: CloudMaskOptions;
  renderProfile: RenderProfileName;
  preferHighRes: boolean;
}

export interface RasterSample {
  status: 'ok' | 'error';
  value: number | null;
  category: number | null;
  masked: boolean;
  maskClass: number | null;
  error?: string | null;
}

export interface ComparisonSampleResponse {
  left: RasterSample;
  right: RasterSample;
}

export interface IrrigationType {
  id: number;
  name: string;
  description: string | null;
}

export interface TillageType {
  id: number;
  name: string;
  description: string | null;
}

export interface Crop {
  id: number;
  name: string;
  seedingTypeId: number | null;
  color: string | null;
  maturityOptions: string[] | null;
  hasWeatherRisk: boolean;
  hasVariety: boolean;
  bbchMode: string | null;
  characteristic: string | null;
  stages?: CropGrowthStage[];
}

export interface CropGrowthStage {
  id: number;
  cropId: number;
  seq: number;
  name: string;
  duration: string | null;
}

export interface CropVariety {
  id: number;
  cropId: number;
  name: string;
  maturityOptions: string[] | null;
}

export interface PaginatedVarieties {
  items: CropVariety[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

export interface PredefinedSeason {
  id: number;
  seasonName: string;
  periodStartDate: string | null;
  periodEndDate: string | null;
  sowingStartDate: string | null;
  sowingEndDate: string | null;
  harvestingStartDate: string | null;
  harvestingEndDate: string | null;
  mainWaterSource: string | null;
}

export type SourceKind = 'optical' | 'sar' | 'context' | 'archive';
export type SourceAnalysisLevel = 'field' | 'regional' | 'context' | 'archive';
export type SourceAvailabilityStatus = 'active' | 'gated';
export type SourceProductRole = 'primary' | 'support' | 'advanced';

/** EOS-style grouped LAYER picker: a labelled category of display modes. */
export interface LayerGroup {
  label: string;
  modes: string[];
}

export interface Source {
  id: string;
  label: string;
  provider: string;
  kind?: SourceKind;
  productRole?: SourceProductRole;
  displayModes?: string[];
  defaultDisplayMode?: string;
  mapDisplayModes?: string[];
  defaultMapDisplayMode?: string;
  displayMode?: string;
  /** Optional category grouping for the LAYER picker; null/absent ⇒ flat list. */
  layerGroups?: LayerGroup[] | null;
  description?: string;
  attribution?: string;
  supportedIndices?: string[];
  maskMethod?: string | null;
  availableMaskOptions?: Array<keyof CloudMaskOptions>;
  limitations?: string[];
  metricsProvisional?: boolean;
  resolutionMeters?: number | null;
  revisitDays?: number | null;
  analysisLevel?: SourceAnalysisLevel;
  availabilityStatus?: SourceAvailabilityStatus;
  gatedReason?: string | null;
  /** True when this source is served by the ingestion pipeline (XYZ index tiles + field stats). */
  pipelineBacked?: boolean;
}

export interface MonitoringFailure {
  productId?: string | null;
  sourceId?: string | null;
  sceneKey?: string | null;
  status?: string | null;
  retries: number;
  bytes: number;
  updatedAt?: string | null;
  failureKind: string;
  error?: string | null;
}

export interface MonitoringLedgerSource {
  sourceId: string;
  statusCounts: Record<string, number>;
  bytes: number;
  lastUpdatedAt?: string | null;
  failureCountsByKind: Record<string, number>;
  lastFailure?: MonitoringFailure | null;
  latestSuccessfulCompositeDate?: string | null;
  latestSuccessfulCompositeProductId?: string | null;
  latestSuccessfulCompositeAoiId?: string | null;
  latestSuccessfulCompositeUpdatedAt?: string | null;
  latestSuccessfulComposites?: Array<{
    aoiId?: string | null;
    date?: string | null;
    productId?: string | null;
    updatedAt?: string | null;
  }>;
  latestSuccessfulSearchAoiId?: string | null;
  latestSuccessfulSearchDatetimeRange?: string | null;
  latestSuccessfulSearchUpdatedAt?: string | null;
}

export interface IngestionLedgerSummary {
  status: string;
  path?: string | null;
  rowCount?: number | null;
  statusCounts: Record<string, number>;
  bytes?: number | null;
  lastUpdatedAt?: string | null;
  failureCountsByKind: Record<string, number>;
  lastFailures: MonitoringFailure[];
  bySource: MonitoringLedgerSource[];
  lastError?: string | null;
}

export interface StoragePrefixUsage {
  prefix: string;
  objectCount: number;
  bytes: number;
  zeroByteObjectCount?: number;
}

export interface StorageUsage {
  status: string;
  bucket?: string | null;
  objectCount?: number | null;
  bytes?: number | null;
  zeroByteObjectCount?: number | null;
  byPrefix: StoragePrefixUsage[];
  lastError?: string | null;
}

export interface ImagerySourceMonitoringSource {
  sourceId: string;
  status: 'ok' | 'warning' | 'error';
  statusReasons: string[];
  label?: string | null;
  provider?: string | null;
  kind?: SourceKind | string | null;
  availabilityStatus?: SourceAvailabilityStatus | string | null;
  analysisLevel?: SourceAnalysisLevel | string | null;
  refreshPolicy?: string | null;
  latestAvailableDate?: string | null;
  latestUsableDate?: string | null;
  daysSinceLatestAvailable?: number | null;
  staleAfterDays: number;
  isStale: boolean;
  dateCount: number;
  tileAvailableDateCount: number;
  coveragePercent?: number | null;
  usablePixelPercent?: number | null;
  cloudMaskedPercent?: number | null;
  metricsProvisional: boolean;
  gatedReason?: string | null;
  warnings: string[];
  tileUnavailableReasons?: string[];
  lastError?: string | null;
  latestSuccessfulCompositeDate?: string | null;
  latestSuccessfulCompositeProductId?: string | null;
  latestSuccessfulCompositeAoiId?: string | null;
  latestSuccessfulCompositeUpdatedAt?: string | null;
  latestSuccessfulComposites?: Array<{
    aoiId?: string | null;
    date?: string | null;
    productId?: string | null;
    updatedAt?: string | null;
  }>;
  daysSinceLatestSuccessfulComposite?: number | null;
  isSuccessfulCompositeStale: boolean;
  latestSuccessfulSearchAoiId?: string | null;
  latestSuccessfulSearchDatetimeRange?: string | null;
  latestSuccessfulSearchUpdatedAt?: string | null;
  daysSinceLatestSuccessfulSearch?: number | null;
  isSuccessfulSearchStale: boolean;
  isUpstreamDataStale: boolean;
  ingestionFailureCountsByKind: Record<string, number>;
  lastIngestionFailure?: MonitoringFailure | null;
  hasUnresolvedIngestionFailure: boolean;
  /** Latest scheduler job ID for this source (Phase 9 scheduler fields). */
  latestSchedulerJobId?: string | null;
  latestSchedulerJobState?: string | null;
  latestSchedulerJobUpdatedAt?: string | null;
}

export interface ImagerySourceMonitoringResponse {
  generatedAt: string;
  status: 'ok' | 'warning' | 'error';
  statusReasons: string[];
  staleAfterDays: number;
  coverageThresholdPercent: number;
  usablePixelThresholdPercent: number;
  sources: ImagerySourceMonitoringSource[];
  storage: StorageUsage;
  ingestionLedger: IngestionLedgerSummary;
}

// ---------------------------------------------------------------------------
// Ingestion scheduler monitoring — Phase 9 BFF endpoints
// ---------------------------------------------------------------------------

export interface IngestionScheduleItem {
  sourceId: string;
  provider?: string | null;
  adapter?: string | null;
  aoiId?: string | null;
  lifecycleState?: string | null;
  scheduleState?: string | null;
  capabilities: string[];
  commercialState?: string | null;
  aoiScope?: string | null;
  validationState?: string | null;
  scheduleEnabled: boolean;
  productExposure?: string | null;
  lastRunAt?: string | null;
  lastSuccessAt?: string | null;
  lastFailureAt?: string | null;
  nextDueAt?: string | null;
  nextWindowStart?: string | null;
  nextWindowEnd?: string | null;
  cadenceDays?: number | null;
  dueReason?: string | null;
  isDue?: boolean;
  isOverdue?: boolean;
}

export interface IngestionScheduleResponse {
  status: string;
  generatedAt: string;
  schedules: IngestionScheduleItem[];
  lastError?: string | null;
}

export interface IngestionSourceLastJob {
  jobId: string;
  state: string;
  runAt?: string | null;
  foundCount?: number | null;
  selectedCount?: number | null;
  downloadedCount?: number | null;
  rejectedCount?: number | null;
  windowStart?: string | null;
  windowEnd?: string | null;
  failureKind?: string | null;
  message?: string | null;
}

export interface IngestionSourceSummary {
  sourceId: string;
  label: string;
  provider?: string | null;
  kind?: string | null;
  active: boolean;
  adminManageable?: boolean;
  syncEnabled?: boolean;
  productExposure?: string | null;
  availabilityStatus?: SourceAvailabilityStatus | string | null;
  scheduleState?: string | null;
  scheduleEnabled?: boolean;
  validationState?: string | null;
  capabilities?: string[];
  gatedReason?: string | null;
  aoiId?: string | null;
  cadenceDays?: number | null;
  lastRunAt?: string | null;
  lastSuccessAt?: string | null;
  lastFailureAt?: string | null;
  nextDueAt?: string | null;
  isDue?: boolean;
  isOverdue?: boolean;
  latestCompositeDate?: string | null;
  lastJob?: IngestionSourceLastJob | null;
}

export interface IngestionSourcesResponse {
  status: string;
  generatedAt: string;
  sources: IngestionSourceSummary[];
  liveTriggerEnabled: boolean;
  lastError?: string | null;
}

export interface IngestionProductItem {
  productId: string;
  sceneKey?: string | null;
  acquisitionDate?: string | null;
  status: string;
  bytes: number;
  updatedAt?: string | null;
  error?: string | null;
}

export interface IngestionSourceProductsResponse {
  status: string;
  generatedAt: string;
  sourceId: string;
  products: IngestionProductItem[];
  lastError?: string | null;
}

export interface TriggerIngestionJobRequest {
  sourceId: string;
  aoiId?: string;
  windowDays?: number;
  windowStart?: string | null;
  windowEnd?: string | null;
  dryRun?: boolean;
  confirmLive?: boolean;
  limit?: number;
  maxDownloads?: number;
  minCoveragePercent?: number;
  notes?: string;
}

export interface TriggerIngestionJobResponse {
  status: 'submitted' | 'rejected' | 'unavailable';
  jobRequestId: string | null;
  dryRun: boolean;
  jobsUrl: string;
  message: string;
}

export interface IngestionJobSummary {
  jobId: string;
  sourceId: string;
  provider?: string | null;
  aoiId?: string | null;
  state: string;
  windowStart?: string | null;
  windowEnd?: string | null;
  foundCount?: number | null;
  selectedCount?: number | null;
  downloadedCount?: number | null;
  rejectedCount?: number | null;
  failureKind?: string | null;
  message?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  updatedAt?: string | null;
}

export interface IngestionJobListResponse {
  status: string;
  generatedAt: string;
  jobs: IngestionJobSummary[];
  nextCursor?: string | null;
  lastError?: string | null;
}

export interface IngestionJobDetail {
  jobId: string;
  sourceId: string;
  provider?: string | null;
  aoiId?: string | null;
  state: string;
  request: Record<string, unknown>;
  providerInputSummary: Record<string, unknown>;
  providerResponseSummary: Record<string, unknown>;
  searchManifestHandle?: string | null;
  downloadManifestHandle?: string | null;
  prepareManifestHandles: string[];
  verificationSummary: Record<string, unknown>;
  scheduleDecision?: string | null;
  nextDueAt?: string | null;
  windowStart?: string | null;
  windowEnd?: string | null;
  foundCount?: number | null;
  selectedCount?: number | null;
  downloadedCount?: number | null;
  rejectedCount?: number | null;
  failureKind?: string | null;
  message?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  updatedAt?: string | null;
  validationProblems: string[];
  rejectionReasons: string[];
  artifactHandles: Record<string, string>;
  ledgerRows: Record<string, unknown>[];
}

export type PipelineStageId =
  | 'planned'
  | 'approved_runtime'
  | 'lock'
  | 'search'
  | 'select'
  | 'download'
  | 'prepare'
  | 'composite'
  | 'verify'
  | 'upload'
  | 'stac'
  | 'ledger';

export type PipelineStageState =
  | 'not_reached'
  | 'inferred'
  | 'unavailable'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'validation_failed';

export interface IngestionJobEvent {
  timestamp: string;
  eventType: string;
  stage: PipelineStageId | 'running' | 'terminal' | 'unknown';
  status:
  | PipelineStageState
  | 'planned'
  | 'queued'
  | 'blocked_by_lock'
  | 'cancelled'
  | 'skipped_not_due'
  | 'skipped_gated'
  | 'unknown';
  message: string;
  payload: Record<string, unknown>;
}

export interface IngestionJobEventsResponse {
  status: string;
  generatedAt: string;
  jobId: string;
  events: IngestionJobEvent[];
  truncated: boolean;
  scannedCount: number;
  totalEventsScanned: number;
  totalValidEvents: number;
  malformedEventsSkipped?: number;
  returnedCount?: number;
  eventLimit?: number;
  lastError?: string | null;
}

export interface IngestionJobFilters {
  limit?: number;
  cursor?: string;
  sourceId?: string;
  aoiId?: string;
  state?: string;
  startedAfter?: string;
  startedBefore?: string;
}

export interface SceneDate {
  /** YYYY-MM-DD */
  acquisitionDate: string;
  datetime: string;
  usablePixelPercent: number | null;
  cloudMaskedPercent: number | null;
  coveragePercent: number | null;
  shadowPercent?: number | null;
  obscuredPercent?: number | null;
  /** Combined cloud + shadow/obscured share when supplied by the BFF. */
  combinedCloudShadowPercent?: number | null;
  /** Effective combined cloud + cirrus + shadow limit used for this acquisition. */
  appliedCloudThresholdPercent?: number | null;
  /** Legacy alias accepted only when normalizing older BFF responses. */
  appliedThresholdPercent?: number | null;
  /** Availability state from the catalog/field-date evaluator. */
  availabilityStatus?: string | null;
  /** Explicit selection state; absent on older BFF responses. */
  selectable?: boolean;
  isLatestUsable: boolean;
  metricsProvisional: boolean;
  tileAvailable: boolean;
  unavailableReason?: string | null;
  sceneCount?: number;
  /** [west, south, east, north] */
  bounds?: [number, number, number, number];
  /** Short sensor badge for the chip (e.g. `S2`, `S1`). */
  sensor?: string | null;
  /** Best-mode provenance label for the chip (e.g. `LISS-4 · 5.8 m`). */
  provenanceLabel?: string | null;
  /** Best-mode resolved source ID (which source this candidate came from). */
  resolvedSourceId?: string | null;
}

// ---------------------------------------------------------------------------
// Best-observation resolver (Phase 11 / TASK-066–071)
// ---------------------------------------------------------------------------

/** A ranked cross-source observation candidate from GET /api/observations/best. */
export interface ObservationCandidate {
  sourceId: string;
  /** YYYY-MM-DD */
  acquisitionDate: string;
  resolutionMeters: number | null;
  analysisLevel: string | null;
  usablePixelPercent: number | null;
  coveragePercent: number | null;
  cloudMaskedPercent: number | null;
  tileAvailable: boolean;
  isLatestUsable: boolean;
  /** Weighted [0, 100] score; higher is better. */
  score: number;
  sourcePriority: number;
  provenanceNote: string | null;
  /** True when the source is regional/coarse (e.g. AWiFS 56 m). */
  isCoarse: boolean;
  supportedIndices: string[];
  /** Human-readable source label from the source registry. */
  label: string;
}

export interface BestObservationsResponse {
  candidates: ObservationCandidate[];
  query: {
    targetDate: string | null;
    startDate: string | null;
    endDate: string | null;
    lookbackDays: number | null;
    indexType: string | null;
    useCase: string;
    allowCoarse: boolean;
    windowDays: number;
    maxCandidates: number;
  };
}

export interface BestObservationsParams {
  targetDate?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  lookbackDays?: number | null;
  indexType?: string | null;
  useCase?: 'field' | 'regional';
  allowCoarse?: boolean;
  windowDays?: number;
  maxCandidates?: number;
}

export interface DefaultLayer {
  sourceId: string;
  acquisitionDate: string | null;
  revisitDays?: number | null;
  nextExpectedAcquisitionDate?: string | null;
  displayMode?: string;
  kind?: SourceKind;
  displayModes?: string[];
  defaultDisplayMode?: string;
  mapDisplayModes?: string[];
  defaultMapDisplayMode?: string;
  description?: string;
  supportedIndices?: string[];
  /** Same-origin `/api/tiles/.../{z}/{x}/{y}.png` template — never a COG/MinIO/TiTiler URL. */
  tileUrlTemplate: string | null;
  /** [west, south, east, north] */
  bounds?: [number, number, number, number] | null;
  sceneCount?: number;
  minzoom: number;
  maxzoom: number;
  attribution: string;
  usablePixelPercent: number | null;
  cloudMaskedPercent: number | null;
  coveragePercent: number | null;
  metricsProvisional: boolean;
  tileAvailable: boolean;
  selectable?: boolean;
  availabilityStatus?: string | null;
  appliedCloudThresholdPercent?: number | null;
  appliedThresholdPercent?: number | null;
  unavailableReason?: string | null;
}

export type PlotStatus = 'planned' | 'active' | 'inactive' | 'archived';

export interface CloudMaskOptions {
  clouds: boolean;
  cloudShadows: boolean;
  cirrus: boolean;
}

export interface CloudMaskMapping {
  nativeExcludedMaskClasses: number[];
  warnings: string[];
}

export type GeoJsonPosition = [number, number] | [number, number, number];

export interface GeoJsonPolygonGeometry {
  type: 'Polygon';
  coordinates: GeoJsonPosition[][];
}

export interface GeoJsonMultiPolygonGeometry {
  type: 'MultiPolygon';
  coordinates: GeoJsonPosition[][][];
}

export type PlotGeometry = GeoJsonPolygonGeometry | GeoJsonMultiPolygonGeometry;

export interface Plot {
  id: string;
  name: string;
  geometry: PlotGeometry;
  areaHa: number | null;
  createdAt: string | null;
  updatedAt: string | null;
  groupName?: string | null;
  cropType?: string | null;
  variety?: string | null;
  seasonLabel?: string | null;
  sowingDate?: string | null;
  plantingDate?: string | null;
  status?: PlotStatus | null;
}

export interface PlotCreatePayload {
  name: string;
  geometry: PlotGeometry;
  groupName?: string | null;
  cropType?: string | null;
  variety?: string | null;
  seasonLabel?: string | null;
  sowingDate?: string | null;
  plantingDate?: string | null;
  status?: PlotStatus | null;
}

export interface PlotUpdatePayload {
  name?: string;
  geometry?: PlotGeometry;
  groupName?: string | null;
  cropType?: string | null;
  variety?: string | null;
  seasonLabel?: string | null;
  sowingDate?: string | null;
  plantingDate?: string | null;
  status?: PlotStatus | null;
}

export interface RejectedFeature {
  index: number;
  code: string;
  message: string;
}

export interface PlotImportResponse {
  imported: Plot[];
  rejected: RejectedFeature[];
  importedCount: number;
  rejectedCount: number;
}

export interface IndexStatistics {
  min: number | null;
  max: number | null;
  mean: number | null;
  stddev: number | null;
  validPixelPercent: number;
  cloudMaskedPercent: number;
  coveragePercent: number;
}

export interface PixelCounts {
  totalPixels: number;
  nodataPixels: number;
  coveragePixels: number;
  maskedPixels: number;
  validPixels: number;
}

export interface PipelineSelectionMetadata {
  windowDays?: number | null;
  rule?: string | null;
  validPixelCount?: number | null;
  [key: string]: unknown;
}

export interface PipelineResolutionMetadata {
  nativeMeters?: number | null;
  processingMeters?: number | null;
  displayMeters?: number | null;
  [key: string]: unknown;
}

export interface PipelineQualityMetadata {
  status?: string | null;
  reason?: string | null;
  warnings?: string[];
  [key: string]: unknown;
}

export interface PipelineFreshnessMetadata {
  status?: string | null;
  stale?: boolean | null;
  aoiId?: string | null;
  latestProcessedSceneDate?: string | null;
  staleAfter?: string | null;
  reason?: string | null;
  warnings?: string[];
  [key: string]: unknown;
}

export interface PipelineClassStatistic {
  class?: string | null;
  valueRange?: [number, number] | number[] | null;
  areaSqM?: number | null;
  areaPercentage?: number | null;
  [key: string]: unknown;
}

export interface FieldStatisticsPipelineMetadata {
  enabled?: boolean;
  status?: string | null;
  source?: string | null;
  providerRoute?: string | null;
  requestedDate?: string | null;
  selectedSceneDate?: string | null;
  tileUrl?: string;
  statsUrl?: string;
  selection?: PipelineSelectionMetadata;
  resolution?: PipelineResolutionMetadata;
  quality?: PipelineQualityMetadata;
  freshness?: PipelineFreshnessMetadata;
  versions?: Record<string, unknown>;
  classStatistics?: PipelineClassStatistic[];
  pixelCountsBasis?: string | null;
  cloudMaskedPercentBasis?: string | null;
  coveragePercentBasis?: string | null;
  cloudMaskOptionsNote?: string | null;
  [key: string]: unknown;
}

export interface SarBandStatistics {
  name: string;
  min: number | null;
  max: number | null;
  mean: number | null;
  stddev: number | null;
  validPixelPercent: number;
}

export interface SarSupport {
  available: boolean;
  status: string;
  sourceId: string;
  acquisitionDate: string | null;
  daysFromOpticalDate: number | null;
  windowDays: number;
  cloudGap: boolean;
  opticalCloudMaskedPercent: number | null;
  opticalMaskedPixels: number | null;
  polarizations: string[];
  coveragePercent: number | null;
  confidence: 'none' | 'low' | 'medium' | 'high' | string;
  reason: string | null;
  bands: SarBandStatistics[];
  wetnessSignal: string;
  changeSignal: string;
}

export interface FieldStatisticsRequest {
  sourceId: string;
  acquisitionDate?: string | null;
  indexType: string;
  cloudMask?: CloudMaskOptions;
  preferHighRes?: boolean;
}

export interface NdviValueSplitCategory {
  id: 'denseVegetation' | 'moderateVegetation' | 'sparseVegetation' | 'openSoil' | 'cloudiness' | string;
  label: string;
  minInclusive: number | null;
  maxExclusive: number | null;
  pixelCount: number | null;
  areaSqM?: number | null;
  percentage: number;
}

export interface NdviValueSplit {
  indexType: 'NDVI';
  profileId: string;
  percentageBasis: 'classifiablePixels';
  thresholds: number[];
  totalPixels: number | null;
  classifiablePixels: number | null;
  noDataPixels: number | null;
  unclassifiedPixels: number | null;
  categories: NdviValueSplitCategory[];
}

export interface FieldMonitoringEvidence {
  fieldId: string;
  targetDate: string;
  optical: {
    status: 'usable' | 'quality_limited' | 'stale' | 'unavailable';
    sourceId: string;
    indexType: string;
    latestCandidateDate: string | null;
    latestQualifyingDate: string | null;
    ageDays: number | null;
    staleAfterDays: number;
    requirements: {
      minimumCoveragePercent: number;
      minimumUsablePixelPercent: number;
      maximumCombinedCloudShadowPercent: number;
    };
  };
  radar: {
    status: 'NOT_REQUESTED' | 'DISABLED' | 'AVAILABLE' | 'UNAVAILABLE';
    sourceId: string;
    triggered: boolean;
    triggerReason: string | null;
    reason?: string | null;
    reasonCode?: string | null;
    acquisitionDate?: string;
    daysFromTarget?: number;
    coveragePercent?: number;
    polarizations?: string[];
    displayedPolarization?: string;
    bands?: Array<{
      polarization: string;
      mean: number | null;
      median: number | null;
      stdDev: number | null;
      validPixelPercent: number;
      unit: 'dB';
    }>;
    features?: Record<string, number>;
    quality?: { qualified: boolean; confidence: 'none' | 'low' | 'medium' | 'high'; warnings: string[] };
    provenance?: Record<string, unknown>;
    overlayUrl?: string;
    selection?: {
      policyVersion: 'radar-support-selection-v1';
      evaluatedSourceIds: string[];
      qualifiedSourceIds: string[];
      selectedSourceId: string | null;
      rules?: string[];
    };
    comparison?: {
      status: 'AVAILABLE' | 'INSUFFICIENT_BASELINE' | 'DEGENERATE_BASELINE' | 'NO_COMPARABLE_HISTORY' | 'METADATA_INCOMPLETE';
      policyVersion?: string | null;
      currentKeyHash?: string | null;
      previousComparableDate?: string | null;
      comparableObservationCount: number;
      excludedObservationCount: number;
      exclusions?: Array<{ acquisitionDate: string; reasonCodes: string[] }>;
    };
    history?: Array<{
      acquisitionDate: string;
      coveragePercent: number;
      validPixelCount: number;
      fieldPixelCount: number;
      bands: Array<{
        polarization: string;
        median: number | null;
        mean: number | null;
        validPixelPercent: number;
        unit: 'dB';
      }>;
      features: Record<string, number>;
      comparableToCurrent: true;
    }>;
    change?: {
      status: 'AVAILABLE' | 'UNAVAILABLE';
      referenceDate?: string | null;
      bands: Array<{
        polarization: string;
        currentMedianDb: number;
        referenceMedianDb: number;
        medianDeltaDb: number;
      }>;
      features: Record<string, number>;
    };
    baseline?: {
      status: 'AVAILABLE' | 'INSUFFICIENT_OBSERVATIONS' | 'DEGENERATE_BASELINE';
      requiredPriorObservations: number;
      priorObservationCount: number;
      windowStart?: string | null;
      windowEnd?: string | null;
      bands: Array<{
        polarization: string;
        currentValue: number;
        baselineMedian: number;
        mad: number;
        robustDeviation: number | null;
      }>;
    };
  };
}

export interface FieldStatisticsResponse {
  plotId: string;
  provider: 'native' | 'pipeline';
  scope: 'field';
  indexType: string;
  sourceId: string;
  acquisitionDate: string;
  cloudMask: CloudMaskOptions;
  statistics: IndexStatistics;
  pixelCounts: PixelCounts;
  valueSplit?: NdviValueSplit | null;
  sarSupport?: SarSupport | null;
  maskedPixels?: number;
  maskMethod?: string | null;
  metricsProvisional?: boolean;
  /** Provenance from LISS-4 best-resolution resolver. */
  resolvedSourceId?: string | null;
  resolutionMeters?: number | null;
  enhanced?: boolean;
  basisDate?: string | null;
  provenanceNote?: string | null;
  metadata: {
    formula?: string;
    bands?: string[];
    maskMethod?: string;
    metricsProvisional?: boolean;
    nativeExcludedMaskClasses?: number[];
    cloudMaskOptions?: CloudMaskOptions;
    cloudMaskMapping?: CloudMaskMapping;
    reflectanceCorrection?: string;
    itemId?: string | null;
    areaHa?: number | null;
    vertices?: number | null;
    warnings?: string[];
    pipeline?: FieldStatisticsPipelineMetadata;
    [key: string]: unknown;
  };
}

export type ImageCorners = [[number, number], [number, number], [number, number], [number, number]];

export interface FieldIndexOverlayImage {
  url: string;
  sourceUrl: string;
  coordinates: ImageCorners;
  stretch: [number, number] | null;
  /** Provenance from LISS-4 best-resolution resolver. */
  resolvedSourceId?: string | null;
  resolutionMeters?: number | null;
  enhanced?: boolean;
  basisDate?: string | null;
  renderProfile?: RenderProfileName;
  renderProfileVersion?: string;
  renderThresholds?: number[];
  renderPalette?: string[];
  renderLegendLabels?: string[];
  renderFallbackReason?: string | null;
}

export interface FieldIndexPointResponse {
  plotId: string;
  sourceId: string;
  acquisitionDate: string;
  indexType: string;
  lng: number;
  lat: number;
  value: number | null;
  masked: boolean;
  maskClass: number | null;
  /** Provenance from LISS-4 best-resolution resolver. */
  resolvedSourceId?: string | null;
  resolutionMeters?: number | null;
  enhanced?: boolean;
  basisDate?: string | null;
  provenanceNote?: string | null;
}

export interface FieldTrendPoint {
  acquisitionDate: string;
  sceneId?: string | null;
  viewId?: string | null;
  mean: number | null;
  min?: number | null;
  max?: number | null;
  stddev?: number | null;
  validPixelPercent?: number | null;
  cloudMaskedPercent?: number | null;
  coveragePercent?: number | null;
  cloudPercent?: number | null;
  metricsProvisional?: boolean;
  unavailableReason?: string | null;
}

export interface FieldTrendResponse {
  plotId: string;
  provider: 'native' | 'pipeline';
  scope: 'native_fallback' | 'pipeline';
  sourceId: string;
  indexType: string;
  startDate: string;
  endDate: string;
  points: FieldTrendPoint[];
  fallbackReason?: string | null;
  metadata: {
    formula?: string;
    bands?: string[];
    cloudMaskOptions?: CloudMaskOptions;
    cloudMaskMapping?: CloudMaskMapping;
    requestStatus?: string;
    rangeLimitDays?: number;
    [key: string]: unknown;
  };
}

export type FieldIndexExportFormat = 'geotiff' | 'geojson' | 'csv' | 'shp';

export interface FieldIndexExportOptions {
  format: FieldIndexExportFormat;
  sourceId: string;
  acquisitionDate: string;
  indexType: string;
  cloudMask?: CloudMaskOptions;
}

export interface FieldReportExportOptions {
  sourceId: string;
  indexType: string;
  startDate?: string;
  endDate?: string;
  cloudMask?: CloudMaskOptions;
}

export interface FileDownload {
  blob: Blob;
  filename: string;
}

export type LeaderboardSortKey =
  | 'rank'
  | 'score'
  | 'latestIndexValue'
  | 'indexDelta'
  | 'cloudFreeRecencyDays'
  | 'areaHa'
  | 'name'
  | 'latestImageDate';

export interface FieldLeaderboardFilters {
  indexType?: string;
  groupName?: string;
  cropType?: string;
  variety?: string;
  seasonLabel?: string;
  search?: string;
  startDate?: string;
  endDate?: string;
  lookbackDays?: number;
  sortBy?: LeaderboardSortKey;
  sortOrder?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
  evaluationLimit?: number;
  sceneScanLimit?: number;
}

export interface LeaderboardScoreComponents {
  vigor?: number | null;
  trend?: number | null;
  recency?: number | null;
  weather?: number | null;
}

export interface FieldLeaderboardRow {
  plotId: string;
  rank?: number | null;
  name: string;
  field: string;
  groupName?: string | null;
  cropType?: string | null;
  variety?: string | null;
  seasonLabel?: string | null;
  location?: string | null;
  coordinates?: [number, number] | null;
  areaHa?: number | null;
  sowingDate?: string | null;
  plantingDate?: string | null;
  latestIndexValue?: number | null;
  latestImageDate?: string | null;
  indexDelta?: number | null;
  previousImageDate?: string | null;
  cloudFreeRecencyDays?: number | null;
  weatherRiskLabel: string;
  weatherRiskLevel: 'unknown';
  actualYield?: number | null;
  score?: number | null;
  scoreComponents: LeaderboardScoreComponents;
  dataAvailable: boolean;
  unavailableReason?: string | null;
  preview?: string | null;
  open?: string | null;
}

export interface FieldLeaderboardResponse {
  indexType: string;
  generatedAt: string;
  rows: FieldLeaderboardRow[];
  metadata: {
    rankingScope?: string;
    truncated?: boolean;
    totalFilteredFields?: number;
    evaluatedFieldCount?: number;
    evaluationLimit?: number;
    partialUnavailableCount?: number;
    weatherRiskAvailable?: boolean;
    weatherRiskSource?: string;
    [key: string]: unknown;
  };
}

export interface ReportTemplate {
  id: string;
  name: string;
  columns: string[];
  filters: Record<string, unknown>;
  sort: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ReportTemplatePayload {
  name: string;
  columns: string[];
  filters?: Record<string, unknown>;
  sort?: Record<string, unknown>;
}

export interface ReportTemplateUpdatePayload {
  name?: string;
  columns?: string[];
  filters?: Record<string, unknown>;
  sort?: Record<string, unknown>;
}

export interface Attachment {
  id: string;
  parentType?: string | null;
  parentId?: string | null;
  filename: string;
  contentType?: string | null;
  sizeBytes?: number | null;
  metadata: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export type FieldActivityStatus = 'planned' | 'in_progress' | 'done' | 'cancelled';

export interface FieldActivity {
  id: string;
  plotId?: string | null;
  fieldName?: string | null;
  groupName?: string | null;
  groupNames: string[];
  cropType?: string | null;
  variety?: string | null;
  seasonLabel?: string | null;
  activityType: string;
  activityDate: string;
  assignee?: string | null;
  status: FieldActivityStatus;
  inputProduct?: string | null;
  cost?: number | null;
  notes?: string | null;
  attachments: Attachment[];
  metadata: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface FieldActivityPayload {
  activityType: string;
  activityDate: string;
  plotId?: string | null;
  assignee?: string | null;
  status?: FieldActivityStatus;
  inputProduct?: string | null;
  cost?: number | null;
  notes?: string | null;
  attachmentIds?: string[];
}

export interface FieldActivityUpdatePayload {
  activityType?: string;
  activityDate?: string;
  plotId?: string | null;
  assignee?: string | null;
  status?: FieldActivityStatus;
  inputProduct?: string | null;
  cost?: number | null;
  notes?: string | null;
  attachmentIds?: string[];
}

export interface ActivityFilters {
  plotId?: string;
  groupName?: string;
  cropType?: string;
  variety?: string;
  activityType?: string;
  assignee?: string;
  year?: number;
  status?: FieldActivityStatus;
}

export interface ScoutTask {
  id: string;
  plotId?: string | null;
  fieldId?: string | null;
  fieldName?: string | null;
  fieldNameSnapshot?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  status: 'new' | 'closed';
  assignee?: string | null;
  priority: 'low' | 'medium' | 'high';
  notes?: string | null;
  attachments: Attachment[];
  metadata: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ScoutTaskPayload {
  plotId?: string | null;
  fieldId?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  status?: 'new' | 'closed';
  assignee?: string | null;
  priority?: 'low' | 'medium' | 'high';
  notes?: string | null;
  attachmentIds?: string[];
}

export interface ScoutTaskUpdatePayload {
  plotId?: string | null;
  fieldId?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  status?: 'new' | 'closed';
  assignee?: string | null;
  priority?: 'low' | 'medium' | 'high';
  notes?: string | null;
  attachmentIds?: string[];
}

export interface UploadedDataset {
  id: string;
  name: string;
  datasetType: 'geojson' | 'shp_zip' | 'iso_xml';
  uploadStatus: 'uploaded' | 'parsed' | 'failed';
  originalFilename?: string | null;
  contentType?: string | null;
  fileSizeBytes?: number | null;
  featureCount?: number | null;
  validationMessage?: string | null;
  metadata: Record<string, unknown>;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface FieldGroup {
  id: string;
  name: string;
  description?: string | null;
  color?: string | null;
  fieldIds: string[];
  plotIds: string[];
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface FieldGroupPayload {
  name?: string;
  description?: string | null;
  color?: string | null;
}

export interface ConnectionStatus {
  provider: string;
  status: 'not_connected';
  message: string;
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'unknown';

export interface RiskComponent {
  id: string;
  label: string;
  available: boolean;
  level: RiskLevel;
  score?: number | null;
  weight: number;
  usedInAggregate: boolean;
  evidence: string[];
  limitations: string[];
  source: string;
  flags?: {
    heat?: boolean | null;
    dryness?: boolean | null;
    excessRain?: boolean | null;
  } | null;
}

export interface CropStageSummary {
  cropType?: string | null;
  startDate?: string | null;
  startDateType: 'sowingDate' | 'plantingDate' | 'unknown';
  daysAfterStart?: number | null;
  stageLabel: string;
  modelVersion: string;
  limitations: string[];
}

export interface FieldRiskSummaryResponse {
  plotId: string;
  fieldWatchLevel: RiskLevel;
  vegetationStressContext: string;
  score?: number | null;
  components: RiskComponent[];
  cropStage: CropStageSummary;
  limitations: string[];
  metadata: Record<string, unknown>;
}

export interface AccountMe {
  user: {
    id: string;
    username?: string | null;
    email: string;
    displayName: string;
    onboardingCompleted: boolean;
  };
  currentTeam: { id: string; name: string; role: string };
  memberships: Array<{ teamId: string; teamName: string; role: string }>;
  authMode: string;
}

export interface AccountSettings {
  teamId?: string;
  safeLocalDev?: boolean;
  /** Maximum accepted optical cloud percentage for imagery dates. */
  opticalCloudThresholdPercent?: number | null;
  [key: string]: unknown;
}

export interface UpdateAccountSettingsPayload {
  opticalCloudThresholdPercent: number;
}

export interface SignupPayload {
  email: string;
  password: string;
  displayName: string;
}

export interface ApiKeyMetadata {
  id: string;
  name: string;
  prefix: string;
  last4: string;
  createdAt: string;
  revokedAt?: string | null;
  rawKey?: string | null;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  resourceType?: string | null;
  resourceId?: string | null;
  readAt?: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface AssistantStatus {
  status: 'disabled';
  message: string;
  evidenceSources: string[];
  limitations: string[];
}

export interface VegetationCycleCreate {
  seasonId: string;
  year: number;
  cropType: number;
  cropVariety?: number | null;
  sowingDate?: string | null;
  harvestingDate?: string | null;
  targetYield?: number | null;
  actualYield?: number | null;
  irrigationType?: number | null;
  tillageType?: number | null;
  maturity?: string | null;
  fertilizer?: string | null;
  hybrid?: string | null;
  ndviList?: string | null;
  notes?: string | null;
  isCutOff?: boolean | null;
}

export interface VegetationCycleResponse {
  id: string;
  fieldId: string;
  seasonId: string;
  seasonName?: string | null;
  year: number;
  cropType: number;
  cropName?: string | null;
  cropVariety?: number | null;
  varietyName?: string | null;
  sowingDate?: string | null;
  harvestingDate?: string | null;
  targetYield?: number | null;
  actualYield?: number | null;
  irrigationType?: number | null;
  irrigationTypeName?: string | null;
  tillageType?: number | null;
  tillageTypeName?: string | null;
  maturity?: string | null;
  fertilizer?: string | null;
  hybrid?: string | null;
  ndviList?: string | null;
  notes?: string | null;
  isCutOff?: boolean | null;
  growthStages?: VegetationCycleGrowthStage[];
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface VegetationCycleGrowthStage {
  id: string | null;
  cropId: number;
  seq: number;
  name: string;
  duration: string | null;
  startDate: string | null;
  saved: boolean;
}

export interface VegetationCycleGrowthStagesPayload {
  stages: Array<{
    seq: number;
    startDate: string | null;
  }>;
}

export interface FieldIdEntry {
  id: string;
  name: string;
  canRemove: boolean;
  isMapped: boolean;
}

export interface Season {
  id: string;
  userId: string;
  name: string;
  startDate: string | null;
  endDate: string | null;
  canDelete: boolean;
  totalArea: number;
  fieldIds: FieldIdEntry[];
  createdAt: string | null;
  updatedAt: string | null;
}

export interface SeasonCreatePayload {
  name: string;
  startDate?: string | null;
  endDate?: string | null;
  fieldIds?: string[];
}

export interface SeasonUpdatePayload {
  name?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  fieldIds?: string[];
}

export interface Field {
  id: string;
  userId: string;
  teamId?: string;
  name: string;
  areaHa: number | null;
  geometry: PlotGeometry;
  groupId: string | null;
  district?: string | null;
  country?: string | null;
  seasonIds: string[];
  vegetationData: VegetationCycleResponse[];
  createdAt: string | null;
  updatedAt: string | null;
}

export interface FieldCreatePayload {
  name: string;
  geometry: PlotGeometry;
  areaHa?: number | null;
  groupId?: string | null;
  district?: string | null;
  country?: string | null;
  seasonIds?: string[];
  vegetationData?: VegetationCycleCreate[];
}

export interface FieldUpdatePayload {
  name?: string | null;
  geometry?: PlotGeometry | null;
  areaHa?: number | null;
  groupId?: string | null;
  district?: string | null;
  country?: string | null;
  seasonIds?: string[] | null;
  vegetationData?: VegetationCycleCreate[] | null;
}

export type DiscoverySort =
  | 'name_asc'
  | 'name_desc'
  | 'newest'
  | 'oldest'
  | 'area_asc'
  | 'area_desc';

export interface DiscoveryFocusBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface DiscoveryOption<T extends string | number> {
  id: T;
  name: string;
}

export interface FieldDiscoveryFacets {
  crops: DiscoveryOption<number>[];
  groups: DiscoveryOption<string>[];
  hasUngrouped: boolean;
}

export interface DiscoveryFieldSummary {
  id: string;
  name: string;
  areaHa: number | null;
  crop: DiscoveryOption<number> | null;
  group: DiscoveryOption<string> | null;
  district: string | null;
  country: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  focusBounds: DiscoveryFocusBounds;
}

export interface DiscoveryTaskSummary {
  id: string;
  status: 'new' | 'closed';
  priority: 'low' | 'medium' | 'high';
  notes: string | null;
  assignee: string | null;
  longitude: number | null;
  latitude: number | null;
  field: DiscoveryFieldSummary | null;
  fieldNameSnapshot: string | null;
  findFieldAvailable: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface DiscoveryFilters {
  seasonId: string;
  q?: string;
  cropIds?: number[];
  groupIds?: string[];
  includeUngrouped?: boolean;
  sort?: DiscoverySort;
  page?: number;
  pageSize?: number;
  pinnedFieldIds?: string[];
  status?: 'new' | 'closed';
}

export interface AppliedDiscoveryFilters {
  seasonId: string;
  q: string;
  cropIds: number[];
  groupIds: string[];
  includeUngrouped: boolean;
  sort: DiscoverySort;
  status: 'new' | 'closed' | null;
}

export interface DiscoveryPage<T> {
  items: T[];
  pinnedItems: DiscoveryFieldSummary[];
  appliedFilters: AppliedDiscoveryFilters;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  resultBounds: DiscoveryFocusBounds | null;
}

export interface DiscoveryMapResponse {
  fields: {
    type: 'FeatureCollection';
    features: Array<Record<string, unknown>>;
  };
  taskPoints: {
    type: 'FeatureCollection';
    features: Array<Record<string, unknown>>;
  };
}

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
