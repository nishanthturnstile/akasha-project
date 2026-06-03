import { ModulePlaceholder, type ModulePlaceholderProps } from '@/components/shell/ModulePlaceholder';

function Placeholder(props: ModulePlaceholderProps) {
  return <ModulePlaceholder { ...props } />;
}

export function MonitoringGlobalView() {
  return (
    <Placeholder
      moduleName="Global view"
      summary="All-field monitoring will summarize portfolio status once field scene and leaderboard APIs exist."
      dependency="Planned for Phase 4 and Phase 9."
    />
  );
}

export function FieldLeaderboardPage() {
  return (
    <Placeholder
      moduleName="Field leaderboard"
      summary="Leaderboard ranking will compare fields by index, crop, group, report date, and change signals."
      dependency="Planned for Phase 9 after analytics and weather outputs are available."
    />
  );
}

export function ReportingPage() {
  return (
    <Placeholder
      moduleName="Reporting"
      summary="Custom report templates and exports will be composed from Akasha field, analytics, weather, and activity data."
      dependency="Planned for Phase 9."
    />
  );
}

export function DiseasesPestsPage() {
  return (
    <Placeholder
      moduleName="Diseases & Pests"
      summary="Disease and pest risk will stay non-diagnostic until validated crop-stage, weather, and risk models exist."
      dependency="Planned for Phase 11."
    />
  );
}

export function WeatherAnalyticsPage() {
  return (
    <Placeholder
      moduleName="Weather Analytics"
      summary="Historical weather charts will use normalized Akasha weather provider contracts for selected fields."
      dependency="Planned for Phase 7."
    />
  );
}

export function WeatherForecastPage() {
  return (
    <Placeholder
      moduleName="Weather Forecast"
      summary="Forecast cards and timelines will require a selected field and server-side weather provider routes."
      dependency="Planned for Phase 7."
    />
  );
}

export function FieldActivityLogPage() {
  return (
    <Placeholder
      moduleName="Field activity log"
      summary="Operations logging will track field activities, filters, assignees, and report downloads as Akasha-owned data."
      dependency="Planned for Phase 10."
    />
  );
}

export function VraSowingPage() {
  return (
    <Placeholder
      moduleName="VRA Sowing"
      summary="Variable-rate sowing maps will build on field zones, crop metadata, and export workflows."
      dependency="Planned after Phase 8 vegetation zoning."
    />
  );
}

export function VraVegetationPage() {
  return (
    <Placeholder
      moduleName="VRA Vegetation"
      summary="Vegetation zoning will create field zones from a selected date, index, and zone-count request."
      dependency="Planned for Phase 8."
    />
  );
}

export function VraPkPage() {
  return (
    <Placeholder
      moduleName="VRA P&K"
      summary="Phosphorus and potassium prescription maps need productivity history and soil or upload inputs."
      dependency="Planned after Phase 8 and data-manager work."
    />
  );
}

export function VraMapBuilderPage() {
  return (
    <Placeholder
      moduleName="VRA Map builder"
      summary="Map builder will combine selected layers and rules into custom application maps."
      dependency="Planned after core zoning and export flows exist."
    />
  );
}

export function VraSoilSamplingPage() {
  return (
    <Placeholder
      moduleName="VRA Soil sampling"
      summary="Soil sampling maps will divide fields into sampling zones and planned points."
      dependency="Planned after VRA and data-manager foundations."
    />
  );
}

export function ScoutTasksPage() {
  return (
    <Placeholder
      moduleName="Scout tasks"
      summary="Scouting tasks will support map pins, new/closed states, filters, and field assignment."
      dependency="Planned for Phase 10."
    />
  );
}

export function DataManagerPage() {
  return (
    <Placeholder
      moduleName="Data manager"
      summary="Dataset uploads will support field boundary and machinery-data metadata without exposing storage internals."
      dependency="Planned for Phase 10."
    />
  );
}

export function ConnectionsPage() {
  return (
    <Placeholder
      moduleName="Connections"
      summary="External machinery integrations remain disconnected until a target integration is confirmed."
      dependency="John Deere and other OAuth flows are deferred to later integration work."
    />
  );
}

export function FieldGroupsPage() {
  return (
    <Placeholder
      moduleName="Field groups"
      summary="Field groups will organize fields for filtering, reports, weather, and operations modules."
      dependency="Planned for Phase 10."
    />
  );
}

export function AiAssistantPage() {
  return (
    <Placeholder
      moduleName="AI assistant"
      summary="The assistant shell will summarize only evidence available from Akasha APIs when the supporting endpoints exist."
      dependency="Planned for Phase 12 after analytics, weather, risk, and auth foundations."
    />
  );
}

export function NotificationsPage() {
  return (
    <Placeholder
      moduleName="Notifications"
      summary="Notifications will surface field changes, task assignment, report availability, and provider sync failures."
      dependency="Planned for Phase 12."
    />
  );
}

export function HelpPage() {
  return (
    <Placeholder
      moduleName="Help"
      summary="Help content will link product guidance, release notes, and support resources without changing runtime workflows."
      dependency="Content and support links are deferred."
    />
  );
}

export function MarketplacePage() {
  return (
    <Placeholder
      moduleName="Marketplace"
      summary="Marketplace add-ons remain a navigation shell until commercial add-on scope is confirmed."
      dependency="Deferred beyond first EOS-like workflow parity."
    />
  );
}

export function AccountSettingsPage() {
  return (
    <Placeholder
      moduleName="Account settings"
      summary="Account, team, and product settings require the later auth and ownership foundation."
      dependency="Planned for Phase 12."
    />
  );
}

export function ApiSettingsPage() {
  return (
    <Placeholder
      moduleName="API settings"
      summary="API settings will never expose provider secrets and will be implemented after Akasha auth is in place."
      dependency="Planned for Phase 12."
    />
  );
}
