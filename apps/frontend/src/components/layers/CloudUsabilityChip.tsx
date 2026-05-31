import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { USABILITY_LABEL, usabilityStatus } from '@/lib/usability';
import { cn } from '@/lib/utils';

interface CloudUsabilityChipProps {
  percent: number | null | undefined;
  className?: string;
}

/**
 * The most-repeated "time is first-class" signal. Colour + label + dot (never colour
 * alone) per design-system §2.3 / §5.6.
 */
export function CloudUsabilityChip({ percent, className }: CloudUsabilityChipProps) {
  const status = usabilityStatus(percent);
  const text =
    percent == null || Number.isNaN(percent)
      ? USABILITY_LABEL.nodata
      : `${Math.round(percent)}% usable`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={status}
          className={cn('cursor-default', className)}
          data-testid="cloud-usability-chip"
          data-status={status}
        >
          <span className="size-1.5 rounded-pill bg-current opacity-90" aria-hidden="true" />
          <span className="font-mono tnum">{text}</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        Share of usable pixels after cloud masking. Scenes at or above 70% are considered
        usable.
      </TooltipContent>
    </Tooltip>
  );
}
