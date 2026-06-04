import { useEffect, useRef } from 'react';
import {
    useInRouterContext,
    useNavigate,
    useParams,
    useSearchParams,
} from 'react-router-dom';
import { useMapView } from '@/state/mapViewContext';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isoDateOrNull(value: string | null): string | null {
    if (!value) return null;
    return ISO_DATE.test(value) ? value : null;
}

function normalizeIdParam(value: string | null | undefined): string | null {
    if (!value) return null;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
}

/**
 * Bridges deep-linkable URL state (route param `:plotId` + `?scene&from&to&source&layer`)
 * with the {@link useMapView} reducer. Hydrates on mount and replaces history (no
 * pushes) on context changes so navigating back/forward feels like normal browsing.
 *
 * Mirrors the EOS deep-link model
 * (`/analytics/field/{id}?sceneID=...&period_from=...&period_to=...`) using Akasha-native
 * param names — never EOS scene ids — per docs/eos/eos-map-screen-ui-parity-plan.md §11.
 *
 * Safe to call outside a React Router context — becomes a no-op so that legacy unit
 * tests rendering `MapPage` without a router keep working.
 */
export function useMapUrlState(): void {
    const inRouter = useInRouterContext();
    if (inRouter) {
        // eslint-disable-next-line react-hooks/rules-of-hooks
        useRoutedMapUrlState();
    }
}

function useRoutedMapUrlState(): void {
    const view = useMapView();
    const navigate = useNavigate();
    const [search] = useSearchParams();
    const params = useParams();

    // Hydration runs once: route/search params win over persisted state on first mount
    // so a shared link always shows the linked scene rather than a stale local one.
    const hydrated = useRef(false);

    useEffect(() => {
        if (hydrated.current) return;
        hydrated.current = true;

        const plotId = normalizeIdParam(params.plotId);
        if (plotId && plotId !== view.selectedPlotId) {
            view.setSelectedPlotId(plotId);
        }

        // SET_SOURCE clears selectedDate / displayMode (source switch invalidates
        // imagery selection), so hydrate source FIRST and let scene/layer follow.
        const source = search.get('source')?.trim();
        if (source && source !== view.activeSourceId) {
            view.setSource(source);
        }

        const scene = isoDateOrNull(search.get('scene'));
        if (scene && scene !== view.selectedDate) {
            view.setDate(scene);
        }

        const from = isoDateOrNull(search.get('from'));
        const to = isoDateOrNull(search.get('to'));
        if (from !== view.periodFrom || to !== view.periodTo) {
            view.setPeriod(from, to);
        }

        const layer = search.get('layer')?.trim();
        if (layer && layer !== view.displayMode) {
            view.setDisplayMode(layer);
        }
    // We intentionally hydrate from the initial route only — subsequent URL changes
    // are written back from the reducer below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Serialize reducer state back into the URL. Skipped until hydration so a stale
    // empty reducer cannot overwrite link-supplied values.
    useEffect(() => {
        if (!hydrated.current) return;

        const next = new URLSearchParams();
        if (view.selectedDate) next.set('scene', view.selectedDate);
        if (view.periodFrom) next.set('from', view.periodFrom);
        if (view.periodTo) next.set('to', view.periodTo);
        if (view.activeSourceId) next.set('source', view.activeSourceId);
        if (view.displayMode) next.set('layer', view.displayMode);

        const queryString = next.toString();
        const basePath = view.selectedPlotId
            ? `/monitoring/field-analytics/field/${view.selectedPlotId}`
            : '/monitoring/field-analytics';
        const targetUrl = queryString ? `${basePath}?${queryString}` : basePath;

        const currentPath = `${window.location.pathname}${window.location.search}`;
        if (currentPath !== targetUrl) {
            navigate(targetUrl, { replace: true });
        }
    }, [
        view.selectedPlotId,
        view.selectedDate,
        view.periodFrom,
        view.periodTo,
        view.activeSourceId,
        view.displayMode,
        navigate,
    ]);
}
