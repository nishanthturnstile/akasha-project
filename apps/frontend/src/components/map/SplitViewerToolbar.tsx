import { Cloud, Square } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { CloudMaskOptions, RenderProfileName, Source } from '@/types/api';

interface SplitViewerToolbarProps {
  side: 'left' | 'right';
  sources: Source[] | undefined;
  sourceId: string | undefined;
  onSourceChange: (sourceId: string) => void;
  indices: string[];
  index: string;
  onIndexChange: (index: string) => void;
  cloudMask: CloudMaskOptions;
  onCloudMaskChange: (mask: CloudMaskOptions) => void;
  renderProfile: RenderProfileName;
  onRenderProfileChange: (profile: RenderProfileName) => void;
  contrastAvailable: boolean;
  onSingleView?: () => void;
}

export function SplitViewerToolbar({
  side,
  sources,
  sourceId,
  onSourceChange,
  indices,
  index,
  onIndexChange,
  cloudMask,
  onCloudMaskChange,
  renderProfile,
  onRenderProfileChange,
  contrastAvailable,
  onSingleView,
}: SplitViewerToolbarProps) {
  const sourceOptions = sources?.filter((source) => (source.supportedIndices?.length ?? 0) > 0) ?? [];
  const sideLabel = side === 'left' ? 'Left' : 'Right';

  return (
    <div
      className="glass pointer-events-auto flex max-w-[calc(100%-1rem)] items-center gap-1 rounded-md p-1 shadow-e2"
      data-testid={ `${side}-viewer-toolbar` }
      aria-label={ `${sideLabel} viewer controls` }
    >
      <label className="min-w-0">
        <span className="sr-only">{ sideLabel } imagery source</span>
        <select
          value={ sourceId ?? '' }
          onChange={ (event) => onSourceChange(event.target.value) }
          aria-label={ `${sideLabel} imagery source` }
          className="h-8 max-w-40 truncate rounded-md border-0 bg-transparent px-2 text-[11px] font-medium text-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
        >
          { sourceOptions.map((source) => (
            <option key={ source.id } value={ source.id }>{ source.label }</option>
          )) }
        </select>
      </label>

      <span aria-hidden="true" className="h-5 w-px bg-border" />

      <label className="min-w-0">
        <span className="sr-only">{ sideLabel } vegetation index</span>
        <select
          value={ index }
          onChange={ (event) => onIndexChange(event.target.value) }
          aria-label={ `${sideLabel} vegetation index` }
          className="h-8 max-w-24 truncate rounded-md border-0 bg-transparent px-2 text-[11px] font-medium text-foreground outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
        >
          { indices.map((option) => <option key={ option } value={ option }>{ option }</option>) }
        </select>
      </label>

      { contrastAvailable && (
        <button
          type="button"
          aria-label={ `${sideLabel} contrast view` }
          aria-pressed={ renderProfile === 'contrast' }
          onClick={ () => onRenderProfileChange(renderProfile === 'contrast' ? 'standard' : 'contrast') }
          className={ cn(
            'h-8 rounded-md px-2 text-[11px] font-medium transition-colors',
            renderProfile === 'contrast' ? 'bg-primary/15 text-primary' : 'text-foreground/75 hover:bg-accent',
          ) }
        >
          { renderProfile === 'contrast' ? 'Contrast' : 'Standard' }
        </button>
      ) }

      <details className="group relative">
        <summary
          className="flex size-8 cursor-pointer list-none items-center justify-center rounded-md text-foreground/80 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={ `${sideLabel} mask options` }
        >
          <Cloud className="size-4" aria-hidden="true" />
        </summary>
        <div className="absolute bottom-10 right-0 z-popover grid w-44 gap-2 rounded-md border border-border bg-popover p-3 text-xs text-popover-foreground shadow-e2">
          { ([['clouds', 'Clouds'], ['cloudShadows', 'Cloud shadows'], ['cirrus', 'Cirrus']] as const).map(([key, label]) => (
            <label key={ key } className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={ cloudMask[key] }
                onChange={ (event) => onCloudMaskChange({ ...cloudMask, [key]: event.target.checked }) }
              />
              { label }
            </label>
          )) }
        </div>
      </details>

      { onSingleView && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label="Single View"
              data-testid="single-view-toggle"
              onClick={ onSingleView }
              className="flex size-8 items-center justify-center rounded-md bg-primary/15 text-primary hover:bg-primary/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Square className="size-4" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">Single View</TooltipContent>
        </Tooltip>
      ) }
    </div>
  );
}
