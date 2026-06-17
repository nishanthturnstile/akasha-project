import { BasemapSession } from '@esri/maplibre-arcgis';
import type { EsriBasemapResolvedConfig } from '@/map/basemap';

type SharedSession = {
    key: string;
    session: Promise<BasemapSession>;
};

let sharedSession: SharedSession | null = null;

function sessionKeyOf(config: EsriBasemapResolvedConfig): string {
    return [
        config.apiKey,
        config.styleFamily,
        config.sessionDurationSeconds,
        config.refreshSafetyMarginSeconds,
    ].join('|');
}

export function getSharedEsriBasemapSession(
    config: EsriBasemapResolvedConfig,
): Promise<BasemapSession> {
    const key = sessionKeyOf(config);
    if (sharedSession?.key === key) return sharedSession.session;

    const session = BasemapSession.start({
        token: config.apiKey,
        styleFamily: config.styleFamily,
        duration: config.sessionDurationSeconds,
        autoRefresh: true,
        safetyMargin: config.refreshSafetyMarginSeconds,
    });
    sharedSession = { key, session };
    return session;
}

export function resetSharedEsriBasemapSessionForTests(): void {
    sharedSession = null;
}
