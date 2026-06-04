import { useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { ChevronDown, Satellite } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { MAIN_MONITORING_ROUTE, productNavigation } from '@/routes/productNavigation';

function testIdFor(label: string): string {
  return `nav-link-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

function slugFor(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function groupLabelForPath(pathname: string): string | null {
  for (const group of productNavigation) {
    const matches = group.items.some(
      (item) => pathname === item.path || pathname.startsWith(`${item.path}/`),
    );
    if (matches) {
      return group.label;
    }
  }
  return null;
}

export function AppShell() {
  const location = useLocation();
  const activeGroupLabel = useMemo(
    () => groupLabelForPath(location.pathname),
    [location.pathname],
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    () => new Set(activeGroupLabel ? [activeGroupLabel] : []),
  );

  // Adjust state during render (React-recommended) so the group containing the
  // active route auto-expands when navigation changes the active group.
  const [trackedGroup, setTrackedGroup] = useState(activeGroupLabel);
  if (activeGroupLabel !== trackedGroup) {
    setTrackedGroup(activeGroupLabel);
    if (activeGroupLabel && !expandedGroups.has(activeGroupLabel)) {
      const next = new Set(expandedGroups);
      next.add(activeGroupLabel);
      setExpandedGroups(next);
    }
  }

  const toggleGroup = (label: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

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
                    className={ ({ isActive }) =>
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
          <nav aria-label="Product modules" className="flex flex-col gap-2 px-3 py-4">
            { productNavigation.map((group) => {
              const slug = slugFor(group.label);
              const isExpanded = expandedGroups.has(group.label);
              const panelId = `nav-group-panel-${slug}`;
              return (
                <section key={ group.label } aria-labelledby={ `nav-group-${slug}` }>
                  <h2 id={ `nav-group-${slug}` } className="sr-only">
                    { group.label }
                  </h2>
                  <button
                    type="button"
                    onClick={ () => toggleGroup(group.label) }
                    data-testid={ `nav-group-toggle-${slug}` }
                    aria-expanded={ isExpanded }
                    aria-controls={ panelId }
                    className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground"
                  >
                    <span className="truncate">{ group.label }</span>
                    <ChevronDown
                      className={ cn(
                        'size-4 shrink-0 text-muted-foreground transition-transform duration-fast',
                        isExpanded && 'rotate-180',
                      ) }
                      strokeWidth={ 1.75 }
                      aria-hidden="true"
                    />
                  </button>
                  { isExpanded && (
                    <div id={ panelId } className="mt-1 flex flex-col gap-1">
                      { group.items.map((item) => {
                        const Icon = item.icon;
                        return (
                          <NavLink
                            key={ item.path }
                            to={ item.path }
                            data-testid={ testIdFor(item.label) }
                            className={ ({ isActive }) =>
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
                  ) }
                </section>
              );
            }) }
          </nav>
        </ScrollArea>
      </aside>
    </div>
  );
}
