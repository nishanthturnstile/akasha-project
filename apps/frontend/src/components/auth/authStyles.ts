import { cn } from '@/lib/utils';

export const authInputClassName = cn(
  'h-11 rounded-lg border border-input bg-background px-3 text-sm text-foreground shadow-e1',
  'outline-none transition-[border-color,box-shadow,background-color] duration-fast',
  'placeholder:text-muted-foreground hover:border-primary/35',
  'focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25',
  'disabled:cursor-not-allowed disabled:bg-muted/60 disabled:text-muted-foreground',
);
