import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import { SplitViewerToolbar } from '@/components/map/SplitViewerToolbar';
import type { Source } from '@/types/api';

const sources = [
  { id: 'sentinel-2-l2a', label: 'Sentinel-2 L2A', supportedIndices: ['NDVI', 'NDMI'] },
  { id: 'landsat-8-l2', label: 'Landsat 8', supportedIndices: ['NDVI'] },
] as Source[];

describe('SplitViewerToolbar', () => {
  it('keeps source, index, render profile, masks, and single-view action independent', () => {
    const onSourceChange = vi.fn();
    const onIndexChange = vi.fn();
    const onRenderProfileChange = vi.fn();
    const onCloudMaskChange = vi.fn();
    const onSingleView = vi.fn();

    render(
      <TooltipProvider>
        <SplitViewerToolbar
          side="left"
          sources={ sources }
          sourceId="sentinel-2-l2a"
          onSourceChange={ onSourceChange }
          indices={ ['NDVI', 'NDMI'] }
          index="NDVI"
          onIndexChange={ onIndexChange }
          cloudMask={ { clouds: true, cloudShadows: true, cirrus: true } }
          onCloudMaskChange={ onCloudMaskChange }
          renderProfile="standard"
          onRenderProfileChange={ onRenderProfileChange }
          contrastAvailable
          onSingleView={ onSingleView }
        />
      </TooltipProvider>,
    );

    fireEvent.change(screen.getByLabelText('Left imagery source'), { target: { value: 'landsat-8-l2' } });
    fireEvent.change(screen.getByLabelText('Left vegetation index'), { target: { value: 'NDMI' } });
    fireEvent.click(screen.getByRole('button', { name: 'Left contrast view' }));
    fireEvent.click(screen.getByLabelText('Left mask options'));
    fireEvent.click(screen.getByLabelText('Cirrus'));
    fireEvent.click(screen.getByRole('button', { name: 'Single View' }));

    expect(onSourceChange).toHaveBeenCalledWith('landsat-8-l2');
    expect(onIndexChange).toHaveBeenCalledWith('NDMI');
    expect(onRenderProfileChange).toHaveBeenCalledWith('contrast');
    expect(onCloudMaskChange).toHaveBeenCalledWith({ clouds: true, cloudShadows: true, cirrus: false });
    expect(onSingleView).toHaveBeenCalledTimes(1);
  });
});
