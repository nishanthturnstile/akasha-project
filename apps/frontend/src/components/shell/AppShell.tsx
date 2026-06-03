import { NavLink, Outlet } from 'react-router-dom';
import { Satellite } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { MAIN_MONITORING_ROUTE, productNavigation } from '@/routes/productNavigation';

function testIdFor(label: string): string {
  return `nav-link-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

export function AppShell() {
  return (
    <div
      className="grid h-screen w-screen grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_19rem] lg:grid-rows-1"
      data-testid="product-shell"
    >
      <header className="border-b border-border bg-background/95 px-3 py-2 backdrop-blur lg:hidden">
        <div className="mb-2 flex items-center justify-between gap-3">
          <NavLink
            to={ MAIN_MONITORING_ROUTE }
            className="flex items-center gap-2 rounded-md px-1 py-1 text-foreground"
            aria-label="Open Akasha monitoring"
          >
            <Satellite className="size-5 text-primary" strokeWidth={ 1.75 } aria-hidden="true" />
            <span className="font-display text-base font-semibold">Akasha</span>
          </NavLink>
        </div>
        <nav aria-label="Product modules" className="-mx-1 overflow-x-auto px-1">
          <div className="flex min-w-max gap-1 pb-1">
            { productNavigation.flatMap((group) =>
              group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={ item.path }
                    to={ item.path }
                    data-testid={ `mobile-${testIdFor(item.label)}` }
                    className={({ isActive }) =>
                      cn(
                        'flex h-9 items-center gap-2 rounded-md px-3 text-[12px] font-medium text-muted-foreground transition-colors duration-fast',
                        isActive && 'bg-primary/15 text-foreground shadow-e1',
                      )
                    }
                  >
                    <Icon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                    { item.label }
                  </NavLink>
                );
              }),
            ) }
          </div>
        </nav>
      </header>

      <section className="relative min-h-0 min-w-0 overflow-hidden" data-testid="shell-content">
        <Outlet />
      </section>

      <aside className="hidden border-l border-border bg-background/96 lg:flex lg:min-h-0 lg:flex-col">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex size-10 items-center justify-center rounded-md bg-primary/15 text-primary">
            <Satellite className="size-5" strokeWidth={ 1.75 } aria-hidden="true" />
          </div>
          <div>
            <p className="font-display text-lg font-semibold leading-5">Akasha</p>
            <p className="text-[12px] text-muted-foreground">Crop intelligence</p>
          </div>
        </div>
        <Separator />
        <ScrollArea className="min-h-0 flex-1">
          <nav aria-label="Product modules" className="flex flex-col gap-5 px-3 py-4">
            { productNavigation.map((group) => (
              <section key={ group.label } aria-labelledby={ `nav-group-${testIdFor(group.label)}` }>
                <h2
                  id={ `nav-group-${testIdFor(group.label)}` }
                  className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  { group.label }
                </h2>
                <div className="flex flex-col gap-1">
                  { group.items.map((item) => {
                    const Icon = item.icon;
                    return (
                      <NavLink
                        key={ item.path }
                        to={ item.path }
                        data-testid={ testIdFor(item.label) }
                        className={({ isActive }) =>
                          cn(
                            'group flex items-center gap-3 rounded-md px-2.5 py-2 text-[13px] text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                            isActive && 'bg-primary/15 text-foreground shadow-e1',
                          )
                        }
                      >
                        <Icon
                          className="size-4 shrink-0 text-muted-foreground group-hover:text-accent-foreground"
                          strokeWidth={ 1.75 }
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1 truncate">{ item.label }</span>
                        { item.status === 'planned' && (
                          <span className="rounded-sm bg-secondary px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                            Planned
                          </span>
                        ) }
                      </NavLink>
                    );
                  }) }
                </div>
              </section>
            )) }
          </nav>
        </ScrollArea>
      </aside>
    </div>
  );
}
