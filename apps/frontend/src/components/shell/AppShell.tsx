import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  CalendarRange,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  Plus,
  Satellite,
  UserCircle2,
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import CreateSeasonDialog from '@/components/seasons/CreateSeasonDialog';
import { cn } from '@/lib/utils';
import { queryClient } from '@/lib/queryClient';
import { useAccountMe, useLogout, useSeasons, useDeleteSeason, useUpdateSeason, useFields } from '@/lib/queries';
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
  const [createSeasonOpen, setCreateSeasonOpen] = useState(false);
  const [seasonDropdownOpen, setSeasonDropdownOpen] = useState(false);
  const [seasonTab, setSeasonTab] = useState<'active' | 'planned' | 'ended'>('active');
  const [editingSeasonId, setEditingSeasonId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editStartDate, setEditStartDate] = useState('');
  const [editEndDate, setEditEndDate] = useState('');

  const seasonsQ = useSeasons();
  const deleteSeason = useDeleteSeason();
  const updateSeason = useUpdateSeason();
  const fieldsQ = useFields();

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
      <CreateSeasonDialog open={ createSeasonOpen } onOpenChange={ setCreateSeasonOpen } />
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

          {/* Season selector dropdown for the product rail. */ }
          <div className={ cn('relative px-3 py-2', railCollapsed && 'px-2') }>
            <button
              type="button"
              data-testid="season-selector"
              aria-label="Season selector"
              onClick={ () => setSeasonDropdownOpen((open) => !open) }
              className={ cn(
                'flex w-full items-center gap-2 rounded-md border border-border/60 px-2 py-2 text-left text-[12px] transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                seasonDropdownOpen && 'border-primary bg-primary/10 text-foreground',
                !seasonDropdownOpen && 'text-muted-foreground hover:bg-accent/40',
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
                  className={ cn(
                    'size-3.5 transition-transform duration-fast',
                    seasonDropdownOpen && 'rotate-180',
                  ) }
                  strokeWidth={ 1.75 }
                  aria-hidden="true"
                />
              ) }
            </button>

            { seasonDropdownOpen && !railCollapsed && (
              <div className="absolute left-0 right-0 z-40 mt-2 w-full rounded-xl border border-border bg-background shadow-e2">
                <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">Active season now</p>
                    <p className="text-xs text-muted-foreground">Create or switch seasons from the selector.</p>
                  </div>
                  <Button variant="primary" size="sm" className="gap-2" onClick={ () => setCreateSeasonOpen(true) }>
                    <Plus className="size-3" aria-hidden="true" />
                    Create season
                  </Button>
                </div>

                <div className="flex items-center gap-2 border-b border-border/60 px-4 py-3">
                  {(['active', 'planned', 'ended'] as const).map((tab) => (
                    <button
                      key={ tab }
                      type="button"
                      onClick={ () => setSeasonTab(tab) }
                      className={ cn(
                        'rounded-full px-3 py-1 text-[12px] font-medium transition-colors duration-fast',
                        seasonTab === tab
                          ? 'bg-primary text-primary-foreground'
                          : 'border border-border bg-card text-foreground hover:bg-accent/40',
                      ) }
                    >
                      { tab === 'active' ? 'Active' : tab === 'planned' ? 'Planned' : 'Ended' }
                    </button>
                  )) }
                </div>

                <div className="space-y-3 px-4 py-4">
                  { seasonsQ.isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading seasons…</p>
                  ) : seasonsQ.error ? (
                    <p className="text-sm text-destructive">Failed to load seasons</p>
                  ) : (seasonsQ.data ?? []).length === 0 ? (
                    <Card className="border-border/60 bg-card/90 shadow-sm">
                      <CardContent>
                        <p className="text-sm font-medium text-foreground">
                          There are no { seasonTab === 'planned' ? 'planned' : seasonTab === 'ended' ? 'ended' : 'active' } seasons.
                        </p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          Create a new season to manage your crop schedule.
                        </p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-3">
                      {(seasonsQ.data ?? []).map((season) => {
                        const seasonFields = (fieldsQ.data ?? []).filter((f) =>
                          f.seasonIds?.includes(season.id),
                        );
                        const isEditing = editingSeasonId === season.id;
                        return (
                          <Card key={season.id} className="border-border/60 bg-card/90 shadow-sm">
                            <CardHeader>
                              {isEditing ? (
                                <div className="space-y-2">
                                  <input
                                    className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                  />
                                  <div className="flex gap-2">
                                    <input
                                      type="date"
                                      className="rounded-md border border-border bg-background px-2 py-1 text-xs"
                                      value={editStartDate}
                                      onChange={(e) => setEditStartDate(e.target.value)}
                                    />
                                    <input
                                      type="date"
                                      className="rounded-md border border-border bg-background px-2 py-1 text-xs"
                                      value={editEndDate}
                                      onChange={(e) => setEditEndDate(e.target.value)}
                                    />
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <CardTitle>{season.name}</CardTitle>
                                  <p className="text-sm text-muted-foreground">
                                    {season.startDate ?? '—'} → {season.endDate ?? '—'}
                                  </p>
                                </>
                              )}
                            </CardHeader>
                            <CardContent className="pt-0">
                              <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
                                <span>Fields:</span>
                                <span className="text-foreground font-semibold">
                                  {seasonFields.length}
                                </span>
                              </div>
                              {seasonFields.length > 0 && (
                                <ul className="mt-1 space-y-0.5">
                                  {seasonFields.map((f) => (
                                    <li key={f.id} className="text-xs text-muted-foreground">
                                      · {f.name}
                                    </li>
                                  ))}
                                </ul>
                              )}
                              <div className="mt-3 flex flex-wrap gap-2">
                                {isEditing ? (
                                  <>
                                    <button
                                      type="button"
                                      className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent/40"
                                      onClick={async () => {
                                        await updateSeason.mutateAsync({
                                          seasonId: season.id,
                                          payload: {
                                            name: editName,
                                            startDate: editStartDate || null,
                                            endDate: editEndDate || null,
                                          },
                                        });
                                        setEditingSeasonId(null);
                                      }}
                                    >
                                      Save
                                    </button>
                                    <button
                                      type="button"
                                      className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent/40"
                                      onClick={() => setEditingSeasonId(null)}
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    <button
                                      type="button"
                                      className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent/40"
                                      onClick={() => {
                                        setEditingSeasonId(season.id);
                                        setEditName(season.name);
                                        setEditStartDate(season.startDate ?? '');
                                        setEditEndDate(season.endDate ?? '');
                                      }}
                                    >
                                      Edit
                                    </button>
                                    <button
                                      type="button"
                                      className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent/40"
                                      onClick={async () => {
                                        if (window.confirm('Delete this season?')) {
                                          await deleteSeason.mutateAsync(season.id);
                                        }
                                      }}
                                    >
                                      Delete
                                    </button>
                                  </>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ) }
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
                      onClick={ async () => {
                        // Fully await the server logout so the request completes
                        // before we tear down the page. Navigating/clearing while
                        // the POST is in flight aborts it. Logout is best-effort:
                        // clear local session state and leave even if it fails.
                        try {
                          await logout.mutateAsync();
                        } catch {
                          // Ignore: the session cookie is cleared server-side and
                          // local state is dropped below regardless.
                        }
                        queryClient.clear();
                        navigate('/login', { replace: true });
                      } }
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
