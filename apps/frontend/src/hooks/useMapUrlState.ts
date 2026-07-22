import { useEffect, useLayoutEffect, useRef } from 'react';
import {
    useInRouterContext,
    useNavigate,
    useParams,
    useSearchParams,
} from 'react-router-dom';
import { useMapView } from '@/state/useMapView';

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

function maskFromParam(value: string | null) {
    if (!value || !/^[01]{3}$/.test(value)) return null;
    return { clouds: value[0] === '1', cloudShadows: value[1] === '1', cirrus: value[2] === '1' };
}

function maskToParam(value: { clouds: boolean; cloudShadows: boolean; cirrus: boolean }) {
    return `${Number(value.clouds)}${Number(value.cloudShadows)}${Number(value.cirrus)}`;
}

/**
 * Bridges deep-linkable URL state (route param `:plotId` + `?scene&from&to&source&layer`)
 * with the {@link useMapView} reducer. Hydrates on mount and replaces history (no
 * pushes) on context changes so navigating back/forward feels like normal browsing.
 *
 * Uses Akasha-native param names, not backend scene identifiers.
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
    const urlPlotId = normalizeIdParam(params.plotId);

    // Hydration runs once: route/search params win over persisted state on first mount
    // so a shared link always shows the linked scene rather than a stale local one.
    const hydrated = useRef(false);

    useLayoutEffect(() => {
        if (hydrated.current) return;
        hydrated.current = true;

        const plotId = normalizeIdParam(params.plotId);
        if (plotId && plotId !== view.selectedPlotId) {
            view.setSelectedPlotId(plotId);
            view.setFocusNonce(Date.now());
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
        if (search.get('split') === '1') view.setSplitEnabled(true);
        const rightSource = search.get('rightSource')?.trim();
        if (rightSource) view.setRightSource(rightSource);
        const rightScene = isoDateOrNull(search.get('rightScene'));
        if (rightScene) view.setRightDate(rightScene);
        const rightLayer = search.get('rightLayer')?.trim();
        if (rightLayer) view.setRightDisplayMode(rightLayer);
        const rightFrom = isoDateOrNull(search.get('rightFrom'));
        const rightTo = isoDateOrNull(search.get('rightTo'));
        if (rightFrom || rightTo) view.setRightPeriod(rightFrom, rightTo);
        if (search.get('profile') === 'contrast') view.setRenderProfile('contrast');
        if (search.get('rightProfile') === 'contrast') view.setRightRenderProfile('contrast');
        const leftMask = maskFromParam(search.get('mask'));
        if (leftMask) view.setCloudMask(leftMask);
        const rightMask = maskFromParam(search.get('rightMask'));
        if (rightMask) view.setRightCloudMask(rightMask);
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
        next.set('mask', maskToParam(view.cloudMask));
        if (view.renderProfile === 'contrast') next.set('profile', 'contrast');
        if (view.splitEnabled) {
            next.set('split', '1');
            if (view.rightSourceId) next.set('rightSource', view.rightSourceId);
            if (view.rightDate) next.set('rightScene', view.rightDate);
            if (view.rightDisplayMode) next.set('rightLayer', view.rightDisplayMode);
            if (view.rightPeriodFrom) next.set('rightFrom', view.rightPeriodFrom);
            if (view.rightPeriodTo) next.set('rightTo', view.rightPeriodTo);
            next.set('rightMask', maskToParam(view.rightCloudMask));
            if (view.rightRenderProfile === 'contrast') next.set('rightProfile', 'contrast');
        }

        const queryString = next.toString();
        const effectivePlotId = view.selectedPlotId;
        const basePath = effectivePlotId
            ? `/monitoring/field-analytics/field/${effectivePlotId}`
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
        urlPlotId,
        view.cloudMask,
        view.renderProfile,
        view.splitEnabled,
        view.rightSourceId,
        view.rightDate,
        view.rightDisplayMode,
        view.rightPeriodFrom,
        view.rightPeriodTo,
        view.rightCloudMask,
        view.rightRenderProfile,
        navigate,
    ]);
}
