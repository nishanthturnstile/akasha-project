import { useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { sampleFieldComparison } from '@/lib/api';
import type { ComparisonSampleResponse, ViewerSelection } from '@/types/api';

interface SplitSampleReadoutProps {
  leftMap: maplibregl.Map | null;
  rightMap: maplibregl.Map | null;
  plotId: string;
  left: ViewerSelection;
  right: ViewerSelection;
}

export function SplitSampleReadout({ leftMap, rightMap, plotId, left, right }: SplitSampleReadoutProps) {
  const [sample, setSample] = useState<ComparisonSampleResponse | null>(null);
  const lastRequest = useRef(0);
  const requestId = useRef(0);

  useEffect(() => {
    if (!leftMap || !rightMap) return;
    const markerElement = () => {
      const element = document.createElement('div');
      element.className = 'pointer-events-none absolute z-10 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary shadow-e2';
      return element;
    };
    const leftMarker = markerElement();
    const rightMarker = markerElement();
    leftMap.getContainer().appendChild(leftMarker);
    rightMap.getContainer().appendChild(rightMarker);
    const move = (event: maplibregl.MapMouseEvent) => {
      const point = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      const leftPixel = leftMap.project(point);
      const rightPixel = rightMap.project(point);
      leftMarker.style.left = `${leftPixel.x}px`;
      leftMarker.style.top = `${leftPixel.y}px`;
      rightMarker.style.left = `${rightPixel.x}px`;
      rightMarker.style.top = `${rightPixel.y}px`;
      if (Date.now() - lastRequest.current < 150) return;
      lastRequest.current = Date.now();
      const id = ++requestId.current;
      void sampleFieldComparison(plotId, point, left, right).then((response) => {
        if (id === requestId.current) setSample(response);
      }).catch(() => undefined);
    };
    leftMap.on('mousemove', move);
    rightMap.on('mousemove', move);
    return () => {
      leftMap.off('mousemove', move);
      rightMap.off('mousemove', move);
      leftMarker.remove();
      rightMarker.remove();
    };
  }, [left, leftMap, plotId, right, rightMap]);

  if (!sample) return null;
  const text = (side: ComparisonSampleResponse['left']) => {
    if (side.status === 'error') return side.error ?? 'Unavailable';
    if (side.masked) return 'Masked / no data';
    return side.value == null
      ? 'No data'
      : `${side.value.toFixed(3)}${side.category == null ? '' : ` · band ${side.category + 1}`}`;
  };
  return (
    <div className="glass pointer-events-none absolute left-1/2 top-14 z-popover grid -translate-x-1/2 grid-cols-2 gap-4 rounded-md px-3 py-2 text-xs" data-testid="split-sample-readout">
      <span>Left: { text(sample.left) }</span>
      <span>Right: { text(sample.right) }</span>
    </div>
  );
}
