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
import {
  SheetRoot,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import CreateSeasonDialog from '@/components/seasons/CreateSeasonDialog';
import EditSeasonDialog from '@/components/seasons/EditSeasonDialog';
import GlobalViewPanel, { getLastFieldPerSeason } from '@/components/fields/GlobalViewPanel';
import { useMapView } from '@/state/useMapView';
import { cn } from '@/lib/utils';
import { queryClient } from '@/lib/queryClient';
import { useAccountMe, useLogout, useSeasons, useDeleteSeason, useUpdateSeason, useFields } from '@/lib/queries';
import { MAIN_MONITORING_ROUTE, productNavigation } from '@/routes/productNavigation';

function formatDate(isoDate: string): string {
  if (!isoDate) return '—';
  const [y, m, d] = isoDate.split('-');
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

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
  const view = useMapView();
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
  const [seasonSheetOpen, setSeasonSheetOpen] = useState(false);
  const [seasonTab, setSeasonTab] = useState<'active' | 'planned' | 'ended'>('active');
  const [editSeasonId, setEditSeasonId] = useState<string | null>(null);
  const [globalViewOpen, setGlobalViewOpen] = useState(true);
  const [deletingSeasonId, setDeletingSeasonId] = useState<string | null>(null);

  const seasonsQ = useSeasons();
  const deleteSeason = useDeleteSeason();
  const updateSeason = useUpdateSeason();
  const fieldsQ = useFields();

  useEffect(() => {
    view.setOverlaysVisible(!globalViewOpen);
  }, [globalViewOpen, view]);

  // Clear persisted field selection on mount (unless deep-linked to a specific field)
  useEffect(() => {
    if (!location.pathname.includes('/field/')) {
      view.clearSelectedPlot();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const sortedSeasons = useMemo(() => {
    const data = seasonsQ.data;
    if (!Array.isArray(data)) return [];
    return [...data].sort(
      (a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime(),
    );
  }, [seasonsQ.data]);

  const filteredSeasons = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return sortedSeasons.filter((s) => {
      if (!s.startDate && !s.endDate) return seasonTab === 'active';
      const start = s.startDate ? new Date(s.startDate) : null;
      const end = s.endDate ? new Date(s.endDate) : null;
      if (seasonTab === 'active') {
        if (start && start > today) return false;
        if (end && end < today) return false;
        return true;
      }
      if (seasonTab === 'planned') {
        return start != null && start > today;
      }
      if (seasonTab === 'ended') {
        return end != null && end < today;
      }
      return true;
    });
  }, [sortedSeasons, seasonTab]);

  const editSeasonTarget = useMemo(
    () => (editSeasonId ? sortedSeasons.find((s) => s.id === editSeasonId) ?? null : null),
    [editSeasonId, sortedSeasons],
  );

  const deletingSeason = useMemo(
    () => (deletingSeasonId ? sortedSeasons.find((s) => s.id === deletingSeasonId) ?? null : null),
    [deletingSeasonId, sortedSeasons],
  );

  const [currentSeasonId, setCurrentSeasonId] = useState<string | null>(null);

  const effectiveSeasonId = currentSeasonId ?? sortedSeasons[0]?.id ?? null;

  const currentSeason = useMemo(
    () => (effectiveSeasonId ? sortedSeasons.find((s) => s.id === effectiveSeasonId) ?? null : null),
    [effectiveSeasonId, sortedSeasons],
  );

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
      <CreateSeasonDialog open={ createSeasonOpen } onOpenChange={ setCreateSeasonOpen } onCreated={ setCurrentSeasonId } />
      { editSeasonTarget && (
        <EditSeasonDialog
          season={ editSeasonTarget }
          allFields={ fieldsQ.data ?? [] }
          open={ !!editSeasonTarget }
          onOpenChange={ () => setEditSeasonId(null) }
          onSave={ (seasonId, payload) => { updateSeason.mutate({ seasonId, payload }); setEditSeasonId(null); } }
        />
      ) }
      <div
        className={ cn(
          'grid h-screen w-screen overflow-hidden bg-background text-foreground lg:grid-rows-1',
          'grid-cols-1 grid-rows-[auto_minmax(0,1fr)]',
          globalViewOpen
            ? 'lg:grid-cols-[minmax(0,1fr)_20rem_var(--rail-w)]'
            : 'lg:grid-cols-[minmax(0,1fr)_var(--rail-w)]',
        ) }
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

        { globalViewOpen && (
          <GlobalViewPanel onClose={ () => setGlobalViewOpen(false) } seasonId={ effectiveSeasonId } />
        ) }

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

          {/* Season selector — opens Sheet with season list */ }
          <div className={ cn('px-3 py-2', railCollapsed && 'px-2') }>
            <button
              type="button"
              data-testid="season-selector"
              aria-label="Season selector"
              onClick={ () => setSeasonSheetOpen(true) }
              className={ cn(
                'flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left text-[12px] transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'border-primary bg-primary/10 text-foreground',
                railCollapsed && 'justify-center px-0',
              ) }
            >
              <CalendarRange className="size-4 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" />
              { !railCollapsed && (
                <span className="min-w-0 flex-1 truncate font-medium">
                  { currentSeason ? currentSeason.name : 'Season' }
                </span>
              ) }
              { !railCollapsed && (
                <span className="shrink-0 pr-1 text-[10px] font-medium text-primary/70 uppercase tracking-wider">
                  View
                </span>
              ) }
            </button>
          </div>

          {/* Sheet: all seasons list */ }
          <SheetRoot open={ seasonSheetOpen } onOpenChange={ setSeasonSheetOpen }>
            <SheetContent side="right" className="flex flex-col max-w-sm">
              <SheetHeader>
                <SheetTitle>Seasons</SheetTitle>
              </SheetHeader>

              <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border/60">
                <div className="flex items-center gap-2">
                  { (['active', 'planned', 'ended'] as const).map((tab) => (
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
                <Button variant="primary" size="sm" className="gap-2 shrink-0" onClick={ () => { setSeasonSheetOpen(false); setCreateSeasonOpen(true); } }>
                  <Plus className="size-3" aria-hidden="true" />
                  Create
                </Button>
              </div>

              <ScrollArea className="min-h-0 flex-1 px-4 py-4">
                <div className="space-y-3 pr-1">
                  { seasonsQ.isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading seasons…</p>
                  ) : seasonsQ.error ? (
                    <p className="text-sm text-destructive">Failed to load seasons</p>
                  ) : filteredSeasons.length === 0 ? (
                    <Card className="border-border/60 bg-card/90 shadow-sm">
                      <CardContent>
                        <p className="text-sm font-medium text-foreground">
                          No { seasonTab } seasons yet
                        </p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          { seasonTab === 'active'
                            ? 'Create a new season to get started.'
                            : seasonTab === 'planned'
                              ? 'Schedule a future season with a start date beyond today.'
                              : 'Seasons with an end date in the past will appear here.' }
                        </p>
                      </CardContent>
                    </Card>
                  ) : (
                    <div className="space-y-3">
                      { filteredSeasons.map((season) => {
                        const seasonFields = (fieldsQ.data ?? []).filter((f) =>
                          f.seasonIds?.includes(season.id),
                        );
                        const isCurrent = effectiveSeasonId === season.id;
                        return (
                          <Card
                            key={ season.id }
                            className={ cn(
                              'border-border/60 bg-card/90 shadow-sm cursor-pointer transition-colors duration-fast',
                              isCurrent && 'border-primary/50 ring-1 ring-primary/20',
                            ) }
                            onClick={ () => {
                              const savedFields = getLastFieldPerSeason();
                              const savedFieldId = savedFields[season.id];
                              const fields = fieldsQ.data ?? [];
                              const savedField = savedFieldId ? fields.find((f) => f.id === savedFieldId && f.seasonIds?.includes(season.id)) : undefined;
                              if (savedField) {
                                view.setSelectedPlotId(savedField.id);
                                view.setFocusNonce(Date.now());
                              } else {
                                view.clearSelectedPlot();
                              }
                              setCurrentSeasonId(season.id);
                              setSeasonSheetOpen(false);
                              setGlobalViewOpen(true);
                            } }
                          >
                            <CardHeader>
                              <div className="flex items-center justify-between gap-2">
                                <CardTitle className={ cn('font-bold', isCurrent && 'text-primary') }>
                                  { season.name }
                                </CardTitle>
                                { isCurrent && (
                                  <span className="text-[10px] font-medium uppercase text-primary tracking-wider">
                                    Active
                                  </span>
                                ) }
                              </div>
                              <div className="mt-2 flex gap-2">
                                <div className="flex-1 rounded-md border border-border/60 bg-background/50 px-2 py-1.5">
                                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Start</p>
                                  <p className="text-xs font-medium text-foreground tnum">
                                    { season.startDate ? formatDate(season.startDate) : '—' }
                                  </p>
                                </div>
                                <div className="flex-1 rounded-md border border-border/60 bg-background/50 px-2 py-1.5">
                                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">End</p>
                                  <p className="text-xs font-medium text-foreground tnum">
                                    { season.endDate ? formatDate(season.endDate) : '—' }
                                  </p>
                                </div>
                              </div>
                            </CardHeader>
                            <CardContent className="border-t border-border/50 pt-3">
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm text-muted-foreground">Fields</span>
                                  <span className="text-base font-bold text-foreground tabular-nums">
                                    { seasonFields.length }
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent/40"
                                    onClick={ (e) => { e.stopPropagation(); setEditSeasonId(season.id); } }
                                  >
                                    Edit
                                  </button>
                                  <button
                                    type="button"
                                    disabled={!season.canDelete}
                                    title={!season.canDelete ? "Cannot delete your only season" : undefined}
                                    className={cn(
                                      "rounded-md border px-3 py-1.5 text-sm",
                                      !season.canDelete
                                        ? "border-dashed text-muted-foreground cursor-not-allowed"
                                        : "border-border text-foreground hover:bg-accent/40"
                                    )}
                                    onClick={ (e) => { e.stopPropagation(); if (season.canDelete) setDeletingSeasonId(season.id); } }
                                  >
                                  Delete
                                </button>
                              </div>
                            </div>
                              {seasonFields.length === 0 && (
                                <button
                                  type="button"
                                  onClick={ (e) => { e.stopPropagation(); setEditSeasonId(season.id); } }
                                  className="mt-2 w-full rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent/40 transition-colors duration-fast"
                                >
                                  + Add field
                                </button>
                              )}
                            </CardContent>
                          </Card>
                        );
                      }) }
                    </div>
                  ) }
                </div>
              </ScrollArea>
            </SheetContent>
          </SheetRoot>

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
                        if (item.label === 'Global view') {
                          return (
                            <Tooltip key={ item.path }>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  onClick={ () => setGlobalViewOpen(true) }
                                  data-testid={ testIdFor(item.label) }
                                  data-active={ globalViewOpen || undefined }
                                  aria-label={ item.label }
                                  className={ cn(
                                    'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                    globalViewOpen && 'bg-primary/15 text-foreground',
                                  ) }
                                >
                                  <Icon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="left">
                                { item.label }
                              </TooltipContent>
                            </Tooltip>
                          );
                        }
                        return (
                          <Tooltip key={ item.path }>
                            <TooltipTrigger asChild>
                              <NavLink
                                to={ item.path }
                                data-testid={ testIdFor(item.label) }
                                aria-label={ item.label }
                                onClick={ () => setGlobalViewOpen(false) }
                                className={ ({ isActive }) =>
                                  cn(
                                    'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                    isActive && !globalViewOpen && 'bg-primary/15 text-foreground shadow-e1',
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
                          if (item.label === 'Global view') {
                            return (
                              <button
                                key={ item.path }
                                type="button"
                                onClick={ () => setGlobalViewOpen(true) }
                                data-testid={ testIdFor(item.label) }
                                data-active={ globalViewOpen || undefined }
                                className={ cn(
                                  'group flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-[13px] text-left transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                  globalViewOpen
                                    ? 'bg-primary/15 text-foreground'
                                    : 'text-muted-foreground',
                                ) }
                              >
                                <Icon
                                  className="size-4 shrink-0"
                                  strokeWidth={ 1.75 }
                                  aria-hidden="true"
                                />
                                <span className="min-w-0 flex-1 truncate">{ item.label }</span>
                              </button>
                            );
                          }
                          return (
                            <NavLink
                              key={ item.path }
                              to={ item.path }
                              data-testid={ testIdFor(item.label) }
                              onClick={ () => setGlobalViewOpen(false) }
                              className={ ({ isActive }) =>
                                cn(
                                  'group flex items-center gap-3 rounded-md px-2.5 py-2 text-[13px] text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                  isActive && !globalViewOpen && 'bg-primary/15 text-foreground shadow-e1',
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

      <AlertDialogRoot open={!!deletingSeasonId} onOpenChange={(open) => { if (!open) setDeletingSeasonId(null); }}>
        <AlertDialogContent>
          <AlertDialogTitle>Delete season?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete "{deletingSeason?.name}"? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={async () => {
              if (!deletingSeasonId) return;
              try {
                await deleteSeason.mutateAsync(deletingSeasonId);
              } catch {
                // error handled by query state
              }
              setDeletingSeasonId(null);
            }}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </TooltipProvider>
  );
}
