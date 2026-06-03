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

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
