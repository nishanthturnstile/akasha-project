import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GeometryPreview } from '@/lib/geometry-preview';
import { geometryToSvg } from '@/lib/geometry-preview-utils';
import type { PlotGeometry } from '@/types/api';

const geometry: PlotGeometry = {
  type: 'Polygon',
  coordinates: [[
    [77.1, 13.1],
    [77.4, 13.15],
    [77.35, 13.4],
    [77.08, 13.3],
    [77.1, 13.1],
  ]],
};

describe('GeometryPreview', () => {
  it('keeps the exact boundary coordinates in the generated path', () => {
    const result = geometryToSvg(geometry);
    expect(result.paths[0].d).toContain('M77.1,13.1');
    expect(result.paths[0].d).toContain('L77.4,13.15');
  });

  it('uses visible theme-aware fill and outline classes', () => {
    render(<GeometryPreview geometry={ geometry } />);
    const preview = screen.getByRole('img', { name: 'Field geometry preview' });
    const path = preview.querySelector('path');
    expect(path?.getAttribute('class')).toContain('fill-primary/15');
    expect(path?.getAttribute('class')).toContain('stroke-interactive');
    expect(path?.getAttribute('vector-effect')).toBe('non-scaling-stroke');
  });
});
