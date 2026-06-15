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

export type BasemapProvider = 'esri';
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
  /** Backward-compatible field. Esri basemaps are configured through `basemap`. */
  basemapStyleUrl: string;
  basemap: BasemapConfig;
  maxPolygonAreaHa: number;
  maxPolygonVertices: number;
  usablePixelThresholdPercent: number;
  supportedIndices: string[];
  defaultIndex: string;
}

export type SourceKind = 'optical' | 'sar';

export interface Source {
  id: string;
  label: string;
  provider: string;
  kind?: SourceKind;
  displayModes?: string[];
  defaultDisplayMode?: string;
  displayMode?: string;
  description?: string;
  attribution?: string;
  supportedIndices?: string[];
  maskMethod?: string | null;
  availableMaskOptions?: Array<keyof CloudMaskOptions>;
  metricsProvisional?: boolean;
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
  sceneCount?: number;
  /** [west, south, east, north] */
  bounds?: [number, number, number, number];
  /** Short sensor badge for the chip (e.g. `S2`, `S1`). */
  sensor?: string | null;
}

export interface DefaultLayer {
  sourceId: string;
  acquisitionDate: string;
  displayMode?: string;
  kind?: SourceKind;
  displayModes?: string[];
  defaultDisplayMode?: string;
  description?: string;
  supportedIndices?: string[];
  /** Same-origin `/api/tiles/.../{z}/{x}/{y}.png` template — never a COG/MinIO/TiTiler URL. */
  tileUrlTemplate: string;
  /** [west, south, east, north] */
  bounds?: [number, number, number, number];
  sceneCount?: number;
  minzoom: number;
  maxzoom: number;
  attribution: string;
  usablePixelPercent: number | null;
  metricsProvisional: boolean;
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
  metadata: {
    formula?: string;
    bands?: string[];
    maskMethod?: string;
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
  user: { id: string; username?: string | null; email: string; displayName: string };
  currentTeam: { id: string; name: string; role: string };
  memberships: Array<{ teamId: string; teamName: string; role: string }>;
  authMode: string;
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

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
