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

/** Standard BFF error envelope: { error: { code, message, details } }. */
export interface ApiErrorShape {
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}
