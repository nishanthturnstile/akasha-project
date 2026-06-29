import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  CalendarRange,
  ChevronDown,
  ChevronsLeft,
  Clock,
  Globe,
  LogOut,
  Menu,
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
import { SeasonProvider } from '@/state/seasonContext';
import { useMapView } from '@/state/useMapView';
import { cn } from '@/lib/utils';
import { queryClient } from '@/lib/queryClient';
import { useAccountMe, useLogout, useSeasons, useDeleteSeason, useUpdateSeason, useFields } from '@/lib/queries';
import {
  MAIN_MONITORING_ROUTE,
  productNavigation,
  type ProductNavGroup,
  type ProductNavItem,
} from '@/routes/productNavigation';

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

function seasonTabFor(season: { startDate: string | null; endDate: string | null }): 'active' | 'planned' | 'ended' {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = season.startDate ? new Date(`${season.startDate}T00:00:00`) : null;
  const end = season.endDate ? new Date(`${season.endDate}T00:00:00`) : null;
  if (!start && !end) return 'active';
  if (start && start > today) return 'planned';
  if (end && end < today) return 'ended';
  return 'active';
}

function testIdFor(label: string): string {
  return `nav-link-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

function slugFor(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function isNavItemVisibleForRole(item: ProductNavItem, role?: string): boolean {
  if (!item.requiredRoles || item.requiredRoles.length === 0) return true;
  return Boolean(role && item.requiredRoles.includes(role));
}

function filterNavigationForRole(groups: ProductNavGroup[], role?: string): ProductNavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => isNavItemVisibleForRole(item, role)),
    }))
    .filter((group) => group.items.length > 0);
}

function groupLabelForPath(pathname: string, groups: ProductNavGroup[]): string | null {
  for (const group of groups) {
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
  const isAdminIngestionRoute = location.pathname.startsWith('/admin/ingestion');
  const view = useMapView();
  const account = useAccountMe();
  const logout = useLogout();
  const currentRole = account.data?.currentTeam?.role;
  const visibleNavigation = useMemo(
    () => filterNavigationForRole(productNavigation, currentRole),
    [currentRole],
  );
  const activeGroupLabel = useMemo(
    () => groupLabelForPath(location.pathname, visibleNavigation),
    [location.pathname, visibleNavigation],
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    () => new Set(activeGroupLabel ? [activeGroupLabel] : []),
  );
  const [railCollapsed, setRailCollapsed] = useState<boolean>(() => loadRailCollapsed());
  const [createSeasonOpen, setCreateSeasonOpen] = useState(false);
  const [seasonSheetOpen, setSeasonSheetOpen] = useState(false);
  const [seasonTab, setSeasonTab] = useState<'active' | 'planned' | 'ended'>('active');
  const [editSeasonId, setEditSeasonId] = useState<string | null>(null);
  const [globalViewOpen, setGlobalViewOpen] = useState(
    !isAdminIngestionRoute && !location.pathname.includes('/field/'),
  );
  const [deletingSeasonId, setDeletingSeasonId] = useState<string | null>(null);
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);

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

  const activeCount = useMemo(
    () => sortedSeasons.filter((s) => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const start = s.startDate ? new Date(`${s.startDate}T00:00:00`) : null;
      const end = s.endDate ? new Date(`${s.endDate}T00:00:00`) : null;
      if (!start && !end) return true;
      if (start && start <= today && (!end || end >= today)) return true;
      if (!start && end && end >= today) return true;
      return false;
    }).length,
    [sortedSeasons],
  );
  const plannedCount = useMemo(
    () => sortedSeasons.filter((s) => {
      if (!s.startDate) return false;
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return new Date(`${s.startDate}T00:00:00`) > today;
    }).length,
    [sortedSeasons],
  );
  const endedCount = useMemo(
    () => sortedSeasons.filter((s) => {
      if (!s.endDate) return false;
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return new Date(`${s.endDate}T00:00:00`) < today;
    }).length,
    [sortedSeasons],
  );

  const filteredSeasons = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return sortedSeasons.filter((s) => {
      const start = s.startDate ? new Date(`${s.startDate}T00:00:00`) : null;
      const end = s.endDate ? new Date(`${s.endDate}T00:00:00`) : null;
      if (seasonTab === 'active') {
        if (!start && !end) return true;
        if (start && start <= today && (!end || end >= today)) return true;
        if (!start && end && end >= today) return true;
        return false;
      }
      if (seasonTab === 'planned') {
        if (!start) return false;
        return start > today;
      }
      if (seasonTab === 'ended') {
        if (!end) return false;
        return end < today;
      }
      return false;
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
  const showGlobalViewPanel = !isAdminIngestionRoute && globalViewOpen;
  const isGlobalViewActive = showGlobalViewPanel;

  const currentSeason = useMemo(
    () => (effectiveSeasonId ? sortedSeasons.find((s) => s.id === effectiveSeasonId) ?? null : null),
    [effectiveSeasonId, sortedSeasons],
  );

  // Auto-select the last-viewed field for the current season on initial load
  useEffect(() => {
    const fields = fieldsQ.data;
    if (!fields || fields.length === 0 || !effectiveSeasonId) return;
    if (view.selectedPlotId) return;

    const savedFields = getLastFieldPerSeason();
    const savedFieldId = savedFields[effectiveSeasonId];
    const savedField = savedFieldId
      ? fields.find((f) => f.id === savedFieldId && f.seasonIds?.includes(effectiveSeasonId))
      : undefined;

    if (savedField) {
      view.setSelectedPlotId(savedField.id);
      view.setFocusNonce(Date.now());
      setTimeout(() => setGlobalViewOpen(false), 0);
    } else {
      const firstField = fields.find((f) => f.seasonIds?.includes(effectiveSeasonId));
      if (firstField) {
        view.setSelectedPlotId(firstField.id);
        view.setFocusNonce(Date.now());
        setTimeout(() => setGlobalViewOpen(false), 0);
      }
    }
  }, [fieldsQ.data, effectiveSeasonId, view.selectedPlotId, view]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(RAIL_STATE_KEY, railCollapsed ? '1' : '0');
    } catch {
      // ignore quota / disabled storage
    }
  }, [railCollapsed]);

  const primaryGroups = useMemo(
    () => visibleNavigation.filter((group) => group.label !== UTILITY_LABEL),
    [visibleNavigation],
  );
  const utilityGroup = useMemo(
    () => visibleNavigation.find((group) => group.label === UTILITY_LABEL),
    [visibleNavigation],
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

  const railWidth = railCollapsed ? '3.5rem' : '16rem';

  return (
    <TooltipProvider delayDuration={ 200 }>
      <CreateSeasonDialog open={ createSeasonOpen } onOpenChange={ setCreateSeasonOpen } onCreated={ (season) => { setCurrentSeasonId(season.id); setSeasonTab(seasonTabFor(season)); setGlobalViewOpen(true); } } />
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
          showGlobalViewPanel
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
              <button
                type="button"
                onClick={ () => { setGlobalViewOpen(true); navigate(MAIN_MONITORING_ROUTE); } }
                data-testid="mobile-nav-link-global-view"
                className={ cn(
                  'flex h-9 items-center gap-2 rounded-md px-3 text-[12px] font-medium text-muted-foreground transition-colors duration-fast',
                  isGlobalViewActive && 'bg-primary/15 text-foreground shadow-e1',
                ) }
              >
                <Globe className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                Global View
              </button>
              { visibleNavigation.flatMap((group) =>
                group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={ item.path }
                      to={ item.path }
                      end={ false }
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
          <SeasonProvider seasonId={ effectiveSeasonId }>
            <Outlet />
          </SeasonProvider>
        </section>

        { showGlobalViewPanel && (
          <GlobalViewPanel key={ effectiveSeasonId ?? 'no-season' } onClose={ () => setGlobalViewOpen(false) } seasonId={ effectiveSeasonId } />
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
            { !railCollapsed && (
              <>
                <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <Satellite className="size-5" strokeWidth={ 1.75 } aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-base font-semibold leading-5">Akasha</p>
                  <p className="truncate text-[11px] text-muted-foreground">Crop intelligence</p>
                </div>
              </>
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
                    <Menu className="size-4" strokeWidth={ 1.75 } />
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
              onClick={ () => { setSeasonSheetOpen(true); if (currentSeason) setSeasonTab(seasonTabFor(currentSeason)); } }
              className={ cn(
                'flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left text-sm transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'border-primary bg-primary/10 text-foreground',
                railCollapsed && 'justify-center px-0',
              ) }
            >
              <CalendarRange className="size-4 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" />
              { !railCollapsed && (
                <span className="min-w-0 flex-1 truncate font-bold text-sm">
                  { currentSeason ? currentSeason.name : 'Season' }
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
                  { (['active', 'planned', 'ended'] as const).map((tab) => {
                    const count = tab === 'active' ? activeCount : tab === 'planned' ? plannedCount : endedCount;
                    return (
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
                        { count > 0 && <span className="ml-1.5 opacity-80">({ count })</span> }
                      </button>
                    );
                  }) }
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
                              'border-border/60 bg-card/90 shadow-sm cursor-pointer transition-colors duration-fast min-h-50',
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
                              setGlobalViewOpen(false);
                              if (savedField) {
                                navigate(`/monitoring/field-analytics/field/${savedField.id}`);
                              } else {
                                navigate('/monitoring/field-analytics');
                              }
                            } }
                          >
                            <CardHeader>
                              <div className="flex items-center justify-between gap-2">
                                <CardTitle className={ cn('font-bold text-lg', isCurrent && 'text-primary') }>
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
                                    disabled={ !season.canDelete }
                                    title={ !season.canDelete ? "Cannot delete your only season" : undefined }
                                    className={ cn(
                                      "rounded-md border px-3 py-1.5 text-sm",
                                      !season.canDelete
                                        ? "border-dashed text-muted-foreground cursor-not-allowed"
                                        : "border-border text-foreground hover:bg-accent/40"
                                    ) }
                                    onClick={ (e) => { e.stopPropagation(); if (season.canDelete) setDeletingSeasonId(season.id); } }
                                  >
                                    Delete
                                  </button>
                                </div>
                              </div>
                              { seasonFields.length === 0 && (
                                <button
                                  type="button"
                                  onClick={ (e) => {
                                    e.stopPropagation();
                                    setCurrentSeasonId(season.id);
                                    setSeasonSheetOpen(false);
                                    setGlobalViewOpen(false);
                                    navigate(`/monitoring/field-create?seasonId=${season.id}`);
                                  } }
                                  className="mt-2 w-full rounded-md border border-dashed border-border px-3 py-2 text-sm text-foreground hover:bg-accent/40 transition-colors duration-fast"
                                >
                                  + Add field
                                </button>
                              ) }
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
              {/* Global View — always visible, toggles the global view panel */ }
              { railCollapsed ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label="Global View"
                      onClick={ () => { setGlobalViewOpen(true); navigate(MAIN_MONITORING_ROUTE); } }
                      className={ cn(
                        'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                        isGlobalViewActive && 'bg-primary/15 text-foreground shadow-e1',
                      ) }
                    >
                      <Globe className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="left">Global View</TooltipContent>
                </Tooltip>
              ) : (
                <button
                  type="button"
                  onClick={ () => { setGlobalViewOpen(true); navigate(MAIN_MONITORING_ROUTE); } }
                  data-testid="nav-link-global-view"
                  className={ cn(
                    'group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                    isGlobalViewActive && 'bg-primary/15 text-foreground shadow-e1',
                  ) }
                >
                  <Globe className="size-4 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate text-left">Global View</span>
                </button>
              ) }
              <Separator className="my-1" />
              { primaryGroups.map((group) => {
                const slug = slugFor(group.label);
                const isExpanded = expandedGroups.has(group.label);
                const panelId = `nav-group-panel-${slug}`;
                if (railCollapsed) {
                  const GroupIcon = group.icon;
                  const isHovered = hoveredGroup === group.label;
                  const panelFlyoutId = `nav-flyout-${slug}`;
                  return (
                    <section
                      key={ group.label }
                      aria-labelledby={ `nav-group-${slug}` }
                      className="relative border-b border-border/40 pb-2 last:border-b-0"
                    >
                      <h2 id={ `nav-group-${slug}` } className="sr-only">
                        { group.label }
                      </h2>
                      <button
                        type="button"
                        aria-label={ group.label }
                        aria-expanded={ isHovered }
                        aria-controls={ panelFlyoutId }
                        data-testid={ `nav-group-btn-${slug}` }
                        onMouseEnter={ () => setHoveredGroup(group.label) }
                        onMouseLeave={ () => setHoveredGroup(null) }
                        className={ cn(
                          'flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                          activeGroupLabel === group.label && 'text-primary',
                        ) }
                      >
                        { GroupIcon && (
                          <GroupIcon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                        ) }
                      </button>
                      { isHovered && (
                        <div
                          id={ panelFlyoutId }
                          role="menu"
                          onMouseEnter={ () => setHoveredGroup(group.label) }
                          onMouseLeave={ () => setHoveredGroup(null) }
                          className="absolute right-full top-0 z-50 ml-3 w-56 rounded-lg border border-border/60 bg-popover p-2 shadow-elevation-high"
                        >
                          <p className="mb-1 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                            { group.label }
                          </p>
                          { group.items.map((item) => {
                            const ItemIcon = item.icon;
                            return (
                              <NavLink
                                key={ item.path }
                                to={ item.path }
                                end={ false }
                                role="menuitem"
                                data-testid={ testIdFor(item.label) }
                                onClick={ () => {
                                  setHoveredGroup(null);
                                  setGlobalViewOpen(false);
                                } }
                                className={ ({ isActive }) =>
                                  cn(
                                    'flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-xs text-center text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                    isActive && !globalViewOpen && 'text-primary font-semibold',
                                  )
                                }
                              >
                                { ItemIcon && (
                                  <ItemIcon className="size-4 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" />
                                ) }
                                <span className="min-w-0 flex-1 truncate">{ item.label }</span>
                                { item.status === 'planned' && (
                                  <Clock className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                                ) }
                              </NavLink>
                            );
                          }) }
                        </div>
                      ) }
                    </section>
                  );
                }
                return (
                  <section
                    key={ group.label }
                    aria-labelledby={ `nav-group-${slug}` }
                  >
                    <h2 id={ `nav-group-${slug}` } className="sr-only">
                      { group.label }
                    </h2>
                    <button
                      type="button"
                      onClick={ () => toggleGroup(group.label) }
                      data-testid={ `nav-group-toggle-${slug}` }
                      aria-expanded={ isExpanded }
                      aria-controls={ panelId }
                      className={ cn(
                        'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                        (isExpanded || activeGroupLabel === group.label) && 'bg-primary/10 text-primary',
                      ) }
                    >
                      <span className="flex items-center gap-2 truncate">
                        { group.icon && <group.icon className="size-3.5 shrink-0" strokeWidth={ 1.75 } aria-hidden="true" /> }
                        <span>{ group.label }</span>
                      </span>
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
                        { group.items.map((item) => (
                          <NavLink
                            key={ item.path }
                            to={ item.path }
                            end={ false }
                            data-testid={ testIdFor(item.label) }
                            onClick={ () => setGlobalViewOpen(false) }
                            className={ ({ isActive }) =>
                              cn(
                                'group flex items-center gap-3 rounded-md px-2.5 py-2 text-xs text-center text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
                                isActive && !globalViewOpen && 'text-primary font-semibold',
                              )
                            }
                          >
                            <span className="min-w-0 flex-1 truncate">{ item.label }</span>
                            { item.status === 'planned' && (
                              <Clock className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                            ) }
                          </NavLink>
                        )) }
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
                            end={ false }
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
                      end={ false }
                      data-testid={ testIdFor(item.label) }
                      className={ ({ isActive }) =>
                        cn(
                          'group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground',
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
                        'mt-1 flex items-center gap-2 rounded-md border border-border/60 px-2 py-2 text-sm text-muted-foreground transition-colors duration-fast hover:bg-accent/40 hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait disabled:opacity-70',
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
                          <span className="block truncate text-sm text-foreground/90">
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

      <AlertDialogRoot open={ !!deletingSeasonId } onOpenChange={ (open) => { if (!open) setDeletingSeasonId(null); } }>
        <AlertDialogContent>
          <AlertDialogTitle>Delete season?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete "{ deletingSeason?.name }"? This action cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={ async () => {
              if (!deletingSeasonId) return;
              try {
                await deleteSeason.mutateAsync(deletingSeasonId);
              } catch {
                // error handled by query state
              }
              setDeletingSeasonId(null);
              window.location.reload();
            } }>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </TooltipProvider>
  );
}
