import {
    useEffect,
    useMemo,
    useReducer,
    type ReactNode,
} from 'react';
import {
    MapViewContext,
    initialMapViewState,
    type MapViewContextValue,
    type MapViewState,
} from '@/state/mapViewState';

/**
 * Client-only UI state for the Map screen redesign (docs/map-screen-redesign.md §6).
 *
 * Server state (config / sources / dates / default layer) stays in TanStack Query.
 * This reducer consolidates the growing pile of view state — active source, date
 * override, display mode, opacity/visibility, and which chrome panels are open —
 * so it no longer prop-drills through `MapPage`.
 *
 * Overrides are intentionally nullable: a `null`/`undefined` value means "fall back
 * to the server-derived default" (e.g. the latest-usable date), which keeps the
 * cold-start behaviour identical to the pre-redesign `useState` model.
 */

type MapViewAction =
    | { type: 'SET_SOURCE'; sourceId: string }
    | { type: 'SET_DATE'; date: string }
    | { type: 'SET_DISPLAY_MODE'; displayMode: string }
    | { type: 'SET_OPACITY'; opacity: number }
    | { type: 'SET_VISIBLE'; visible: boolean }
    | { type: 'SET_LAYERS_OPEN'; open: boolean }
    | { type: 'TOGGLE_LAYERS' }
    | { type: 'SET_COMPARE_ENABLED'; enabled: boolean }
    | { type: 'SET_COMPARE_DATE'; date: string | null }
    | { type: 'SET_SELECTED_PLOT_ID'; plotId: string | null }
    | { type: 'CLEAR_SELECTED_PLOT' }
    | {
        type: 'SET_CLOUD_MASK';
        cloudMask: { clouds: boolean; cloudShadows: boolean; cirrus: boolean };
    }
    | { type: 'SET_LEGEND_OPEN'; open: boolean }
    | { type: 'SET_PERIOD'; from: string | null; to: string | null }
    | { type: 'SET_LEGEND_STATIC'; staticMode: boolean }
    | { type: 'SET_LAYER_BAR_COLLAPSED'; collapsed: boolean }
    | { type: 'SET_OVERLAYS_VISIBLE'; visible: boolean }
    | { type: 'SET_HEADER_VISIBLE'; visible: boolean }
    | { type: 'SET_BOTTOM_BAR_VISIBLE'; visible: boolean }
    | { type: 'SET_PENDING_ACTION'; action: 'create-field' | null }
    | { type: 'SET_FOCUS_NONCE'; nonce: number }
    | { type: 'SET_MAP_FULLSCREEN'; fullscreen: boolean };

function reducer(state: MapViewState, action: MapViewAction): MapViewState {
    switch (action.type) {
        case 'SET_SOURCE':
            if (action.sourceId === state.activeSourceId) return state;
            // Switching source invalidates source-scoped imagery selections so the new source
            // recomputes its own default date / display mode and compare scene.
            return {
                ...state,
                activeSourceId: action.sourceId,
                selectedDate: null,
                displayMode: null,
                compareEnabled: false,
                compareDate: null,
            };
        case 'SET_DATE':
            if (action.date === state.selectedDate) return state;
            return { ...state, selectedDate: action.date };
        case 'SET_DISPLAY_MODE':
            if (action.displayMode === state.displayMode) return state;
            return { ...state, displayMode: action.displayMode };
        case 'SET_OPACITY':
            return { ...state, opacity: action.opacity };
        case 'SET_VISIBLE':
            return { ...state, visible: action.visible };
        case 'SET_LAYERS_OPEN':
            return { ...state, layersOpen: action.open };
        case 'TOGGLE_LAYERS':
            return { ...state, layersOpen: !state.layersOpen };
        case 'SET_COMPARE_ENABLED':
            if (action.enabled === state.compareEnabled) return state;
            // Leaving compare clears the B date so re-entering starts clean.
            return {
                ...state,
                compareEnabled: action.enabled,
                compareDate: action.enabled ? state.compareDate : null,
            };
        case 'SET_COMPARE_DATE':
            if (action.date === state.compareDate) return state;
            return { ...state, compareDate: action.date };
        case 'SET_SELECTED_PLOT_ID':
            if (action.plotId === state.selectedPlotId) return state;
            return { ...state, selectedPlotId: action.plotId };
        case 'CLEAR_SELECTED_PLOT':
            if (state.selectedPlotId === null) return state;
            return { ...state, selectedPlotId: null };
        case 'SET_CLOUD_MASK':
            return { ...state, cloudMask: action.cloudMask };
        case 'SET_LEGEND_OPEN':
            if (action.open === state.legendOpen) return state;
            return { ...state, legendOpen: action.open };
        case 'SET_PERIOD':
            if (action.from === state.periodFrom && action.to === state.periodTo) return state;
            return { ...state, periodFrom: action.from, periodTo: action.to };
        case 'SET_LEGEND_STATIC':
            if (action.staticMode === state.legendStatic) return state;
            return { ...state, legendStatic: action.staticMode };
        case 'SET_LAYER_BAR_COLLAPSED':
            if (action.collapsed === state.layerBarCollapsed) return state;
            return { ...state, layerBarCollapsed: action.collapsed };
        case 'SET_OVERLAYS_VISIBLE':
            if (action.visible === state.overlaysVisible) return state;
            return { ...state, overlaysVisible: action.visible };
        case 'SET_HEADER_VISIBLE':
            if (action.visible === state.headerVisible) return state;
            return { ...state, headerVisible: action.visible };
        case 'SET_BOTTOM_BAR_VISIBLE':
            if (action.visible === state.bottomBarVisible) return state;
            return { ...state, bottomBarVisible: action.visible };
        case 'SET_PENDING_ACTION':
            if (action.action === state.pendingAction) return state;
            return { ...state, pendingAction: action.action };
        case 'SET_FOCUS_NONCE':
            if (action.nonce === state.focusNonce) return state;
            return { ...state, focusNonce: action.nonce };
        case 'SET_MAP_FULLSCREEN':
            if (action.fullscreen === state.mapFullscreen) return state;
            return { ...state, mapFullscreen: action.fullscreen };
        default:
            return state;
    }
}

/**
 * Persist the selected field across reloads and module navigations so weather,
 * VRA, analytics, and risk pages remain usable when opened directly. Only the
 * field id is persisted; all server data stays in TanStack Query.
 */
const SELECTED_PLOT_STORAGE_KEY = 'akasha.selectedPlotId';

function readPersistedPlotId(): string | null {
    if (typeof window === 'undefined') return null;
    try {
        return window.localStorage.getItem(SELECTED_PLOT_STORAGE_KEY) || null;
    } catch {
        return null;
    }
}

function writePersistedPlotId(plotId: string | null): void {
    if (typeof window === 'undefined') return;
    try {
        if (plotId) {
            window.localStorage.setItem(SELECTED_PLOT_STORAGE_KEY, plotId);
        } else {
            window.localStorage.removeItem(SELECTED_PLOT_STORAGE_KEY);
        }
    } catch {
        /* storage unavailable (private mode / quota) — selection stays in-memory only */
    }
}

export function MapViewProvider({
    children,
    initialState,
}: {
    children: ReactNode;
    initialState?: Partial<MapViewState>;
}) {
    const [state, dispatch] = useReducer(reducer, {
        ...initialMapViewState,
        selectedPlotId: readPersistedPlotId(),
        ...initialState,
    });

    useEffect(() => {
        writePersistedPlotId(state.selectedPlotId);
    }, [state.selectedPlotId]);

    const value = useMemo<MapViewContextValue>(
        () => ({
            ...state,
            setSource: (sourceId) => dispatch({ type: 'SET_SOURCE', sourceId }),
            setDate: (date) => dispatch({ type: 'SET_DATE', date }),
            setDisplayMode: (displayMode) => dispatch({ type: 'SET_DISPLAY_MODE', displayMode }),
            setOpacity: (opacity) => dispatch({ type: 'SET_OPACITY', opacity }),
            setVisible: (visible) => dispatch({ type: 'SET_VISIBLE', visible }),
            setLayersOpen: (open) => dispatch({ type: 'SET_LAYERS_OPEN', open }),
            toggleLayers: () => dispatch({ type: 'TOGGLE_LAYERS' }),
            setCompareEnabled: (enabled) => dispatch({ type: 'SET_COMPARE_ENABLED', enabled }),
            setCompareDate: (date) => dispatch({ type: 'SET_COMPARE_DATE', date }),
            setSelectedPlotId: (plotId) => dispatch({ type: 'SET_SELECTED_PLOT_ID', plotId }),
            clearSelectedPlot: () => dispatch({ type: 'CLEAR_SELECTED_PLOT' }),
            setCloudMask: (cloudMask) => dispatch({ type: 'SET_CLOUD_MASK', cloudMask }),
            setLegendOpen: (open) => dispatch({ type: 'SET_LEGEND_OPEN', open }),
            setPeriod: (from, to) => dispatch({ type: 'SET_PERIOD', from, to }),
            setLegendStatic: (staticMode) =>
                dispatch({ type: 'SET_LEGEND_STATIC', staticMode }),
            setLayerBarCollapsed: (collapsed) =>
                dispatch({ type: 'SET_LAYER_BAR_COLLAPSED', collapsed }),
            setOverlaysVisible: (visible) =>
                dispatch({ type: 'SET_OVERLAYS_VISIBLE', visible }),
            setHeaderVisible: (visible) =>
                dispatch({ type: 'SET_HEADER_VISIBLE', visible }),
            setBottomBarVisible: (visible) =>
                dispatch({ type: 'SET_BOTTOM_BAR_VISIBLE', visible }),
            setPendingAction: (action) =>
                dispatch({ type: 'SET_PENDING_ACTION', action }),
            setFocusNonce: (nonce) =>
                dispatch({ type: 'SET_FOCUS_NONCE', nonce }),
            setMapFullscreen: (fullscreen) =>
                dispatch({ type: 'SET_MAP_FULLSCREEN', fullscreen }),
        }),
        [state],
    );

    return <MapViewContext.Provider value={ value }>{ children }</MapViewContext.Provider>;
}
