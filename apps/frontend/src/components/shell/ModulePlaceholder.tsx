import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BrandLockup } from '@/components/BrandLockup';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

export interface ModulePlaceholderProps {
  className?: string;
  dependency: string;
  moduleName: string;
  summary: string;
}

export function ModulePlaceholder({
  className,
  dependency,
  moduleName,
  summary,
}: ModulePlaceholderProps) {
  return (
    <main
      className={ cn(
        'h-full overflow-auto bg-background px-4 py-5 text-foreground md:px-8 md:py-8',
        className,
      ) }
      data-testid="module-placeholder"
    >
      <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center">
        <section className="glass-card hero-pattern max-w-3xl overflow-hidden p-6 md:p-8">
          <div className="mb-5 flex items-center gap-3">
            <BrandLockup variant="icon" />
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                Product module
              </p>
              <h1 className="font-display text-2xl font-semibold text-foreground md:text-3xl">
                { moduleName }
              </h1>
            </div>
          </div>

          <p className="max-w-2xl text-[14px] leading-6 text-muted-foreground md:text-[15px]">
            { summary }
          </p>
          <p className="mt-4 max-w-2xl text-[13px] leading-5 text-muted-foreground/80">
            { dependency }
          </p>

          <div className="mt-7 flex flex-wrap gap-3">
            <Button asChild variant="primary" size="sm">
              <Link to={ MAIN_MONITORING_ROUTE }>
                Open Monitoring <ArrowRight className="size-4" strokeWidth={ 1.75 } />
              </Link>
            </Button>
          </div>
        </section>
      </div>
    </main>
  );
}

export function NotFoundPage() {
  return (
    <ModulePlaceholder
      moduleName="Route not found"
      summary="This product route is not part of the current Akasha navigation surface."
      dependency="Use the product navigation to return to a supported module."
    />
  );
}
