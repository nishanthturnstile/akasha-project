import { lazy, Suspense, type ComponentType } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthGate } from '@/components/auth/AuthGate';
import { AppShell } from '@/components/shell/AppShell';
import { NotFoundPage } from '@/components/shell/ModulePlaceholder';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

const FieldAnalyticsPage = lazy(() => import('@/pages/monitoring/FieldAnalyticsPage'));

function lazyPlaceholderPage(name: keyof typeof import('@/pages/product/ProductPlaceholderPages')) {
  return lazy(async () => {
    const module = await import('@/pages/product/ProductPlaceholderPages');
    return { default: module[name] as ComponentType };
  });
}

const MonitoringGlobalView = lazyPlaceholderPage('MonitoringGlobalView');
const FieldLeaderboardPage = lazy(() => import('@/pages/reports/FieldLeaderboardPage'));
const ReportingPage = lazy(() => import('@/pages/reports/ReportingPage'));
const DiseasesPestsPage = lazy(() => import('@/pages/risk/DiseasesPestsPage'));
const WeatherAnalyticsPage = lazyPlaceholderPage('WeatherAnalyticsPage');
const WeatherForecastPage = lazyPlaceholderPage('WeatherForecastPage');
const FieldActivityLogPage = lazy(() => import('@/pages/operations/FieldActivityLogPage'));
const VraSowingPage = lazyPlaceholderPage('VraSowingPage');
const VraVegetationPage = lazyPlaceholderPage('VraVegetationPage');
const VraPkPage = lazyPlaceholderPage('VraPkPage');
const VraMapBuilderPage = lazyPlaceholderPage('VraMapBuilderPage');
const VraSoilSamplingPage = lazyPlaceholderPage('VraSoilSamplingPage');
const ScoutTasksPage = lazy(() => import('@/pages/operations/ScoutTasksPage'));
const DataManagerPage = lazy(() => import('@/pages/data-manager/DataManagerPage'));
const ConnectionsPage = lazy(() => import('@/pages/data-manager/ConnectionsPage'));
const FieldGroupsPage = lazy(() => import('@/pages/field-manager/FieldGroupsPage'));
const AiAssistantPage = lazy(() => import('@/pages/account/AiAssistantPage'));
const NotificationsPage = lazy(() => import('@/pages/account/NotificationsPage'));
const HelpPage = lazyPlaceholderPage('HelpPage');
const MarketplacePage = lazyPlaceholderPage('MarketplacePage');
const AccountSettingsPage = lazy(() => import('@/pages/account/AccountSettingsPage'));
const ApiSettingsPage = lazy(() => import('@/pages/account/ApiSettingsPage'));
const LoginPage = lazy(() => import('@/pages/auth/LoginPage'));

function RouteFallback() {
  return (
    <div className="flex h-full items-center justify-center bg-background" data-testid="route-loading">
      <div className="glass scan-sweep h-20 w-[280px] max-w-[80vw]" />
    </div>
  );
}

function withSuspense(Component: ComponentType) {
  return (
    <Suspense fallback={ <RouteFallback /> }>
      <Component />
    </Suspense>
  );
}

export function ProductRoutes() {
  return (
    <Routes>
      <Route path="login" element={ withSuspense(LoginPage) } />
      <Route element={ <AuthGate><AppShell /></AuthGate> }>
        <Route index element={ <Navigate to={ MAIN_MONITORING_ROUTE } replace /> } />
        <Route path="map" element={ <Navigate to={ MAIN_MONITORING_ROUTE } replace /> } />
        <Route
          path="monitoring/field-analytics"
          element={ withSuspense(FieldAnalyticsPage) }
        />
        <Route
          path="monitoring/field-analytics/field/:plotId"
          element={ withSuspense(FieldAnalyticsPage) }
        />
        <Route path="monitoring/global" element={ withSuspense(MonitoringGlobalView) } />
        <Route path="monitoring/field-leaderboard" element={ withSuspense(FieldLeaderboardPage) } />
        <Route path="monitoring/reporting" element={ withSuspense(ReportingPage) } />
        <Route path="monitoring/diseases-pests" element={ withSuspense(DiseasesPestsPage) } />
        <Route path="weather/analytics" element={ withSuspense(WeatherAnalyticsPage) } />
        <Route path="weather/forecast" element={ withSuspense(WeatherForecastPage) } />
        <Route path="activity-log" element={ withSuspense(FieldActivityLogPage) } />
        <Route path="vra/sowing" element={ withSuspense(VraSowingPage) } />
        <Route path="vra/vegetation" element={ withSuspense(VraVegetationPage) } />
        <Route path="vra/pk" element={ withSuspense(VraPkPage) } />
        <Route path="vra/map-builder" element={ withSuspense(VraMapBuilderPage) } />
        <Route path="vra/soil-sampling" element={ withSuspense(VraSoilSamplingPage) } />
        <Route path="scout-tasks" element={ withSuspense(ScoutTasksPage) } />
        <Route path="data-manager/data" element={ withSuspense(DataManagerPage) } />
        <Route path="data-manager/connections" element={ withSuspense(ConnectionsPage) } />
        <Route path="field-manager/groups" element={ withSuspense(FieldGroupsPage) } />
        <Route path="assistant" element={ withSuspense(AiAssistantPage) } />
        <Route path="notifications" element={ withSuspense(NotificationsPage) } />
        <Route path="help" element={ withSuspense(HelpPage) } />
        <Route path="marketplace" element={ withSuspense(MarketplacePage) } />
        <Route path="account/settings" element={ withSuspense(AccountSettingsPage) } />
        <Route path="account/api" element={ withSuspense(ApiSettingsPage) } />
        <Route path="*" element={ <NotFoundPage /> } />
      </Route>
    </Routes>
  );
}
