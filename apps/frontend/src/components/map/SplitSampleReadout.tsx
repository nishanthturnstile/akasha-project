import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type maplibregl from 'maplibre-gl';
import { sampleFieldComparison } from '@/lib/api';
import type { ComparisonSampleResponse, ViewerSelection } from '@/types/api';

interface SplitSampleReadoutProps {
  leftMap: maplibregl.Map | null;
  rightMap: maplibregl.Map | null;
  plotId: string;
  left: ViewerSelection;
  right: ViewerSelection;
  leftLegendLabels?: string[];
  rightLegendLabels?: string[];
}

export function SplitSampleReadout({
  leftMap,
  rightMap,
  plotId,
  left,
  right,
  leftLegendLabels,
  rightLegendLabels,
}: SplitSampleReadoutProps) {
  const selectionKey = [
    left.sourceId,
    left.acquisitionDate,
    left.indexType,
    left.renderProfile,
    right.sourceId,
    right.acquisitionDate,
    right.indexType,
    right.renderProfile,
  ].join('|');
  const [sample, setSample] = useState<{ key: string; value: ComparisonSampleResponse } | null>(null);
  const [hover, setHover] = useState<{
    key: string;
    left: { x: number; y: number };
    right: { x: number; y: number };
  } | null>(null);
  const lastRequest = useRef(0);
  const requestId = useRef(0);

  useEffect(() => {
    if (!leftMap || !rightMap) return;
    requestId.current += 1;
    const markerElement = () => {
      const element = document.createElement('div');
      element.className = 'pointer-events-none absolute z-10 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary shadow-e2';
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
      leftMarker.hidden = false;
      rightMarker.hidden = false;
      setHover({
        key: selectionKey,
        left: { x: leftPixel.x, y: leftPixel.y },
        right: { x: rightPixel.x, y: rightPixel.y },
      });
      if (Date.now() - lastRequest.current < 150) return;
      lastRequest.current = Date.now();
      const id = ++requestId.current;
      void sampleFieldComparison(plotId, point, left, right).then((response) => {
        if (id === requestId.current) setSample({ key: selectionKey, value: response });
      }).catch((reason) => {
        if (id !== requestId.current) return;
        const error = reason instanceof Error ? reason.message : 'Value lookup unavailable';
        setSample({
          key: selectionKey,
          value: {
            left: { status: 'error', value: null, category: null, masked: false, maskClass: null, error },
            right: { status: 'error', value: null, category: null, masked: false, maskClass: null, error },
          },
        });
      });
    };
    const leave = () => {
      requestId.current += 1;
      leftMarker.hidden = true;
      rightMarker.hidden = true;
      setHover(null);
      setSample(null);
    };
    leftMarker.hidden = true;
    rightMarker.hidden = true;
    leftMap.on('mousemove', move);
    rightMap.on('mousemove', move);
    leftMap.on('mouseout', leave);
    rightMap.on('mouseout', leave);
    return () => {
      leftMap.off('mousemove', move);
      rightMap.off('mousemove', move);
      leftMap.off('mouseout', leave);
      rightMap.off('mouseout', leave);
      leftMarker.remove();
      rightMarker.remove();
    };
  }, [left, leftMap, plotId, right, rightMap, selectionKey]);

  if (!hover || hover.key !== selectionKey || !leftMap || !rightMap) return null;
  const currentSample = sample?.key === selectionKey ? sample.value : null;
  const text = (side: ComparisonSampleResponse['left'], legendLabels: string[] | undefined) => {
    if (side.status === 'error') return side.error ?? 'Unavailable';
    if (side.masked) return 'Masked / no data';
    const category = side.category == null
      ? null
      : legendLabels?.[side.category] ?? `Class ${side.category + 1}`;
    return side.value == null
      ? 'No data'
      : `${side.value.toFixed(3)}${category == null ? '' : ` · ${category}`}`;
  };
  const popover = (
    side: 'left' | 'right',
    selection: ViewerSelection,
    position: { x: number; y: number },
    result: ComparisonSampleResponse['left'] | undefined,
    legendLabels: string[] | undefined,
  ) => {
    const container = side === 'left' ? leftMap.getContainer() : rightMap.getContainer();
    const left = Math.min(Math.max(8, position.x + 14), Math.max(8, container.clientWidth - 190));
    const top = Math.min(Math.max(8, position.y + 14), Math.max(8, container.clientHeight - 82));
    return createPortal(
      <div
        className="glass pointer-events-none absolute z-popover min-w-44 rounded-md px-3 py-2 text-xs shadow-e2"
        style={ { left, top } }
        data-testid={ `${side}-sample-popover` }
      >
        <p className="font-semibold text-foreground">{ selection.indexType } · { selection.acquisitionDate }</p>
        <p className="mt-0.5 text-muted-foreground">{ result ? text(result, legendLabels) : 'Reading value…' }</p>
      </div>,
      container,
    );
  };

  return (
    <>
      { popover('left', left, hover.left, currentSample?.left, leftLegendLabels) }
      { popover('right', right, hover.right, currentSample?.right, rightLegendLabels) }
    </>
  );
}
