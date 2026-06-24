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
export type BasemapUsageModel = 'session';
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

export type SourceKind = 'optical' | 'sar' | 'context' | 'archive';
export type SourceAnalysisLevel = 'field' | 'regional' | 'context' | 'archive';
export type SourceAvailabilityStatus = 'active' | 'gated';

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
  analysisLevel?: SourceAnalysisLevel;
  availabilityStatus?: SourceAvailabilityStatus;
  gatedReason?: string | null;
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

export interface SceneDate {
  /** YYYY-MM-DD */
  acquisitionDate: string;
  datetime: string;
  usablePixelPercent: number | null;
  cloudMaskedPercent: number | null;
  coveragePercent: number | null;
  isLatestUsable: boolean;
  metricsProvisional: boolean;
  tileAvailable: boolean;
  unavailableReason?: string | null;
  sceneCount?: number;
  /** [west, south, east, north] */
  bounds?: [number, number, number, number];
  /** Short sensor badge for the chip (e.g. `S2`, `S1`). */
  sensor?: string | null;
}

export interface DefaultLayer {
  sourceId: string;
  acquisitionDate: string | null;
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

export interface FieldStatisticsRequest {
  sourceId: string;
  acquisitionDate?: string | null;
  indexType: string;
  cloudMask?: CloudMaskOptions;
  preferHighRes?: boolean;
}

export interface FieldStatisticsResponse {
  plotId: string;
  provider: 'native';
  scope: 'field';
  indexType: string;
  sourceId: string;
  acquisitionDate: string;
  cloudMask: CloudMaskOptions;
  statistics: IndexStatistics;
  pixelCounts: PixelCounts;
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
  provider: 'native';
  scope: 'native_fallback';
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
  fieldName?: string | null;
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
  createdAt?: string | null;
  updatedAt?: string | null;
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
  name: string;
  areaHa: number | null;
  geometry: PlotGeometry;
  groupId: string | null;
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
  seasonIds?: string[];
  vegetationData?: VegetationCycleCreate[];
}

export interface FieldUpdatePayload {
  name?: string | null;
  geometry?: PlotGeometry | null;
  areaHa?: number | null;
  groupId?: string | null;
  seasonIds?: string[] | null;
  vegetationData?: VegetationCycleCreate[] | null;
}

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
