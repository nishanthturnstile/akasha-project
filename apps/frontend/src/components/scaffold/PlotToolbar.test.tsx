import { fireEvent, render, screen } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import { PlotToolbar } from '@/components/scaffold/PlotToolbar';

function renderToolbar(ui: React.ReactElement) {
  return render(<TooltipProvider>{ ui }</TooltipProvider>);
}

describe('PlotToolbar field actions', () => {
  it('disables selection-only actions until a field is selected', () => {
    renderToolbar(<PlotToolbar />);

    expect((screen.getByTestId('field-toolbar-draw') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('field-toolbar-import') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByTestId('field-toolbar-edit') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('field-toolbar-export') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('field-toolbar-delete') as HTMLButtonElement).disabled).toBe(true);
  });

  it('calls provided action handlers and marks active draw mode', () => {
    const onDraw = vi.fn();
    const onExport = vi.fn();

    renderToolbar(
      <PlotToolbar
        activeAction="draw"
        hasSelectedField
        selectedFieldName="North field"
        onDrawField={ onDraw }
        onExportGeoJSON={ onExport }
      />,
    );

    expect(screen.getByTestId('field-toolbar-draw').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('field-toolbar-draw'));
    fireEvent.click(screen.getByTestId('field-toolbar-export'));

    expect(onDraw).toHaveBeenCalledTimes(1);
    expect(onExport).toHaveBeenCalledTimes(1);
  });
});
