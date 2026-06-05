import { cn } from '@/lib/utils';

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('scan-sweep rounded-md bg-muted/60', className)}
      aria-hidden="true"
      {...props}
    />
  );
}
