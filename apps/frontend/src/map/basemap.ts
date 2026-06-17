import type {
  AppConfig,
  BasemapPlacesPreference,
  BasemapProvider,
  BasemapUsageModel,
} from '@/types/api';

const DEFAULT_BASEMAP = {
  provider: 'esri' as BasemapProvider,
  style: 'arcgis/imagery',
  styleFamily: 'arcgis',
  usageModel: 'session' as BasemapUsageModel,
  places: 'none' as BasemapPlacesPreference,
  sessionDurationSeconds: 43_200,
};

const PLACE_VALUES = new Set<BasemapPlacesPreference>(['all', 'attributed', 'none']);
const PROVIDER_VALUES = new Set<BasemapProvider>(['esri', 'osm', 'empty']);
const MAX_SESSION_SECONDS = 43_200;
const DEFAULT_REFRESH_SAFETY_MARGIN_SECONDS = 300;
const OSM_ATTRIBUTION = '© OpenStreetMap contributors';

export class BasemapConfigurationError extends Error {
  readonly code = 'BASEMAP_CONFIGURATION_ERROR';

  constructor(message: string) {
    super(message);
    this.name = 'BasemapConfigurationError';
  }
}

export interface EsriBasemapResolvedConfig {
  provider: 'esri';
  apiKey: string;
  style: string;
  styleFamily: 'arcgis';
  places: BasemapPlacesPreference;
  sessionDurationSeconds: number;
  refreshSafetyMarginSeconds: number;
}

export interface OsmBasemapResolvedConfig {
  provider: 'osm';
  attribution: string;
}

export interface EmptyBasemapResolvedConfig {
  provider: 'empty';
}

export type ResolvedBasemapConfig =
  | EsriBasemapResolvedConfig
  | OsmBasemapResolvedConfig
  | EmptyBasemapResolvedConfig;

function envValue(value: string | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed || trimmed.startsWith('<')) return null;
  return trimmed;
}

function resolvePlaces(value: string | undefined): BasemapPlacesPreference {
  if (value && PLACE_VALUES.has(value as BasemapPlacesPreference)) {
    return value as BasemapPlacesPreference;
  }
  return DEFAULT_BASEMAP.places;
}

function resolveSessionSeconds(value: string | number | undefined): number {
  const raw = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_BASEMAP.sessionDurationSeconds;
  return Math.min(Math.floor(raw), MAX_SESSION_SECONDS);
}

function resolveProvider(value: string | undefined): BasemapProvider | null {
  if (value && PROVIDER_VALUES.has(value as BasemapProvider)) {
    return value as BasemapProvider;
  }
  return null;
}

export function resolveBasemapConfig(config: AppConfig | undefined): ResolvedBasemapConfig {
  const serverConfig = config?.basemap ?? DEFAULT_BASEMAP;
  const provider =
    resolveProvider(envValue(import.meta.env.VITE_BASEMAP_PROVIDER) ?? undefined) ??
    resolveProvider(serverConfig.provider) ??
    DEFAULT_BASEMAP.provider;

  if (provider === 'osm') {
    return { provider: 'osm', attribution: OSM_ATTRIBUTION };
  }

  if (provider === 'empty') {
    return { provider: 'empty' };
  }

  if (provider !== 'esri') {
    throw new BasemapConfigurationError(
      `Unsupported basemap provider "${provider}". Use "esri", "osm", or "empty".`,
    );
  }
  if (serverConfig.usageModel !== 'session') {
    throw new BasemapConfigurationError(
      `Unsupported Esri basemap usage model "${serverConfig.usageModel}". Use basemap sessions.`,
    );
  }

  const apiKey = envValue(import.meta.env.VITE_ESRI_API_KEY);
  if (!apiKey) {
    throw new BasemapConfigurationError(
      'Esri basemap is not configured. Set VITE_ESRI_API_KEY to a referrer-restricted ArcGIS Location Platform key with Basemaps privilege.',
    );
  }

  const style = envValue(import.meta.env.VITE_ESRI_BASEMAP_STYLE) ?? serverConfig.style;
  const styleFamily =
    envValue(import.meta.env.VITE_ESRI_BASEMAP_STYLE_FAMILY) ?? serverConfig.styleFamily;
  if (styleFamily !== 'arcgis') {
    throw new BasemapConfigurationError(
      `Unsupported Esri basemap style family "${styleFamily}". Use "arcgis" with arcgis/imagery.`,
    );
  }

  return {
    provider: 'esri',
    apiKey,
    style: style || DEFAULT_BASEMAP.style,
    styleFamily,
    places: resolvePlaces(
      envValue(import.meta.env.VITE_ESRI_BASEMAP_PLACES) ?? serverConfig.places,
    ),
    sessionDurationSeconds: resolveSessionSeconds(
      envValue(import.meta.env.VITE_ESRI_BASEMAP_SESSION_SECONDS) ??
      serverConfig.sessionDurationSeconds,
    ),
    refreshSafetyMarginSeconds: DEFAULT_REFRESH_SAFETY_MARGIN_SECONDS,
  };
}
