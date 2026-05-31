import { AlertTriangle, RefreshCw } from 'lucide-react';
import type { SceneDate } from '@/types/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { CloudUsabilityChip } from './CloudUsabilityChip';
import { cn } from '@/lib/utils';

interface DateListProps {
  dates: SceneDate[] | undefined;
  selectedDate: string | null;
  onSelect: (acquisitionDate: string) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

function LoadingRows() {
  return (
    <div className="flex flex-col gap-1.5" data-testid="date-list-loading">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function DateList({
  dates,
  selectedDate,
  onSelect,
  loading,
  error,
  onRetry,
}: DateListProps) {
  if (loading) return <LoadingRows />;

  if (error) {
    return (
      <div
        className="flex flex-col items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3"
        data-testid="date-list-error"
      >
        <div className="flex items-center gap-2 text-[13px] text-destructive">
          <AlertTriangle className="size-4" strokeWidth={1.75} />
          <span>{error}</span>
        </div>
        <Button variant="outline" size="sm" onClick={onRetry} data-testid="date-list-retry">
          <RefreshCw className="size-4" strokeWidth={1.75} /> Retry
        </Button>
      </div>
    );
  }

  if (!dates || dates.length === 0) {
    return (
      <p className="px-1 py-2 text-[13px] text-muted-foreground" data-testid="date-list-empty">
        No acquisition dates available for this source.
      </p>
    );
  }

  return (
    <ScrollArea className="max-h-56 pr-2" data-testid="date-list">
      <div className="flex flex-col gap-1.5">
        {dates.map((d) => {
          const selected = d.acquisitionDate === selectedDate;
          const disabled = !d.tileAvailable;
          return (
            <button
              key={d.acquisitionDate}
              type="button"
              disabled={disabled}
              aria-current={selected}
              data-testid={`date-row-${d.acquisitionDate}`}
              data-selected={selected}
              onClick={() => onSelect(d.acquisitionDate)}
              className={cn(
                'group flex items-center gap-2 rounded-md border px-2.5 py-2 text-left transition-colors duration-fast ease-standard',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selected
                  ? 'border-primary/50 bg-primary/10'
                  : 'border-transparent hover:border-border hover:bg-accent/60',
                disabled && 'cursor-not-allowed opacity-45 hover:border-transparent hover:bg-transparent',
              )}
            >
              <span className="flex items-center gap-1.5">
                {d.isLatestUsable && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        className="size-2 rounded-pill bg-primary"
                        aria-label="Latest usable scene"
                        data-testid={`latest-usable-dot-${d.acquisitionDate}`}
                      />
                    </TooltipTrigger>
                    <TooltipContent>Latest usable scene</TooltipContent>
                  </Tooltip>
                )}
                <span className="font-mono tnum text-[13px] text-foreground">
                  {d.acquisitionDate}
                </span>
              </span>
              <span className="ml-auto">
                <CloudUsabilityChip percent={d.usablePixelPercent} />
              </span>
            </button>
          );
        })}
      </div>
    </ScrollArea>
  );
}
