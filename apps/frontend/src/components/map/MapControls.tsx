import { useEffect, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Compass, Eye, EyeOff, LocateFixed, Minus, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MapControlsProps {
  map: maplibregl.Map | null;
  hasSelectedField?: boolean;
  legendOpen?: boolean;
  onFindSelectedField?: () => void;
  onLegendOpenChange?: (open: boolean) => void;
  simplified?: boolean;
}

function ControlButton({
  label,
  onClick,
  children,
  testId,
  style,
  disabled,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  testId: string;
  style?: React.CSSProperties;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={ label }
      title={ label }
      data-testid={ testId }
      onClick={ onClick }
      disabled={ disabled }
      style={ style }
      className={ cn(
        'flex h-9 w-9 items-center justify-center text-foreground/80 transition-colors duration-fast ease-standard',
        'hover:bg-accent hover:text-accent-foreground active:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        disabled && 'cursor-not-allowed opacity-45 hover:bg-transparent hover:text-foreground/80',
      ) }
    >
      { children }
    </button>
  );
}

export function MapControls({
  map,
  hasSelectedField = false,
  legendOpen = true,
  onFindSelectedField,
  onLegendOpenChange,
  simplified = false,
}: MapControlsProps) {
  const [bearing, setBearing] = useState(0);

  useEffect(() => {
    if (!map) return;
    const onRotate = () => setBearing(map.getBearing());
    map.on('rotate', onRotate);
    return () => {
      map.off('rotate', onRotate);
    };
  }, [map]);

  const geolocate = () => {
    if (!map || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => map.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 13 }),
      () => undefined,
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  return (
    <div
      className="glass flex flex-col overflow-hidden rounded-md p-0"
      data-testid="map-controls"
      role="group"
      aria-label="Map controls"
    >
      <ControlButton label="Zoom in" testId="zoom-in-btn" onClick={ () => map?.zoomIn() }>
        <Plus className="size-5" strokeWidth={ 1.75 } />
      </ControlButton>
      <div className="h-px w-full bg-border" />
      <ControlButton label="Zoom out" testId="zoom-out-btn" onClick={ () => map?.zoomOut() }>
        <Minus className="size-5" strokeWidth={ 1.75 } />
      </ControlButton>
      <div className="h-px w-full bg-border" />
      <ControlButton
        label="Reset bearing to north"
        testId="compass-btn"
        onClick={ () => map?.resetNorth() }
        style={ { transform: `rotate(${-bearing}deg)` } }
      >
        <Compass className="size-5" strokeWidth={ 1.75 } />
      </ControlButton>
      { !simplified && (
        <>
          <div className="h-px w-full bg-border" />
          <ControlButton label="Find my location" testId="geolocate-btn" onClick={ geolocate }>
            <LocateFixed className="size-5" strokeWidth={ 1.75 } />
          </ControlButton>
        </>
      ) }
      { !simplified && onFindSelectedField && (
        <>
          <div className="h-px w-full bg-border" />
          <ControlButton
            label="Find selected field"
            testId="find-selected-field-btn"
            onClick={ onFindSelectedField }
            disabled={ !hasSelectedField }
          >
            <LocateFixed className="size-5" strokeWidth={ 1.75 } />
          </ControlButton>
        </>
      ) }
      { !simplified && onLegendOpenChange && (
        <>
          <div className="h-px w-full bg-border" />
          <ControlButton
            label={ legendOpen ? 'Hide legend' : 'Show legend' }
            testId="legend-toggle-btn"
            onClick={ () => onLegendOpenChange(!legendOpen) }
          >
            { legendOpen ? (
              <EyeOff className="size-5" strokeWidth={ 1.75 } />
            ) : (
              <Eye className="size-5" strokeWidth={ 1.75 } />
            ) }
          </ControlButton>
        </>
      ) }
    </div>
  );
}
