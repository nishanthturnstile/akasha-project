import { useContext } from 'react';
import { MapViewContext, type MapViewContextValue } from '@/state/mapViewState';

export function useMapView(): MapViewContextValue {
    const ctx = useContext(MapViewContext);
    if (!ctx) {
        throw new Error('useMapView must be used within a <MapViewProvider>.');
    }
    return ctx;
}