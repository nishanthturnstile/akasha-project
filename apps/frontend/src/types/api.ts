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

export interface AppConfig {
  appName: string;
  aoi: AoiConfig;
  /** May be empty; resolve via basemap precedence rule. */
  basemapStyleUrl: string;
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

export type ProviderSyncStatus = 'not_synced' | 'pending' | 'synced' | 'failed';

export interface CloudMaskOptions {
  clouds: boolean;
  cloudShadows: boolean;
  cirrus: boolean;
}

export interface CloudMaskMapping {
  nativeExcludedSclClasses: number[];
  eosCloudMaskingLevel?: number | null;
  eosExact: boolean;
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
  externalProvider?: string | null;
  externalFieldId?: string | null;
  providerSyncStatus?: ProviderSyncStatus | null;
  providerSyncedAt?: string | null;
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

export interface ProviderSyncResponse {
  plotId: string;
  provider: string;
  syncStatus: ProviderSyncStatus;
  syncedAt?: string | null;
  field?: {
    plotId: string;
    provider: string;
    externalFieldId: string;
    syncStatus: ProviderSyncStatus;
    syncedAt?: string | null;
    providerAreaHa?: number | null;
  } | null;
}

export type FieldLayerKind = 'rgb' | 'index' | 'composite';

export interface FieldLayer {
  displayMode: string;
  label: string;
  kind: FieldLayerKind;
  tileUrlTemplate: string;
  available: boolean;
  unavailableReason?: string | null;
  attribution: string;
}

export interface FieldScene {
  sceneToken: string;
  acquisitionDate: string;
  datetime?: string | null;
  sensor?: string | null;
  cloudPercent?: number | null;
  usablePixelPercent: number | null;
  cloudMaskedPercent?: number | null;
  coveragePercent?: number | null;
  bounds?: [number, number, number, number];
  tileAvailable: boolean;
  metricsProvisional: boolean;
  sceneCount?: number | null;
  layers: FieldLayer[];
}

export interface FieldSceneListResponse {
  plotId: string;
  provider: string;
  scope: 'field' | 'global_fallback';
  sourceId: string;
  defaultDisplayMode: 'RGB';
  displayModes: string[];
  scenes: FieldScene[];
  fallbackReason?: string | null;
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
  sclExcludedPixels: number;
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
    cloudMask?: string;
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
  min: number | null;
  max: number | null;
  stddev: number | null;
  validPixelPercent?: number | null;
  cloudMaskedPercent?: number | null;
  coveragePercent?: number | null;
  cloudPercent?: number | null;
  metricsProvisional: boolean;
  unavailableReason?: string | null;
}

export interface FieldTrendResponse {
  plotId: string;
  provider: string;
  scope: 'field' | 'native_fallback';
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
  provider?: 'auto' | 'eos' | 'native';
  sceneToken?: string | null;
  cloudMask?: CloudMaskOptions;
}

export interface FieldReportExportOptions {
  sourceId: string;
  indexType: string;
  provider?: 'auto' | 'eos' | 'native';
  startDate?: string;
  endDate?: string;
  cloudMask?: CloudMaskOptions;
}

export interface FileDownload {
  blob: Blob;
  filename: string;
}

export type WeatherProviderChoice = 'auto' | 'eos';

export type WeatherSeriesId =
  | 'accumulatedPrecipitation'
  | 'dailyPrecipitation'
  | 'dailyTemperature'
  | 'sumActiveTemperatures'
  | 'evapotranspiration'
  | 'relativeHumidity'
  | 'globalRadiation';

export interface WeatherForecastCard {
  id: 'temperature' | 'precipitation' | 'relativeHumidity' | 'clouds' | 'wind';
  label: string;
  value: number | null;
  unit: string;
  secondaryValue?: number | null;
  secondaryUnit?: string | null;
  summary: string;
}

export interface WeatherForecastPoint {
  date: string;
  startTime?: string | null;
  endTime?: string | null;
  temperatureMinC?: number | null;
  temperatureMaxC?: number | null;
  temperatureAvgC?: number | null;
  precipitationMm?: number | null;
  humidityPercent?: number | null;
  cloudinessPercent?: number | null;
  windMps?: number | null;
  windDirection?: string | null;
  conditions?: string | null;
}

export interface WeatherForecastResponse {
  plotId: string;
  provider: string;
  scope: 'field';
  startDate: string;
  endDate: string;
  cards: WeatherForecastCard[];
  timeline: WeatherForecastPoint[];
  metadata: Record<string, unknown>;
}

export interface WeatherSeriesPoint {
  date: string;
  value: number | null;
}

export interface WeatherSeries {
  id: WeatherSeriesId | 'soilMoisture';
  label: string;
  unit: string;
  available: boolean;
  unavailableReason?: string | null;
  points: WeatherSeriesPoint[];
}

export interface WeatherHistoryResponse {
  plotId: string;
  provider: string;
  scope: 'field';
  startDate: string;
  endDate: string;
  series: WeatherSeries[];
  metadata: Record<string, unknown>;
}

export interface WeatherSoilMoistureResponse {
  plotId: string;
  provider: string;
  scope: 'field';
  startDate: string;
  endDate: string;
  available: boolean;
  series?: WeatherSeries | null;
  unavailableReason?: string | null;
  unavailableCode?: string | null;
  metadata: Record<string, unknown>;
}

export type ZoningStatus = 'processing' | 'ready' | 'failed' | 'unknown';

export interface VegetationZoningRequest {
  indexType: string;
  imageDate: string;
  zoneCount: number;
  minZoneArea: number;
  provider?: 'auto' | 'eos';
  asyncProcessing?: boolean;
}

export interface ZoningZone {
  zoneId: string;
  color: string;
  areaHa?: number | null;
  areaPercent?: number | null;
  clusterValue?: number | null;
  geometry?: PlotGeometry | null;
}

export interface ZoningMapMetadata {
  requestedAt?: string | null;
  imageDate?: string | null;
  indexType?: string | null;
  zoneCount?: number | null;
  minZoneAreaHa?: number | null;
  statusUpdatedAt?: string | null;
  source: 'provider-adapter';
}

export interface ZoningMap {
  plotId: string;
  mapId: string;
  provider: string;
  status: ZoningStatus;
  mapType: string;
  indexType?: string | null;
  imageDate?: string | null;
  zoneCount?: number | null;
  minZoneAreaHa?: number | null;
  zones: ZoningZone[];
  metadata: ZoningMapMetadata;
}

export interface ZoningMapListResponse {
  plotId: string;
  provider: string;
  maps: ZoningMap[];
}

export type ZoningExportFormat = 'geojson' | 'shp';

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
