import { Satellite } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface BrandLockupProps {
  className?: string;
  variant?: 'full' | 'compact' | 'icon';
}

/** Shared product endorsement. Internal product and API names remain Akasha. */
export function BrandLockup({ className, variant = 'full' }: BrandLockupProps) {
  return (
    <span
      className={ cn('inline-flex min-w-0 items-center gap-2.5 text-foreground', className) }
      aria-label="Akasha by CIDSA"
      data-testid="brand-lockup"
    >
      <span
        className={ cn(
          'flex shrink-0 items-center justify-center bg-linear-to-br from-cidsa-primary to-cidsa-accent text-white shadow-e1',
          variant === 'full' ? 'size-10 rounded-lg' : 'size-8 rounded-md',
        ) }
        aria-hidden="true"
      >
        <Satellite className={ variant === 'full' ? 'size-5' : 'size-4' } strokeWidth={ 1.8 } />
      </span>

      { variant === 'full' && (
        <span className="min-w-0 leading-none">
          <span className="block truncate font-display text-base font-bold tracking-[-0.02em]">Akasha</span>
          <span className="mt-1 block truncate font-sans text-[10px] font-semibold uppercase tracking-[0.14em] text-primary">
            by CIDSA
          </span>
        </span>
      ) }

      { variant === 'compact' && (
        <span className="truncate font-display text-sm font-bold tracking-[-0.015em]">
          Akasha <span className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-primary">by CIDSA</span>
        </span>
      ) }

      { variant === 'icon' && <span className="sr-only">Akasha by CIDSA</span> }
    </span>
  );
}
