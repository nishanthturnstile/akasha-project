import type { PlotGeometry } from '@/types/api';
import { geometryToSvg } from '@/lib/geometry-preview-utils';

/**
 * Converts a PlotGeometry into SVG viewBox + path data for a simple
 * polygon preview. Handles Polygon and MultiPolygon.
 */
interface GeometryPreviewProps {
  geometry: PlotGeometry;
  className?: string;
  width?: number;
  height?: number;
}

export function GeometryPreview({
  geometry,
  className,
  width = 80,
  height = 80,
}: GeometryPreviewProps) {
  if (!geometry || !geometry.type || !geometry.coordinates) {
    return (
      <div
        className={ `bg-muted ${className ?? ''}` }
        style={{ width, height }}
        aria-label="No geometry available"
      />
    );
  }

  const { viewBox, paths } = geometryToSvg(geometry);

  if (paths.length === 0) {
    return (
      <div
        className={ `bg-muted ${className ?? ''}` }
        style={{ width, height }}
        aria-label="No geometry available"
      />
    );
  }

  return (
    <svg
      viewBox={viewBox}
      width={width}
      height={height}
      className={className}
      aria-label="Field geometry preview"
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect
        x={viewBox.split(' ')[0]}
        y={viewBox.split(' ')[1]}
        width={viewBox.split(' ')[2]}
        height={viewBox.split(' ')[3]}
        className="fill-primary/5"
      />
      {paths.map((p, i) => (
        <path
          key={i}
          d={p.d}
          className="fill-primary/15 stroke-interactive"
          strokeWidth="1.75"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </svg>
  );
}
