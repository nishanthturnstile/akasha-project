import { createContext } from 'react';

export interface MapViewState {
    /** User-chosen imagery source; `undefined` => first source from `/api/sources`. */
    activeSourceId: string | undefined;
    /** User-chosen acquisition date; `null` => server-derived default date. */
    selectedDate: string | null;
    /** User-chosen render mode; `null` => source default display mode. */
    displayMode: string | null;
    /** Overlay opacity, 0..100 (percent). */
    opacity: number;
    /** Overlay visibility toggle. */
    visible: boolean;
    /** Layers surface (left drawer / bottom sheet) expanded. */
    layersOpen: boolean;
    /** Compare (A-over-B opacity blend) mode active. */
    compareEnabled: boolean;
    /** The "B" acquisition date to blend under the active date; `null` when unset. */
    compareDate: string | null;
    /** Client-only selected field/plot id; server field data stays in TanStack Query. */
    selectedPlotId: string | null;
    /** Field scene visual cloud mask switches; statistics keep server-safe defaults. */
    cloudMask: {
        clouds: boolean;
        cloudShadows: boolean;
        cirrus: boolean;
    };
    /** Legend visibility toggle. RGB still renders no legend content. */
    legendOpen: boolean;
    /** Inclusive timeline window start (YYYY-MM-DD); `null` => no lower bound. */
    periodFrom: string | null;
    /** Inclusive timeline window end (YYYY-MM-DD); `null` => no upper bound. */
    periodTo: string | null;
    /** Discrete (classified) palette mode for the active index legend/raster. */
    legendStatic: boolean;
    /** Layer control bar collapsed (icon-only) state. */
    layerBarCollapsed: boolean;
    /** Overlay UI visibility (all map chrome except zoom/compass/controls). */
    overlaysVisible: boolean;
    /** Header bar visibility (center title "Add Field"). */
    headerVisible: boolean;
    /** Bottom action bar visibility (Cancel / Save buttons). */
    bottomBarVisible: boolean;
    /** Pending user action to be picked up by MapPage. */
    pendingAction: 'create-field' | null;
    /** Monotonic counter bumped on explicit focus requests (bypasses duplicate guard). */
    focusNonce: number;
    /**
     * Map card fills available height, hiding the bottom analytics panel (drawer closed).
     * Defaults to `true` so the analytics drawer stays closed on load and only opens when
     * the user clicks the drawer toggle near the timeline.
     */
    mapFullscreen: boolean;
    /** Timeline uses the best available observation resolver instead of one source's dates. */
    bestMode: boolean;
    /** Mirrors AppShell's Global View mode so MapPage can render all season fields. */
    globalViewOpen: boolean;
    /** Show the selected field-clipped radar evidence instead of the optical index overlay. */
    radarEvidenceVisible: boolean;
}

export const initialMapViewState: MapViewState = {
    activeSourceId: undefined,
    selectedDate: null,
    displayMode: null,
    opacity: 100,
    visible: true,
    layersOpen: false,
    compareEnabled: false,
    compareDate: null,
    selectedPlotId: null,
    cloudMask: {
        clouds: true,
        cloudShadows: true,
        cirrus: true,
    },
    legendOpen: true,
    periodFrom: null,
    periodTo: null,
    legendStatic: false,
    layerBarCollapsed: false,
    overlaysVisible: false,
    headerVisible: true,
    bottomBarVisible: true,
    pendingAction: null,
    focusNonce: 0,
    mapFullscreen: true,
    bestMode: false,
    globalViewOpen: false,
    radarEvidenceVisible: false,
};

export interface MapViewContextValue extends MapViewState {
    setSource: (sourceId: string) => void;
    setDate: (date: string) => void;
    setDisplayMode: (displayMode: string) => void;
    setOpacity: (opacity: number) => void;
    setVisible: (visible: boolean) => void;
    setLayersOpen: (open: boolean) => void;
    toggleLayers: () => void;
    setCompareEnabled: (enabled: boolean) => void;
    setCompareDate: (date: string | null) => void;
    setSelectedPlotId: (plotId: string | null) => void;
    clearSelectedPlot: () => void;
    setCloudMask: (cloudMask: MapViewState['cloudMask']) => void;
    setLegendOpen: (open: boolean) => void;
    setPeriod: (from: string | null, to: string | null) => void;
    setLegendStatic: (staticMode: boolean) => void;
    setLayerBarCollapsed: (collapsed: boolean) => void;
    setOverlaysVisible: (visible: boolean) => void;
    setHeaderVisible: (visible: boolean) => void;
    setBottomBarVisible: (visible: boolean) => void;
    setPendingAction: (action: 'create-field' | null) => void;
    setFocusNonce: (nonce: number) => void;
    setMapFullscreen: (fullscreen: boolean) => void;
    setBestMode: (enabled: boolean) => void;
    setGlobalViewOpen: (open: boolean) => void;
    setRadarEvidenceVisible: (visible: boolean) => void;
}

export const MapViewContext = createContext<MapViewContextValue | null>(null);
