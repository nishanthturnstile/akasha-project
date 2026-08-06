import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { NdviValueSplit as NdviValueSplitData } from '@/types/api';

interface NdviValueSplitProps {
  valueSplit: NdviValueSplitData;
  selectedDate?: string | null;
}

const CATEGORY_COLOR_CLASSES: Record<string, string> = {
  denseVegetation: 'bg-success',
  moderateVegetation: 'bg-primary/55',
  sparseVegetation: 'bg-warning',
  openSoil: 'bg-destructive',
  cloudiness: 'bg-muted-foreground/30',
};

const FALLBACK_COLOR_CLASS = 'bg-muted-foreground';

function validPercentage(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(Math.max(value, 0), 100);
}

function formatPercentage(value: number): string {
  const normalized = validPercentage(value);
  return normalized % 1 === 0 ? `${normalized.toFixed(0)}%` : `${normalized.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Latest date';
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  const month = date.toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' });
  return `${date.getUTCDate()} ${month}'${String(date.getUTCFullYear()).slice(-2)}`;
}

function barHeight(percentage: number): number {
  const normalized = validPercentage(percentage);
  return normalized === 0 ? 1 : Math.max(3, Number((normalized * 0.78).toFixed(2)));
}

export function NdviValueSplit({ valueSplit, selectedDate }: NdviValueSplitProps) {
  const categories = valueSplit.categories.filter((category) => category && category.label);
  const hasDistribution = categories.some((category) => validPercentage(category.percentage) > 0);

  return (
    <section
      className="flex min-h-0 flex-col rounded-lg border border-border/70 bg-background/40 p-2.5"
      data-testid="ndvi-value-split"
      aria-labelledby="ndvi-value-split-title"
    >
      <div className="flex items-center gap-1.5">
        <h3 id="ndvi-value-split-title" className="text-sm font-semibold text-foreground">
          NDVI values split
        </h3>
        <Info
          className="size-3.5 text-muted-foreground"
          strokeWidth={ 1.75 }
          aria-label="Percent of pixels in each NDVI class"
        />
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground" data-testid="ndvi-value-split-date">
        Date: { formatDate(selectedDate) }
      </p>

      { hasDistribution ? (
        <div className="mt-2 grid min-w-0 gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(130px,0.72fr)] sm:items-center">
          <div
            className="flex h-26 min-w-0 items-end gap-px border-b border-border/80"
            role="img"
            aria-label={ categories
              .map((category) => `${category.label} ${formatPercentage(category.percentage)}`)
              .join(', ') }
            data-testid="ndvi-value-split-bar"
          >
            { categories.map((category) => {
              const percentage = validPercentage(category.percentage);
              const style = {
                height: `${barHeight(percentage)}%`,
              };
              return (
                <div key={ category.id } className="flex h-full min-w-0 flex-1 flex-col justify-end">
                  <span className="mb-1 text-center text-[10px] leading-3 tabular-nums text-muted-foreground">
                    { formatPercentage(percentage) }
                  </span>
                  <span
                    className={ cn(
                      'block w-full shrink-0',
                      CATEGORY_COLOR_CLASSES[category.id] ?? FALLBACK_COLOR_CLASS,
                    ) }
                    style={ style }
                    title={ `${category.label}: ${formatPercentage(percentage)}` }
                    data-testid={ `ndvi-value-split-segment-${category.id}` }
                  />
                </div>
              );
            }) }
          </div>

          <div className="grid min-w-0 grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-1">
            { categories.map((category) => (
              <div
                key={ category.id }
                className="flex min-w-0 items-center gap-1.5"
                data-testid={ `ndvi-value-split-category-${category.id}` }
              >
                <span
                  className={ cn(
                    'size-1.5 shrink-0 rounded-full',
                    CATEGORY_COLOR_CLASSES[category.id] ?? FALLBACK_COLOR_CLASS,
                  ) }
                  aria-hidden="true"
                />
                <span className="truncate text-[11px] text-muted-foreground">
                  { category.label }
                </span>
              </div>
            )) }
          </div>
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-muted-foreground" data-testid="ndvi-value-split-empty">
          No classifiable NDVI pixels for this date.
        </p>
      ) }
    </section>
  );
}