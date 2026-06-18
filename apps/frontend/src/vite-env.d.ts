/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BASEMAP_PROVIDER?: string;
  readonly VITE_ESRI_API_KEY?: string;
  readonly VITE_ESRI_BASEMAP_STYLE?: string;
  readonly VITE_ESRI_BASEMAP_STYLE_FAMILY?: string;
  readonly VITE_ESRI_BASEMAP_PLACES?: string;
  readonly VITE_ESRI_BASEMAP_SESSION_SECONDS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
