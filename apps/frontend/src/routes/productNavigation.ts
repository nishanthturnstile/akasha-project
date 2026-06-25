import {
  Activity,
  Bell,
  Bot,
  Bug,
  CalendarClock,
  CloudSun,
  Database,
  FileBarChart,
  Flag,
  Gauge,
  HelpCircle,
  KeyRound,
  Layers3,
  LineChart,
  MapPinned,
  NotebookTabs,
  Rows3,
  Settings,
  ShoppingBag,
  Sprout,
  Target,
  Users,
  type LucideIcon,
} from 'lucide-react';

export interface ProductNavItem {
  description: string;
  icon: LucideIcon;
  label: string;
  path: string;
  requiredRoles?: string[];
  status?: 'ready' | 'planned';
  surface?: 'product' | 'admin';
}

export interface ProductNavGroup {
  icon: LucideIcon;
  items: ProductNavItem[];
  label: string;
}

export const MAIN_MONITORING_ROUTE = '/monitoring/field-analytics';

export const productNavigation: ProductNavGroup[] = [
  {
    label: 'Monitoring',
    icon: Activity,
    items: [
      {
        label: 'Field analytics',
        path: MAIN_MONITORING_ROUTE,
        icon: LineChart,
        description: 'Satellite map workspace with fields, timeline, and layers.',
        status: 'ready',
      },
      {
        label: 'Field leaderboard',
        path: '/monitoring/field-leaderboard',
        icon: Rows3,
        description: 'Rank fields by latest crop-monitoring signals.',
        status: 'planned',
      },
      {
        label: 'Reporting',
        path: '/monitoring/reporting',
        icon: FileBarChart,
        description: 'Build and export field monitoring reports.',
        status: 'planned',
      },
      {
        label: 'Diseases & Pests',
        path: '/monitoring/diseases-pests',
        icon: Bug,
        description: 'Risk context for validated crop threat models.',
        status: 'planned',
      },
    ],
  },
  {
    label: 'Operations Admin',
    icon: Settings,
    items: [
      {
        label: 'Ingestion overview',
        path: '/admin/ingestion',
        icon: Database,
        description: 'Internal imagery-source and scheduler operations overview.',
        requiredRoles: ['owner', 'admin'],
        status: 'ready',
        surface: 'admin',
      },
      {
        label: 'Ingestion jobs',
        path: '/admin/ingestion/jobs',
        icon: Rows3,
        description: 'Internal ingestion job queue and run history.',
        requiredRoles: ['owner', 'admin'],
        status: 'ready',
        surface: 'admin',
      },
      {
        label: 'Schedules',
        path: '/admin/ingestion/schedules',
        icon: CalendarClock,
        description: 'Internal source and AOI scheduler cadence.',
        requiredRoles: ['owner', 'admin'],
        status: 'ready',
        surface: 'admin',
      },
    ],
  },
  {
    label: 'Weather',
    icon: CloudSun,
    items: [
      {
        label: 'Analytics',
        path: '/weather/analytics',
        icon: Gauge,
        description: 'Historical weather parameters and comparisons.',
        status: 'planned',
      },
      {
        label: 'Forecast',
        path: '/weather/forecast',
        icon: CloudSun,
        description: 'Field forecast cards and forecast timeline.',
        status: 'planned',
      },
    ],
  },
  {
    label: 'Operations',
    icon: NotebookTabs,
    items: [
      {
        label: 'Field activity log',
        path: '/activity-log',
        icon: NotebookTabs,
        description: 'Track planned and completed field work.',
        status: 'planned',
      },
      {
        label: 'Scout tasks',
        path: '/scout-tasks',
        icon: MapPinned,
        description: 'Map-based scouting tasks and field notes.',
        status: 'planned',
      },
      {
        label: 'Data',
        path: '/data-manager/data',
        icon: Database,
        description: 'Upload and manage field datasets.',
        status: 'planned',
      },
      {
        label: 'Connections',
        path: '/data-manager/connections',
        icon: Layers3,
        description: 'External machinery and data connections.',
        status: 'planned',
      },
      {
        label: 'Field groups',
        path: '/field-manager/groups',
        icon: Users,
        description: 'Organize fields into operational groups.',
        status: 'planned',
      },
    ],
  },
  {
    label: 'VRA maps',
    icon: Layers3,
    items: [
      {
        label: 'Sowing',
        path: '/vra/sowing',
        icon: Sprout,
        description: 'Variable-rate sowing map workflow.',
        status: 'planned',
      },
      {
        label: 'Vegetation',
        path: '/vra/vegetation',
        icon: Target,
        description: 'Vegetation-zone creation and export.',
        status: 'planned',
      },
      {
        label: 'P&K',
        path: '/vra/pk',
        icon: Flag,
        description: 'Phosphorus and potassium prescription maps.',
        status: 'planned',
      },
      {
        label: 'Map builder',
        path: '/vra/map-builder',
        icon: Activity,
        description: 'Combine layers into custom application maps.',
        status: 'planned',
      },
      {
        label: 'Soil sampling',
        path: '/vra/soil-sampling',
        icon: MapPinned,
        description: 'Sampling zones and point planning.',
        status: 'planned',
      },
    ],
  },
  {
    label: 'Utility',
    icon: Settings,
    items: [
      {
        label: 'AI assistant',
        path: '/assistant',
        icon: Bot,
        description: 'Evidence-bound assistant shell.',
        status: 'planned',
      },
      {
        label: 'Notifications',
        path: '/notifications',
        icon: Bell,
        description: 'Field changes, tasks, and report alerts.',
        status: 'planned',
      },
      {
        label: 'Help',
        path: '/help',
        icon: HelpCircle,
        description: 'User guide and support links.',
        status: 'planned',
      },
      {
        label: 'Marketplace',
        path: '/marketplace',
        icon: ShoppingBag,
        description: 'Add-ons and integrations.',
        status: 'planned',
      },
      {
        label: 'Settings',
        path: '/account/settings',
        icon: Settings,
        description: 'Account, team, and product settings.',
        status: 'planned',
      },
      {
        label: 'API',
        path: '/account/api',
        icon: KeyRound,
        description: 'API access and integration settings.',
        status: 'planned',
      },
    ],
  },
];

export const flatProductNavigation = productNavigation.flatMap((group) => group.items);
