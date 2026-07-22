import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-pill border px-2 py-0.5 font-sans text-[12px] font-semibold leading-4 transition-colors',
  {
    variants: {
      variant: {
        neutral: 'border-border bg-muted/60 text-muted-foreground',
        success: 'border-success/30 bg-success/15 text-success',
        warning: 'border-warning/30 bg-warning/15 text-warning',
        destructive: 'border-destructive/30 bg-destructive/15 text-destructive',
        info: 'border-info/30 bg-info/15 text-info',
        nodata: 'border-nodata/30 bg-nodata/15 text-nodata',
        outline: 'border-border bg-transparent text-foreground',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
  VariantProps<typeof badgeVariants> {}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <span ref={ ref } className={ cn(badgeVariants({ variant }), className) } { ...props } />
  ),
);
Badge.displayName = 'Badge';
