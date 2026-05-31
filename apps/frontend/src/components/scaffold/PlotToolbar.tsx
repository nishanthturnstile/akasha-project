import { Download, Pencil, Spline, Trash2, Upload } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const TOOLS = [
  { icon: Pencil, label: 'Draw plot' },
  { icon: Spline, label: 'Edit plot' },
  { icon: Upload, label: 'Import GeoJSON' },
  { icon: Download, label: 'Export GeoJSON' },
  { icon: Trash2, label: 'Delete plot' },
] as const;

/**
 * Phase 5 placeholder. Reserves the top-left anchor with disabled glass affordances
 * so the Terra Draw toolbar can drop in later. No behaviour is implemented.
 */
export function PlotToolbar() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className="glass flex items-center gap-0.5 rounded-md p-1"
          data-testid="plot-toolbar"
          aria-label="Plot tools (available in Phase 5)"
        >
          {TOOLS.map(({ icon: Icon, label }) => (
            <span
              key={label}
              aria-label={label}
              className="flex size-9 cursor-not-allowed items-center justify-center rounded-md text-muted-foreground/50"
            >
              <Icon className="size-[18px]" strokeWidth={1.75} />
            </span>
          ))}
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom">Plot drawing &amp; import/export arrive in Phase 5.</TooltipContent>
    </Tooltip>
  );
}
