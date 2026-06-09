declare module '@esri/maplibre-arcgis' {
  import type { Map } from 'maplibre-gl';

  export type PlacesOptions = 'all' | 'attributed' | 'none';
  export type StyleFamily = 'arcgis' | 'open';

  export interface IBasemapSessionOptions {
    token: string;
    styleFamily: StyleFamily;
    duration?: number;
    autoRefresh?: boolean;
    safetyMargin?: number;
  }

  export type BasemapSessionEventMap = {
    BasemapSessionRefreshed: unknown;
    BasemapSessionExpired: unknown;
    BasemapSessionError: Error;
  };

  export class BasemapSession {
    static start(options: IBasemapSessionOptions): Promise<BasemapSession>;
    on<K extends keyof BasemapSessionEventMap>(
      eventName: K,
      handler: (data: BasemapSessionEventMap[K]) => void,
    ): void;
    off<K extends keyof BasemapSessionEventMap>(
      eventName: K,
      handler: (data: BasemapSessionEventMap[K]) => void,
    ): void;
  }

  export type BasemapStyleEventMap = {
    BasemapStyleLoad: BasemapStyle;
    BasemapAttributionLoad: unknown;
    BasemapStyleError: Error;
  };

  export interface IBasemapStyleOptions {
    map?: Map;
    style: string;
    token?: string;
    session?: BasemapSession | Promise<BasemapSession>;
    preferences?: {
      places?: PlacesOptions;
      language?: string;
      worldview?: string;
    };
  }

  export class BasemapStyle {
    constructor(options: IBasemapStyleOptions);
    applyTo(map: Map): Map;
    loadStyle(): Promise<unknown>;
    static applyStyle(map: Map, options: IBasemapStyleOptions): BasemapStyle;
    on<K extends keyof BasemapStyleEventMap>(
      eventName: K,
      handler: (data: BasemapStyleEventMap[K]) => void,
    ): void;
    off<K extends keyof BasemapStyleEventMap>(
      eventName: K,
      handler: (data: BasemapStyleEventMap[K]) => void,
    ): void;
  }
}
