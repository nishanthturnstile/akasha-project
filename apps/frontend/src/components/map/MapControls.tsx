import { useEffect, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { Compass, LocateFixed, Maximize, Minimize, Minus, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MapControlsProps {
  map: maplibregl.Map | null;
}

function ControlButton({
  label,
  onClick,
  children,
  testId,
  style,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  testId: string;
  style?: React.CSSProperties;
}) {
  return (
    <button
      type="button"
      aria-label={ label }
      title={ label }
      data-testid={ testId }
      onClick={ onClick }
      style={ style }
      className={ cn(
        'flex h-9 w-9 items-center justify-center text-foreground/80 transition-colors duration-fast ease-standard',
        'hover:bg-accent hover:text-accent-foreground active:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      ) }
    >
      { children }
    </button>
  );
}

export function MapControls({ map }: MapControlsProps) {
  const [bearing, setBearing] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!map) return;
    const onRotate = () => setBearing(map.getBearing());
    map.on('rotate', onRotate);
    return () => {
      map.off('rotate', onRotate);
    };
  }, [map]);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const fullscreenSupported =
    typeof document !== 'undefined' && Boolean(document.documentElement.requestFullscreen);

  const toggleFullscreen = () => {
    if (!fullscreenSupported) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => undefined);
    } else {
      void document.documentElement.requestFullscreen().catch(() => undefined);
    }
  };

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
      <div className="h-px w-full bg-border" />
      <ControlButton label="Find my location" testId="geolocate-btn" onClick={ geolocate }>
        <LocateFixed className="size-5" strokeWidth={ 1.75 } />
      </ControlButton>
      { fullscreenSupported && (
        <>
          <div className="h-px w-full bg-border" />
          <ControlButton
            label={ isFullscreen ? 'Exit full screen' : 'Enter full screen' }
            testId="fullscreen-btn"
            onClick={ toggleFullscreen }
          >
            { isFullscreen ? (
              <Minimize className="size-5" strokeWidth={ 1.75 } />
            ) : (
              <Maximize className="size-5" strokeWidth={ 1.75 } />
            ) }
          </ControlButton>
        </>
      ) }
    </div>
  );
}
