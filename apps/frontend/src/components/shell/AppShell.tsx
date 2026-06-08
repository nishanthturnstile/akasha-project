import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  CalendarRange,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  Satellite,
  UserCircle2,
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useAccountMe, useLogout } from '@/lib/queries';
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

const UTILITY_LABEL = 'Utility';
const RAIL_STATE_KEY = 'akasha.railCollapsed';

function loadRailCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(RAIL_STATE_KEY) === '1';
  } catch {
    return false;
  }
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const account = useAccountMe();
  const logout = useLogout();
  const activeGroupLabel = useMemo(
    () => groupLabelForPath(location.pathname),
    [location.pathname],
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    () => new Set(activeGroupLabel ? [activeGroupLabel] : []),
  );
  const [railCollapsed, setRailCollapsed] = useState<boolean>(() => loadRailCollapsed());

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(RAIL_STATE_KEY, railCollapsed ? '1' : '0');
    } catch {
      // ignore quota / disabled storage
    }
  }, [railCollapsed]);

  const primaryGroups = useMemo(
    () => productNavigation.filter((group) => group.label !== UTILITY_LABEL),
    [],
  );
  const utilityGroup = useMemo(
    () => productNavigation.find((group) => group.label === UTILITY_LABEL),
    [],
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

  const railWidth = railCollapsed ? '3.5rem' : '19rem';

  return (
    <TooltipProvider delayDuration={ 200 }>
      <div
        className="grid h-screen w-screen grid-cols-1 grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_var(--rail-w)] lg:grid-rows-1"
        style={ { '--rail-w': railWidth } as CSSProperties }
        data-testid="product-shell"
        data-rail-collapsed={ railCollapsed ? 'true' : 'false' }
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

        <aside
          className="hidden border-l border-border bg-background/96 lg:flex lg:min-h-0 lg:flex-col"
          data-testid="product-rail"
        >
          {/* Brand row + collapse toggle */ }
          <div
            className={ cn(
              'flex items-center gap-3 border-b border-border/60 px-3 py-4',
              railCollapsed && 'justify-center px-2',
            ) }
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
              <Satellite className="size-5" strokeWidth={ 1.75 } aria-hidden="true" />
            </div>
            { !railCollapsed && (
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-base font-semibold leading-5">Akasha</p>
                <p className="truncate text-[11px] text-muted-foreground">Crop intelligence</p>
              </div>
            ) }
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={ () => setRailCollapsed((v) => !v) }
                  aria-label={ railCollapsed ? 'Expand sidebar' : 'Collapse sidebar' }
                  aria-pressed={ railCollapsed }
                  data-testid="rail-collapse-toggle"
                  className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  { railCollapsed ? (
                    <ChevronsRight className="size-4" strokeWidth={ 1.75 } />
                  ) : (
                    <ChevronsLeft className="size-4" strokeWidth={ 1.75 } />
                  ) }
                </button>
              </TooltipTrigger>
              <TooltipContent side="left">
                { railCollapsed ? 'Expand' : 'Collapse' }
              </TooltipContent>
            </Tooltip>
          </div>

          {/* Season selector placeholder for the product rail. */ }
          <div className={ cn('px-3 py-2', railCollapsed && 'px-2') }>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  disabled
                  data-testid="season-selector"
                  aria-label="Season selector (coming soon)"
                  className={ cn(
                    'flex w-full items-center gap-2 rounded-md border border-dashed border-border/60 px-2 py-2 text-left text-[12px] text-muted-foreground transition-colors duration-fast hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-70',
                    railCollapsed && 'justify-center px-0',
                  ) }
                >
                  <CalendarRange className="size-4 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" />
                  { !railCollapsed && (
                    <span className="min-w-0 flex-1 truncate">
                      Season · <span className="text-foreground/70">All seasons</span>
                    </span>
                  ) }
                  { !railCollapsed && (
                    <ChevronDown
                      className="size-3.5 text-muted-foreground"
                      strokeWidth={ 1.75 }
                      aria-hidden="true"
                    />
                  ) }
                </button>
              </TooltipTrigger>
              <TooltipContent side="left">Season filter (coming soon)</TooltipContent>
            </Tooltip>
          </div>

          <Separator />

          {/* Primary product nav (scrollable) */ }
          <ScrollArea className="min-h-0 flex-1">
            <nav
              aria-label="Product modules"
              className={ cn('flex flex-col gap-2 px-3 py-3', railCollapsed && 'px-1') }
            >
              { primaryGroups.map((group) => {
                const slug = slugFor(group.label);
                const isExpanded = expandedGroups.has(group.label);
                const panelId = `nav-group-panel-${slug}`;
                if (railCollapsed) {
                  // Collapsed rail: render every item as an icon-only NavLink (no group headers).
                  return (
                    <section
                      key={ group.label }
                      aria-labelledby={ `nav-group-${slug}` }
                      className="flex flex-col gap-1 border-b border-border/40 pb-2 last:border-b-0"
                    >
                      <h2 id={ `nav-group-${slug}` } className="sr-only">
                        { group.label }
                      </h2>
                      { group.items.map((item) => {
                        const Icon = item.icon;
                        return (
                          <Tooltip key={ item.path }>
                            <TooltipTrigger asChild>
                              <NavLink
                                to={ item.path }
                                data-testid={ testIdFor(item.label) }
                                aria-label={ item.label }
                                className={ ({ isActive }) =>
                                  cn(
                                    'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                    isActive && 'bg-primary/15 text-foreground shadow-e1',
                                  )
                                }
                              >
                                <Icon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                              </NavLink>
                            </TooltipTrigger>
                            <TooltipContent side="left">
                              { item.label }
                              { item.status === 'planned' && (
                                <span className="ml-1 text-[10px] uppercase text-muted-foreground">
                                  · planned
                                </span>
                              ) }
                            </TooltipContent>
                          </Tooltip>
                        );
                      }) }
                    </section>
                  );
                }
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

          {/* Utility footer (pinned). Icon-only when collapsed; flat list otherwise. */ }
          { utilityGroup && (
            <>
              <Separator />
              <nav
                aria-label="Utility"
                className={ cn(
                  'flex flex-col gap-1 px-3 py-3',
                  railCollapsed && 'items-center px-1',
                ) }
                data-testid="utility-footer"
              >
                { utilityGroup.items.map((item) => {
                  const Icon = item.icon;
                  if (railCollapsed) {
                    return (
                      <Tooltip key={ item.path }>
                        <TooltipTrigger asChild>
                          <NavLink
                            to={ item.path }
                            data-testid={ testIdFor(item.label) }
                            aria-label={ item.label }
                            className={ ({ isActive }) =>
                              cn(
                                'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                isActive && 'bg-primary/15 text-foreground shadow-e1',
                              )
                            }
                          >
                            <Icon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                          </NavLink>
                        </TooltipTrigger>
                        <TooltipContent side="left">{ item.label }</TooltipContent>
                      </Tooltip>
                    );
                  }
                  return (
                    <NavLink
                      key={ item.path }
                      to={ item.path }
                      data-testid={ testIdFor(item.label) }
                      className={ ({ isActive }) =>
                        cn(
                          'group flex items-center gap-3 rounded-md px-2.5 py-2 text-[12px] text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                          isActive && 'bg-primary/15 text-foreground shadow-e1',
                        )
                      }
                    >
                      <Icon
                        className="size-4 shrink-0"
                        strokeWidth={ 1.75 }
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 truncate">{ item.label }</span>
                    </NavLink>
                  );
                }) }
                {/* Account / team controls */ }
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={ () =>
                        logout.mutate(undefined, {
                          onSettled: () => navigate('/login', { replace: true }),
                        })
                      }
                      data-testid="account-popover-trigger"
                      aria-label="Sign out"
                      className={ cn(
                        'mt-1 flex items-center gap-2 rounded-md border border-border/60 px-2 py-2 text-[12px] text-muted-foreground transition-colors duration-fast hover:bg-accent/40 hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-70',
                        railCollapsed ? 'size-9 justify-center px-0 py-0' : 'w-full',
                      ) }
                      disabled={ logout.isPending }
                    >
                      { railCollapsed ? (
                        <LogOut className="size-4 shrink-0 text-primary" strokeWidth={ 1.75 } />
                      ) : (
                        <UserCircle2
                          className="size-5 shrink-0 text-primary"
                          strokeWidth={ 1.5 }
                          aria-hidden="true"
                        />
                      ) }
                      { !railCollapsed && (
                        <span className="min-w-0 flex-1 truncate text-left">
                          <span className="block truncate text-[12px] text-foreground/90">
                            { account.data?.user?.displayName ?? 'Akasha user' }
                          </span>
                          <span className="block truncate text-[10px] uppercase tracking-wide text-muted-foreground">
                            { account.data?.currentTeam?.name ?? 'Workspace' }
                          </span>
                        </span>
                      ) }
                      { !railCollapsed && <LogOut className="size-4 shrink-0" strokeWidth={ 1.75 } /> }
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="left">Sign out</TooltipContent>
                </Tooltip>
              </nav>
            </>
          ) }
        </aside>
      </div>
    </TooltipProvider>
  );
}
