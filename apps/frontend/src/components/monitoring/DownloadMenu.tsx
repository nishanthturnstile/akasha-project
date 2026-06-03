import { useState } from 'react';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface DownloadMenuProps {
  hasSelectedField: boolean;
  selectedDate: string | null;
  displayMode: string;
}

const EXPORTS = [
  { id: 'index-tiff', label: 'Index GeoTIFF' },
  { id: 'index-shp', label: 'Index SHP' },
  { id: 'contours-shp', label: 'Contours SHP' },
];

export function DownloadMenu({ hasSelectedField, selectedDate, displayMode }: DownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const disabledReason = !hasSelectedField
    ? 'Select a field to download map outputs.'
    : !selectedDate
      ? 'Select a scene date to download map outputs.'
      : null;

  return (
    <div className="flex flex-col items-end gap-2" data-testid="download-menu">
      { open && (
        <div className="glass w-56 rounded-md p-3" data-testid="download-menu-panel">
          <p className="mb-2 text-[12px] font-semibold text-foreground">
            { displayMode } · { selectedDate ?? 'No date' }
          </p>
          <div className="flex flex-col gap-1">
            { EXPORTS.map((item) => (
              <button
                key={ item.id }
                type="button"
                disabled
                className="flex items-center justify-between rounded px-2 py-1.5 text-left text-[12px] text-muted-foreground opacity-70"
                data-testid={ `download-${item.id}` }
                title="Available in Phase 6 exports"
              >
                { item.label }
                <span className="text-[10px] uppercase tracking-wide">Phase 6</span>
              </button>
            )) }
          </div>
          { disabledReason && (
            <p className="mt-2 text-[11px] leading-4 text-muted-foreground">{ disabledReason }</p>
          ) }
        </div>
      ) }
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={ open ? 'Close downloads' : 'Open downloads' }
        aria-expanded={ open }
        onClick={ () => setOpen((current) => !current) }
        data-testid="download-menu-toggle"
        title="Downloads"
        className="glass size-9"
      >
        <Download className="size-5" strokeWidth={ 1.75 } />
      </Button>
    </div>
  );
}
