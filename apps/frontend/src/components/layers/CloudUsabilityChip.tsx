import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { USABILITY_LABEL, usabilityStatus } from '@/lib/usability';
import { cn } from '@/lib/utils';
import type { SourceKind } from '@/types/api';

interface CloudUsabilityChipProps {
  percent: number | null | undefined;
  coveragePercent?: number | null;
  sourceKind?: SourceKind;
  className?: string;
}

/**
 * The most-repeated "time is first-class" signal. Colour + label + dot (never colour
 * alone) per design-system §2.3 / §5.6.
 */
export function CloudUsabilityChip({
  percent,
  coveragePercent,
  sourceKind,
  className,
}: CloudUsabilityChipProps) {
  if (sourceKind === 'sar') {
    const hasCoverage = coveragePercent != null && !Number.isNaN(coveragePercent);
    const status = hasCoverage ? 'info' : 'nodata';
    const text = hasCoverage ? `${Math.round(coveragePercent)}% coverage` : 'Radar pass';

    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant={status}
            className={cn('cursor-default', className)}
            data-testid="radar-coverage-chip"
            data-status={status}
          >
            <span className="size-1.5 rounded-pill bg-current opacity-90" aria-hidden="true" />
            <span className="font-mono tnum">{text}</span>
          </Badge>
        </TooltipTrigger>
        <TooltipContent>Radar acquisition pass. Coverage is footprint-based when available.</TooltipContent>
      </Tooltip>
    );
  }

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
