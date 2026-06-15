import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve("outputs", "akasha-delivery-tracker-refresh");
const outputPath = path.join(outputDir, "Akasha Delivery Tracker Refresh.xlsx");

const owners = {
  frontend: "Frontend - Rafiq",
  backend: "Backend/API - Sanoj",
  fullstack: "Fullstack - Deva",
  architect: "Architect / Fullstack / DevOps - Nishanth",
  lead: "Team Lead - Karthi",
  shared: "Team Lead - Karthi; Architect / Fullstack / DevOps - Nishanth",
};

const sourceUrls = [
  ["Seasonality guide", "https://eos.com/user-guide/crop-monitoring/seasonality/"],
  ["Add field guide", "https://eos.com/user-guide/crop-monitoring/add-field/"],
  ["Monitoring guide", "https://eos.com/user-guide/crop-monitoring/fields/"],
  ["VRA maps guide", "https://eos.com/user-guide/crop-monitoring/vra-maps/"],
  ["Field manager guide", "https://eos.com/user-guide/crop-monitoring/field-manager/"],
];

const roadmapHeaders = [
  "Phase",
  "Module",
  "EOS Baseline Feature",
  "Akasha Scope",
  "UI Scope",
  "Backend/Data Scope",
  "DevOps/QA Scope",
  "Owner",
  "Priority",
  "Status",
  "Acceptance Criteria",
  "Dependencies",
  "Notes",
];

const roadmap = [
  [
    "Phase 0 - Implemented Foundation",
    "Architecture and service topology",
    "Production application foundation",
    "Canonical multi-service app with one public web gateway, internal API/TiTiler/STAC/PostGIS/MinIO, local Docker, Railway, and Coolify portability.",
    "React/Vite SPA served through Caddy gateway; same-origin /api and /tiles paths.",
    "FastAPI BFF, pgSTAC/STAC, PostGIS, MinIO, TiTiler display tile path, ingestion worker.",
    "Docker Compose, health checks, slice validators, smoke test, pinned images.",
    owners.architect,
    "P0",
    "Done",
    "Gateway is the only public service; API and tile calls stay same-origin; local stack can bootstrap with make dev.",
    "None.",
    "Old root preview shims are no longer source of truth.",
  ],
  [
    "Phase 0 - Implemented Foundation",
    "Auth, teams, account and API access shell",
    "Team Management; Settings; Access Through API",
    "Hand-rolled cookie-session auth with team roles, account profile, API keys, notifications, password change, bootstrap controls.",
    "Login page, auth gate, app shell, account/API/notifications pages.",
    "Auth/session tables, HMAC session tokens, Argon2 password hashing, owner/admin/member/viewer roles, account routes.",
    "Auth-on deployment guardrails; local disabled mode only where permitted.",
    owners.backend,
    "P0",
    "Done",
    "Protected routes require session/team context; bootstrap is controlled; API keys never expose service secrets.",
    "Production secrets and password pepper.",
    "Not Better Auth; current implementation is Akasha-owned.",
  ],
  [
    "Phase 0 - Implemented Foundation",
    "Core field and plot management",
    "Add field; Draw field; Upload fields; Field Manager",
    "Named plots/fields with geometry, area, crop metadata, season label, groups, import/export.",
    "Field analytics map supports drawing/editing with Terra Draw; field list/panel; GeoJSON import/export actions.",
    "Plot CRUD, field CRUD, field groups, field seasons/seasons models, GeoJSON validation/export.",
    "API tests for plots, fields, field groups, seasons, exports.",
    `${owners.frontend}; ${owners.backend}`,
    "P0",
    "Partial",
    "User can create and manage field boundaries through native APIs; EOS-style upload formats beyond GeoJSON remain planned.",
    "Shapefile/KML/KMZ upload parser for full EOS parity.",
    "Current geometry upload is GeoJSON-oriented.",
  ],
  [
    "Phase 0 - Implemented Foundation",
    "Map and monitoring workspace",
    "Work With Crop Map; Monitoring; Image sources; Date line; Vegetation indices",
    "MapLibre workspace with ArcGIS basemap, satellite overlays, source/date layer panel, opacity, visibility, compare, measurement, command palette, index panel.",
    "Field Analytics route is the main ready product screen; MapPage drives map, layers, timeline controls, draw/edit, stats panel.",
    "BFF product routes for config, sources, dates, layers, tiles, and index statistics.",
    "Frontend unit tests cover layer/date behavior and same-origin tile URL helpers.",
    owners.frontend,
    "P0",
    "Done",
    "Default map is true-colour basemap; overlay metadata comes from BFF; browser never receives MinIO/STAC/TiTiler internals.",
    "Dense ResourceSat composite catalog for production data.",
    "ArcGIS remains basemap; ResourceSat FCC is an overlay.",
  ],
  [
    "Phase 0 - Implemented Foundation",
    "CI/CD and self-hosted deployment",
    "Production operations foundation",
    "GitHub Actions CI, GHCR image build, Coolify staging deploy, production deploy workflow, Azure VM staging validation.",
    "No direct UI feature; deploys the SPA/gateway image.",
    "Builds web/api/ingestion-worker/ingestion-sar images; patches Coolify compose with immutable SHA.",
    "CI runs API tests, frontend lint/test/build, slice validators, Trivy scan; staging deploy uses self-hosted runner.",
    owners.architect,
    "P0",
    "Validated",
    "Staging stack can be patched/deployed through Coolify; private service ports remain closed; smoke checks pass.",
    "Production Coolify service UUID and final domain/TLS before production cutover.",
    "Production deploy uses previously validated Git SHA only.",
  ],
  [
    "Phase 1 - Bhoonidhi ResourceSat Completion",
    "Bhoonidhi access and product diagnostics",
    "Image sources; monitoring data availability",
    "Validated ResourceSat-2A LISS-3 BOA search/download from staging VM and inspected real product layout.",
    "Admin-only diagnostic result is backend-facing; no raw download exposed in UI.",
    "Bhoonidhi diagnostic endpoint, stdlib client, real download inspection, sanitized job status.",
    "Staging smoke from whitelisted egress IP 20.219.3.35; tests mock network and archive inspection.",
    `${owners.backend}; ${owners.architect}`,
    "P0",
    "Validated",
    "Search returns Online=Y products; download succeeds; product contains BAND2/BAND3/BAND4/BAND5; no native quality raster found.",
    "Bhoonidhi credentials and static staging egress must remain valid.",
    "Diagnostic should remain disabled except during controlled staging tests.",
  ],
  [
    "Phase 1 - Bhoonidhi ResourceSat Completion",
    "Source-aware raster/statistics contracts",
    "Monitoring indexes; mask filter; image sources",
    "Generalize Sentinel SCL assumptions to source-neutral masks, ResourceSat spectral roles, FCC display, and supported-index validation.",
    "Hide unsupported indices; show mask provenance/provisional status; use FCC display mode for ResourceSat.",
    "Source registry, ResourceSat band roles, mask asset, MSAVI formula, unsupported-index rejection, source-neutral pixel-count fields.",
    "API/frontend contract tests for source-specific indices and mask fields.",
    `${owners.backend}; ${owners.frontend}`,
    "P0",
    "In Progress",
    "ResourceSat supports NDVI, MSAVI, NDMI, NDWI_GREEN_NIR; NDRE/RECI hidden or rejected; output no longer exposes Sentinel-only SCL wording.",
    "Complete source-neutral API/UI rename and tests.",
    "Current working tree includes active ResourceSat/source-neutral changes.",
  ],
  [
    "Phase 1 - Bhoonidhi ResourceSat Completion",
    "Single-scene COG preparation",
    "Latest Image layer; monitoring date line",
    "Prepare ResourceSat BOA products into analytic COG and Akasha-generated mask COG with correct band order and reflectance metadata.",
    "No direct UI until loaded into catalog; later appears as selectable ResourceSat date.",
    "prepare_resourcesat_liss3_boa_cogs.py, BAND_META parsing, mask classes, COG validation.",
    "Synthetic and real-product COG tests; verify-manifest-cogs.",
    `${owners.fullstack}; ${owners.backend}`,
    "P0",
    "In Progress",
    "Generated analytic has 4 bands; mask aligns; overviews valid; metadata records provisional mask method and attribution.",
    "More real samples to validate consistent product layout.",
    "Proceed with provisional mask fallback because diagnostic found no native quality layer.",
  ],
  [
    "Phase 1 - Bhoonidhi ResourceSat Completion",
    "Full 60 km AOI composite",
    "Image sources; date line; full coverage monitoring",
    "Build ingestion-time cloud-free composite per dated window: one analytic COG plus one mask COG covering Bangalore 60 km AOI.",
    "ResourceSat FCC overlay should cover the full launch AOI; timeline dates represent composite dates.",
    "Composite grid, reprojection, valid-pixel selection, most-recent-valid tie-break, metrics, STAC item generation.",
    "verify-composite requires coverage threshold, CRS/resolution, mask classes, COG overviews, catalog item.",
    `${owners.fullstack}; ${owners.architect}`,
    "P0",
    "In Progress",
    "Composite date renders without multi-scene errors; polygons anywhere in AOI return cloud-free stats.",
    "Enough Online=Y products within compositing windows.",
    "This is the launch gate before switching default source to ResourceSat.",
  ],
  [
    "Phase 1 - Bhoonidhi ResourceSat Completion",
    "Scheduled sync and 90-day backfill",
    "Date line; historical monitoring",
    "Automate search, download, prepare, composite, verify, and ingest on the whitelisted staging VM.",
    "Timeline lists available composite dates for the last 3 months.",
    "bhoonidhi-sync, SQLite ledger, retry/backoff, raw/temp paths under /srv/akasha, STAC/MinIO ingest.",
    "Idempotency tests, rate-limit handling tests, operator logs, daily schedule validation.",
    `${owners.architect}; ${owners.fullstack}`,
    "P1",
    "In Progress",
    "Re-running sync skips completed products, rebuilds affected composites, and avoids duplicates.",
    "Bhoonidhi rate limits and daily download caps.",
    "Backfill may need to span multiple days.",
  ],
  [
    "Phase 2 - Core EOS Monitoring Parity",
    "Field analytics and charts",
    "Monitoring; Charts; Vegetation indices; Details",
    "Field-specific index statistics, trend chart, selected source/date/index, downloadable index/report outputs.",
    "Field trend chart, index panel, cloud/mask controls, download menu.",
    "Field analytics API, field exports, BFF statistics engine.",
    "API and frontend tests for analytics/export flows.",
    `${owners.frontend}; ${owners.backend}`,
    "P0",
    "Partial",
    "Selected field shows latest index stats/trends and exports; source-specific index availability enforced.",
    "ResourceSat composite dates and source-neutral mask payloads.",
    "EOS VMI/ReCI are not supported unless source data supports them.",
  ],
  [
    "Phase 2 - Core EOS Monitoring Parity",
    "Map tools and layer controls",
    "Find location; Zoom tool; Distance and area measurements; Split view; Layers; Contrast view",
    "Map controls, coordinate readout, measurement, source/date panel, compare control, opacity and visibility.",
    "Layer panel, compare control, measurement tool, command palette, legend, MapLayerManager.",
    "Same-origin tile templates from BFF; no direct storage URLs.",
    "Frontend tests for layer manager, compare, controls, measurement, URL state.",
    owners.frontend,
    "P1",
    "Partial",
    "User can inspect source/date layers and compare dates without disrupting basemap.",
    "Polish split/contrast parity against exact client expectations.",
    "EOS terminology may need client screenshot alignment.",
  ],
  [
    "Phase 3 - Seasonality & Field Manager",
    "Season lifecycle",
    "Seasonality: create, edit, delete season",
    "Create/edit/delete seasons, assign fields to seasons, preserve at least one active season rule.",
    "Season management UI and field assignment workflow.",
    "Seasons API and field-season association already exist; enforce EOS deletion/transfer rules.",
    "Tests for season duration edits and field association constraints.",
    `${owners.backend}; ${owners.frontend}`,
    "P1",
    "Partial",
    "Season list supports create/edit/delete; fields are always associated with at least one season.",
    "UI completion and EOS-specific validation rules.",
    "Backend primitives exist; full EOS workflow needs UI hardening.",
  ],
  [
    "Phase 3 - Seasonality & Field Manager",
    "Crop rotation, sowing and allocation",
    "Field Manager: crop rotation, manage sowing, crop allocation",
    "Capture crop type, variety, sowing/planting/harvest metadata, season crop allocation, and field filters.",
    "Field edit forms and manager screens for crop/season assignment.",
    "Plot/field metadata columns exist; add normalized crop catalog only if required.",
    "Validation tests for dates inside season and crop allocation filters.",
    `${owners.frontend}; ${owners.backend}`,
    "P1",
    "Planned",
    "Crop and sowing metadata drive monitoring filters and reports.",
    "Client crop taxonomy, if different from free text.",
    "Keep initial version lightweight unless client needs full crop catalog admin.",
  ],
  [
    "Phase 3 - Seasonality & Field Manager",
    "Field groups",
    "Field Manager: field groups",
    "Group fields by operational characteristics for filtering, reports, weather and operations.",
    "Field groups page with create/edit/delete and assign fields.",
    "Field groups API and membership table already exist.",
    "API/frontend tests for assignment and group filters.",
    `${owners.fullstack}; ${owners.frontend}`,
    "P1",
    "Partial",
    "Groups can be maintained and reflected in field views/reports.",
    "UI completion.",
    "Backend is ahead of product UI.",
  ],
  [
    "Phase 4 - Operations & Scouting",
    "Field activity log",
    "Field Activity Log",
    "Track planned/completed field work, inputs, status, assignee, cost, notes and CSV export.",
    "Activity log page with filters and edit flows.",
    "Activities API and CSV export already exist.",
    "Tests cover list/create/update/delete/export.",
    `${owners.backend}; ${owners.frontend}`,
    "P1",
    "Partial",
    "Activities can be created and exported; UI supports daily operations workflow.",
    "UX parity for filters and status views.",
    "Native Akasha data, not EOS import.",
  ],
  [
    "Phase 4 - Operations & Scouting",
    "Scout tasks",
    "Scouting: task description, report, download, closed tasks",
    "Map-based scouting tasks with status, priority, assignee, notes, coordinates and closed-task handling.",
    "Scout tasks page and map pins.",
    "Scout task API exists; attachments model exists.",
    "Tests for create/update/close/delete and future report/download.",
    `${owners.frontend}; ${owners.backend}`,
    "P1",
    "Partial",
    "User can create and close scouting tasks for fields; reports/downloads are added after core task UI.",
    "Attachment/report UX.",
    "Current backend primitives exist.",
  ],
  [
    "Phase 5 - Reports, Leaderboard & Risk",
    "Field leaderboard and reports",
    "Overview: Season Analytics, Field Leaderboard, Custom Report",
    "Rank fields by latest monitoring signals and export custom report templates.",
    "Leaderboard and reporting pages; template UI.",
    "Reports API, templates and leaderboard export routes exist.",
    "CSV export tests and report-template API tests.",
    `${owners.frontend}; ${owners.backend}`,
    "P1",
    "Partial",
    "Client can view ranked fields and export report data once analytics data is dense enough.",
    "ResourceSat history and UI completion.",
    "Reports should remain evidence-based.",
  ],
  [
    "Phase 5 - Reports, Leaderboard & Risk",
    "Disease and pest risk context",
    "Risks; Diseases & Pests",
    "Transparent crop-risk context, not diagnosis from vegetation index alone.",
    "Diseases & Pests page with evidence and disclaimers.",
    "Risk API exists with transparent rule model.",
    "Tests for risk summary route and unsupported cases.",
    `${owners.backend}; ${owners.frontend}`,
    "P2",
    "Partial",
    "Risk explanations cite input data and avoid unsupported diagnosis.",
    "Weather provider and validated crop-stage models for stronger alerts.",
    "Do not overclaim disease/pest detection.",
  ],
  [
    "Phase 6 - Weather",
    "Historical weather analytics",
    "Historical weather; precipitation, temperature, active temperature, moisture charts",
    "Field-level historical weather charts aligned to seasons and monitoring dates.",
    "Weather analytics page with chart panels.",
    "Weather provider adapter behind BFF; normalized field/date weather endpoints.",
    "Provider contract tests and chart tests.",
    `${owners.fullstack}; ${owners.frontend}`,
    "P2",
    "Deferred",
    "Historical precipitation/temperature/moisture charts render for selected fields.",
    "Weather data provider selection and license.",
    "No provider is selected yet.",
  ],
  [
    "Phase 6 - Weather",
    "Weather forecast",
    "Weather Forecast",
    "Forecast cards and timeline for selected fields.",
    "Forecast page with field cards and forecast timeline.",
    "Forecast API normalized behind BFF.",
    "Provider mocks and fallback-state tests.",
    `${owners.fullstack}; ${owners.frontend}`,
    "P2",
    "Deferred",
    "Forecast data is available without exposing provider credentials.",
    "Weather data provider.",
    "Deferred until provider decision.",
  ],
  [
    "Phase 7 - Data Manager & Connections",
    "Dataset uploads",
    "Data Manager: Data",
    "Upload and manage boundary/machinery datasets with metadata and validation messages.",
    "Data manager page with upload/list/status.",
    "Datasets API and uploaded_datasets table exist; extend parsers for target formats.",
    "Upload validation tests and no-secret storage checks.",
    `${owners.fullstack}; ${owners.frontend}`,
    "P2",
    "Partial",
    "User can upload supported datasets and see validation state.",
    "Supported format list and file-size limits.",
    "Current backend supports initial dataset metadata.",
  ],
  [
    "Phase 7 - Data Manager & Connections",
    "Machinery connections",
    "Data Manager: Connections",
    "External machinery connection status and future OAuth integrations such as John Deere-style flows.",
    "Connections page with disconnected/connected states.",
    "Connection status API placeholder; no external OAuth until target integration confirmed.",
    "Mock connection tests before live provider work.",
    `${owners.architect}; ${owners.fullstack}`,
    "P3",
    "Deferred",
    "Client-approved machinery provider can connect without leaking tokens.",
    "Provider agreement, OAuth app, callback domain.",
    "Do not build speculative OAuth integrations.",
  ],
  [
    "Phase 8 - VRA Maps",
    "Vegetation zoning",
    "Zoning; VRA maps",
    "Create zones from selected index/date and field, with 2-7 zone support where appropriate.",
    "Vegetation VRA page with zone count, detail level, preview and save.",
    "Zoning algorithm over cloud-masked index rasters; persist map metadata.",
    "Algorithm unit tests and export validation.",
    `${owners.fullstack}; ${owners.frontend}`,
    "P2",
    "Planned",
    "Zones are reproducible and derived from selected source/date/index.",
    "ResourceSat composite analytics ready.",
    "Start with vegetation zones before fertilizer/seeding prescriptions.",
  ],
  [
    "Phase 8 - VRA Maps",
    "Sowing, nitrogen, P&K and map builder",
    "Create sowing maps; nitrogen fertilization; P&K; map builder; supported formats; save maps",
    "Build variable-rate maps and exports using selected layers and optional uploaded machinery/yield data.",
    "VRA module pages for sowing, vegetation, P&K, map builder, soil sampling.",
    "Prescription model, export format support, layer combination pipeline.",
    "Golden-file export tests and machinery-format compatibility tests.",
    `${owners.fullstack}; ${owners.architect}`,
    "P3",
    "Planned",
    "Saved VRA maps can be downloaded in agreed supported formats.",
    "Client equipment/export-format requirements.",
    "Map builder can use up to five selected layers after data manager exists.",
  ],
  [
    "Phase 9 - Production Hardening",
    "Production Coolify rollout",
    "Pilot operations",
    "Create production environment, deploy validated Git SHA, run migrations/seeds, smoke, rollback rehearsal.",
    "Production SPA with final domain/TLS.",
    "Production Coolify stack, env, migrations, MinIO/STAC/PostGIS state.",
    "Manual approval workflow, smoke tests, private-port scans, rollback.",
    `${owners.architect}; ${owners.lead}`,
    "P0",
    "Planned",
    "Production deploy uses exact staging-validated image tag and passes authenticated smoke tests.",
    "Production VM/domain/TLS/secrets.",
    "Staging path is validated; production promotion remains planned.",
  ],
  [
    "Phase 9 - Production Hardening",
    "Monitoring, backup and support",
    "Operational readiness",
    "Monitor latest composite freshness, Bhoonidhi failures, MinIO usage, STAC registration, backups and restore drills.",
    "Admin/support visibility where needed.",
    "Worker logs, support bundle, backup/restore scripts, ingestion ledger, stale-date alerts.",
    "Restore dry run, support-bundle redaction, alert checks.",
    `${owners.architect}; ${owners.lead}`,
    "P1",
    "Planned",
    "Operators can diagnose failed refreshes and restore from backup.",
    "Production backup target and alert channel.",
    "Required before long-running pilot.",
  ],
];

const builtInventoryHeaders = ["Area", "Implemented / Validated Capability", "Status", "Evidence", "Owner", "Next Gap"];
const builtInventory = [
  ["Architecture", "Canonical multi-service topology with web gateway, API, TiTiler, STAC API, PostGIS, MinIO, ingestion worker.", "Done", "README, infra/docker, infra/gateway, apps/api, services/*.", owners.architect, "Production environment creation."],
  ["Frontend", "React 18 + Vite + TypeScript SPA, product shell, authenticated routes, MapPage field analytics workspace.", "Done", "apps/frontend/src/routes/ProductRoutes.tsx; FieldAnalyticsPage uses MapPage.", owners.frontend, "Complete placeholder modules."],
  ["Basemap", "ArcGIS/Esri basemap configured as visual base layer.", "Done", "apps/frontend package uses @esri/maplibre-arcgis; /api/config basemap payload.", owners.frontend, "Keep ResourceSat as overlay only."],
  ["Map UX", "Layer panel, source/date selection, opacity, visibility, compare, measure, command palette, legend, URL state.", "Done", "apps/frontend/src/components/map and components/layers tests.", owners.frontend, "EOS split/contrast polish."],
  ["BFF Product API", "Config, sources, dates, default layer, display-mode tiles, index statistics.", "Done", "apps/api/app/product.py.", owners.backend, "Finish source-neutral ResourceSat fields."],
  ["Raster Statistics", "BFF computes cloud/mask-aware index stats; TiTiler serves display tiles only.", "Done", "apps/api/app/raster/service.py and statistics_core.py.", owners.backend, "ResourceSat composite statistics smoke."],
  ["Auth/Teams", "Cookie sessions, team RBAC, login/logout/bootstrap/password, API keys, notifications.", "Done", "apps/api/app/auth*.py, account.py, models.py.", owners.backend, "Production user provisioning policy."],
  ["Fields/Plots", "Plot CRUD, field CRUD, field groups, seasons, GeoJSON import/export.", "Partial", "apps/api/app/plots.py, fields.py, field_groups.py, seasons.py.", `${owners.backend}; ${owners.frontend}`, "Full EOS upload formats and season UI."],
  ["Operations", "Activities, scout tasks, attachments model, activity CSV export.", "Partial", "apps/api/app/operations.py, scout_tasks.py, models.py.", `${owners.backend}; ${owners.frontend}`, "Complete operations/scouting UI parity."],
  ["Reports/Risk", "Report templates, leaderboard APIs, risk summary API.", "Partial", "apps/api/app/reports.py, risk.py.", owners.backend, "UI polish and data density."],
  ["Data Manager", "Dataset upload metadata and connection status endpoints.", "Partial", "apps/api/app/data_manager.py.", `${owners.fullstack}; ${owners.frontend}`, "Format parsers and UI completion."],
  ["Bhoonidhi Diagnostics", "Real staging auth/search/download/inspect validated on 2026-06-14.", "Validated", "docs/impl-plan/feature-bhoonidhi-diagnostic-download-1.md.", `${owners.backend}; ${owners.architect}`, "Full ingestion/composite path."],
  ["ResourceSat Registry", "ResourceSat LISS-3 BOA source, FCC display mode, spectral roles, provisional mask metadata.", "In Progress", "apps/api/app/raster/catalog_resolver.py and indices.py.", owners.backend, "Complete source-neutral payload migration."],
  ["Composite Pipeline", "Best-available-pixel ResourceSat composite helpers, verify-composite, bhoonidhi-sync ledger.", "In Progress", "services/ingestion/akasha_ingest/composite.py, sync.py, worker.py.", `${owners.fullstack}; ${owners.architect}`, "Real full-AOI composite smoke."],
  ["CI/CD", "CI workflow, Trivy scan, GHCR image build, Coolify staging patch/deploy, production deploy workflow.", "Validated", ".github/workflows/*.yml; infra/selfhosted/README.md.", owners.architect, "Production promotion and rollback drill."],
];

const eosHeaders = ["EOSDA Module", "Baseline Functionalities", "Akasha Current Status", "Current Akasha Coverage", "Gap / Planned Work", "Owner", "Priority"];
const eosMapping = [
  ["Seasonality", "Create season; edit season; delete season; copy/transfer fields; season dates drive analytics.", "Partial", "Backend seasons and field-season schema exist.", "Complete season UI, copy/transfer workflow, deletion guardrails.", `${owners.backend}; ${owners.frontend}`, "P1"],
  ["Add Field", "Upload fields; draw field; upload error handling; layers/latest image during field creation.", "Partial", "Draw/edit with Terra Draw and GeoJSON import/export exist.", "Add SHP/KML/KMZ upload, parameter mapping, upload manager, circle/cut tools if required.", `${owners.frontend}; ${owners.backend}`, "P1"],
  ["Monitoring", "Image sources, elevation/slope, date line, crop info, crop rotation, growth stages, risks, charts.", "Partial", "Source/date overlays, field analytics, risk API, trend chart foundations exist.", "ResourceSat composites, season-aware charts, elevation/slope if required.", `${owners.frontend}; ${owners.backend}`, "P0"],
  ["Monitoring Indexes", "NDVI, NDRE, MSAVI, ReCI, NDMI, details, download, mask filter.", "Partial", "NDVI, NDRE, NDMI, NDWI and MSAVI registry; exports and mask controls exist.", "Hide unsupported indices per source; ResourceSat does not support NDRE/ReCI.", owners.backend, "P0"],
  ["Weather", "Historical weather, precipitation, daily temperatures, active temperature, forecast.", "Deferred", "Weather routes are placeholder-only.", "Select provider, implement BFF adapter and UI charts.", `${owners.fullstack}; ${owners.frontend}`, "P2"],
  ["Scouting", "Task description, general info, report, download, closed tasks.", "Partial", "Scout task API exists; UI route exists.", "Map pins, reports/downloads, closed-task UX.", `${owners.frontend}; ${owners.backend}`, "P1"],
  ["Overview", "Season analytics, field leaderboard, custom report.", "Partial", "Leaderboard/report APIs and templates exist.", "Client-ready UI, report builder, season analytics from dense data.", `${owners.frontend}; ${owners.backend}`, "P1"],
  ["VRA Maps", "Sowing, nitrogen, P&K, map builder, savings, machinery formats, save maps.", "Planned", "Navigation shell exists.", "Zoning, prescriptions, layer combination, equipment-format exports.", `${owners.fullstack}; ${owners.architect}`, "P2"],
  ["Field Activity Log", "Track and manage field operations.", "Partial", "Activity API and export exist.", "Complete operations UI and filters.", `${owners.frontend}; ${owners.backend}`, "P1"],
  ["Data Manager - Data", "Upload/manage field datasets.", "Partial", "Dataset upload metadata API exists.", "UI, validation reports, supported file parsers.", `${owners.fullstack}; ${owners.frontend}`, "P2"],
  ["Data Manager - Connections", "External machinery/data connections.", "Deferred", "Connection status placeholder exists.", "Provider-specific OAuth after client confirms target integration.", `${owners.architect}; ${owners.fullstack}`, "P3"],
  ["Field Manager", "Crop rotation, manage sowing, crop allocation, field groups.", "Partial", "Field groups and metadata primitives exist.", "Complete crop/season allocation UI and rules.", `${owners.frontend}; ${owners.backend}`, "P1"],
  ["Team Management", "Add users, roles, dashboard, edit/switch teams.", "Partial", "Team memberships and roles exist; account/team endpoints exist.", "Team admin UI and invitation/user-management workflow.", `${owners.backend}; ${owners.frontend}`, "P2"],
  ["Settings", "Account/product settings.", "Partial", "Account settings/API key routes and pages exist.", "Finalize settings UI, notification preferences, team controls.", `${owners.frontend}; ${owners.backend}`, "P2"],
  ["Access Through API", "API access for integrations.", "Partial", "API key metadata/create/revoke exists.", "Document external API surface and rate-limit policy.", `${owners.backend}; ${owners.architect}`, "P2"],
];

const bhoonidhiHeaders = ["Workstream", "Task", "Status", "Owner", "Acceptance Criteria", "Dependencies / Notes"];
const bhoonidhiPlan = [
  ["Validated access", "Staging diagnostic endpoint, auth/search/download/inspect real LISS-3 BOA product.", "Validated", `${owners.backend}; ${owners.architect}`, "Real product downloaded from egress 20.219.3.35; four bands readable; no native mask found.", "Keep diagnostics disabled outside controlled staging tests."],
  ["Source contracts", "ResourceSat source metadata, FCC default display, role-based indices, source-neutral mask fields.", "In Progress", owners.backend, "Source lists supported indices and display modes; unsupported index requests fail safely.", "Frontend/API type migration still active."],
  ["Single-scene prep", "BAND_META parsing, analytic.tif and mask.tif generation, COG validation.", "In Progress", `${owners.fullstack}; ${owners.backend}`, "4-band analytic + 1-band mask aligned, overviews valid, reflectance scale/offset correct.", "Validate additional real products."],
  ["Composite build", "Full 60 km AOI ingestion-time cloud-free composite.", "In Progress", `${owners.fullstack}; ${owners.architect}`, "One dated analytic+mask pair covers launch AOI and avoids query-time mosaic errors.", "Availability of enough Online=Y scenes."],
  ["Catalog/storage", "Upload composite COGs to MinIO and register dated composite STAC item.", "In Progress", owners.fullstack, "BFF /sources/{id}/dates lists composite dates with metrics and tileAvailable true.", "STAC/MinIO env and catalog migration health."],
  ["Scheduled sync", "bhoonidhi-sync with SQLite ledger, retries, idempotent product selection and composite rebuild.", "In Progress", owners.architect, "Re-running sync skips terminal products and logs retryable failures.", "Bhoonidhi rate limits; /srv/akasha disk use."],
  ["UI timeline", "Past-three-month composite date timeline, latest cloud-free default, FCC overlay attribution.", "Planned", owners.frontend, "User selects composite date and sees FCC overlay plus cloud-free stats.", "Composite dates in catalog."],
  ["Production switch", "Switch default source from Sentinel to ResourceSat after composite smoke.", "Planned", `${owners.architect}; ${owners.lead}`, "ResourceSat is default; Sentinel removed or hidden from production.", "Only after Phase 2b full-AOI smoke succeeds."],
];

const riskHeaders = ["Type", "Decision / Risk / Input", "Status", "Owner", "Action / Note"];
const risks = [
  ["Locked decision", "ArcGIS remains the true-colour basemap; ResourceSat FCC is an Akasha overlay.", "Locked", owners.lead, "Do not replace basemap with ResourceSat."],
  ["Locked decision", "ResourceSat LISS-3 has no blue band; default display is FCC NIR/Red/Green.", "Locked", owners.backend, "Do not fake natural colour."],
  ["Locked decision", "Full 60 km AOI coverage is required for launch via ingestion-time composite.", "Locked", owners.architect, "Avoid query-time mosaic as the launch path."],
  ["Locked decision", "No native quality/cloud raster found in validated product; use Akasha threshold mask v1.", "Locked", owners.backend, "Label as provisional in API/UI."],
  ["Risk", "Bhoonidhi rate limits and daily download throttling can slow 90-day backfill.", "Open", owners.architect, "Spread backfill across days and reuse tokens."],
  ["Risk", "ResourceSat product availability may not yield cloud-free full coverage in every window.", "Open", owners.fullstack, "Composite metrics must show coverage and freshness honestly."],
  ["External input", "Weather provider and license are not selected.", "Needed", owners.lead, "Required before Weather phase implementation."],
  ["External input", "Client equipment/export formats for VRA are not confirmed.", "Needed", owners.lead, "Required before VRA export implementation."],
  ["External input", "Production domain, TLS, secrets, and Coolify production service UUID.", "Needed", owners.architect, "Required for production cutover."],
  ["Non-goal", "Do not expose Bhoonidhi, MinIO, STAC, TiTiler or raw object URLs to the browser.", "Always", owners.architect, "Keep one-public-service rule."],
  ["Non-goal", "Do not claim disease/pest diagnosis from vegetation index alone.", "Always", owners.backend, "Risk model must be evidence-bound."],
];

const statusColors = {
  Done: "#D1FAE5",
  Validated: "#C7D2FE",
  "In Progress": "#FEF3C7",
  Partial: "#DBEAFE",
  Planned: "#E5E7EB",
  Deferred: "#F3E8FF",
  Locked: "#D1FAE5",
  Open: "#FEE2E2",
  Needed: "#FEF3C7",
  Always: "#E0F2FE",
};

const phaseColors = {
  "Phase 0 - Implemented Foundation": "#0F766E",
  "Phase 1 - Bhoonidhi ResourceSat Completion": "#B45309",
  "Phase 2 - Core EOS Monitoring Parity": "#2563EB",
  "Phase 3 - Seasonality & Field Manager": "#7C3AED",
  "Phase 4 - Operations & Scouting": "#0E7490",
  "Phase 5 - Reports, Leaderboard & Risk": "#BE123C",
  "Phase 6 - Weather": "#0369A1",
  "Phase 7 - Data Manager & Connections": "#4D7C0F",
  "Phase 8 - VRA Maps": "#A16207",
  "Phase 9 - Production Hardening": "#374151",
};

function colLetter(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function styleHeader(range, fill = "#111827") {
  range.format = {
    fill,
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
  };
}

function styleTable(sheet, startRow, startCol, rowCount, colCount, tableName) {
  const start = `${colLetter(startCol)}${startRow}`;
  const end = `${colLetter(startCol + colCount - 1)}${startRow + rowCount - 1}`;
  styleHeader(sheet.getRange(`${start}:${colLetter(startCol + colCount - 1)}${startRow}`));
  const body = sheet.getRange(`${colLetter(startCol)}${startRow + 1}:${end}`);
  body.format = {
    wrapText: true,
    verticalAlignment: "top",
    borders: { preset: "all", style: "thin", color: "#D1D5DB" },
  };
  sheet.tables.add(`${start}:${end}`, true, tableName).style = "TableStyleMedium2";
}

function setWidths(sheet, widths) {
  widths.forEach((width, idx) => {
    sheet.getRange(`${colLetter(idx + 1)}:${colLetter(idx + 1)}`).format.columnWidthPx = width;
  });
}

function applyStatusFills(sheet, statusCol, firstDataRow, rows) {
  rows.forEach((row, idx) => {
    const status = row[statusCol - 1];
    const color = statusColors[status] || "#FFFFFF";
    sheet.getRange(`${colLetter(statusCol)}${firstDataRow + idx}`).format = {
      fill: color,
      font: { bold: true, color: "#111827" },
      horizontalAlignment: "center",
      verticalAlignment: "top",
      wrapText: true,
    };
  });
}

function addRowsSheet(workbook, name, headers, rows, widths, tableName, statusCol = null) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).values = [headers, ...rows];
  styleTable(sheet, 1, 1, rows.length + 1, headers.length, tableName);
  setWidths(sheet, widths);
  sheet.freezePanes.freezeRows(1);
  if (statusCol) applyStatusFills(sheet, statusCol, 2, rows);
  sheet.getRange(`A1:${colLetter(headers.length)}${rows.length + 1}`).format.rowHeightPx = 54;
  sheet.getRange(`A1:${colLetter(headers.length)}1`).format.rowHeightPx = 42;
  return sheet;
}

function countBy(rows, idx) {
  const out = new Map();
  rows.forEach((row) => out.set(row[idx], (out.get(row[idx]) || 0) + 1));
  return out;
}

async function build() {
  await fs.mkdir(outputDir, { recursive: true });
  const workbook = Workbook.create();

  const summary = workbook.worksheets.add("Executive Summary");
  summary.showGridLines = false;
  summary.getRange("A1:H1").merge();
  summary.getRange("A1").values = [["Akasha Delivery Tracker Refresh"]];
  summary.getRange("A1").format = {
    fill: "#0F172A",
    font: { bold: true, color: "#FFFFFF", size: 18 },
    verticalAlignment: "center",
  };
  summary.getRange("A1:H1").format.rowHeightPx = 34;
  summary.getRange("A2:H2").merge();
  summary.getRange("A2").values = [[
    "Client-facing phase/module tracker aligned to the current Akasha implementation, EOSDA baseline functionality, and active Bhoonidhi ResourceSat work.",
  ]];
  summary.getRange("A2").format = { fill: "#E0F2FE", wrapText: true, font: { color: "#0F172A" } };

  const roadmapStatus = countBy(roadmap, 9);
  const kpis = [
    ["Done", roadmapStatus.get("Done") || 0, "Implemented foundations and ready product surfaces."],
    ["Validated", roadmapStatus.get("Validated") || 0, "Staging/Coolify or real Bhoonidhi validation completed."],
    ["In Progress", roadmapStatus.get("In Progress") || 0, "Active ResourceSat/Bhoonidhi and source-neutral work."],
    ["Partial", roadmapStatus.get("Partial") || 0, "Backend or UI exists but EOS parity is incomplete."],
    ["Planned", roadmapStatus.get("Planned") || 0, "Scoped future modules."],
    ["Deferred", roadmapStatus.get("Deferred") || 0, "Blocked by external provider/access decision."],
  ];
  summary.getRange("A4:C10").values = [["Status", "Roadmap Rows", "Meaning"], ...kpis];
  styleTable(summary, 4, 1, 7, 3, "SummaryStatusTable");
  applyStatusFills(summary, 1, 5, kpis);
  setWidths(summary, [150, 105, 360, 180, 170, 170, 170, 170]);
  summary.getRange("E4:H4").merge();
  summary.getRange("E4").values = [["Current Implementation Snapshot"]];
  styleHeader(summary.getRange("E4:H4"), "#0F766E");
  const snapshot = [
    ["Basemap", "ArcGIS/Esri remains the visual basemap; ResourceSat FCC is overlay-only."],
    ["Ready screen", "Field Analytics / MapPage is the main implemented product workspace."],
    ["Validated", "Coolify staging and Bhoonidhi diagnostic were validated from the staging VM."],
    ["Active work", "ResourceSat source-neutral masks, COG prep, full-AOI composites and sync."],
    ["EOS baseline", "Public EOSDA user guide, especially Seasonality and related modules."],
  ];
  summary.getRange("E5:H9").values = snapshot.map(([a, b]) => [a, b, null, null]);
  summary.getRange("E5:E9").format = { fill: "#F8FAFC", font: { bold: true } };
  summary.getRange("F5:H9").merge(true);
  summary.getRange("E5:H9").format = {
    wrapText: true,
    verticalAlignment: "top",
    borders: { preset: "all", style: "thin", color: "#D1D5DB" },
  };

  summary.getRange("A12:H12").merge();
  summary.getRange("A12").values = [["Owners"]];
  styleHeader(summary.getRange("A12:H12"), "#374151");
  summary.getRange("A13:C17").values = [
    ["Role", "Owner", "Primary Scope"],
    ["Frontend", "Rafiq", "SPA screens, map interactions, EOS-parity UI"],
    ["Backend/API", "Sanoj", "BFF, auth, product APIs, analytics contracts"],
    ["Fullstack", "Deva", "Data workflows, integrations, UI/API joins"],
    ["Architect / Fullstack / DevOps", "Nishanth", "Architecture, DevOps, Coolify, ingestion orchestration"],
  ];
  styleTable(summary, 13, 1, 5, 3, "OwnerLegendTable");

  summary.getRange("E13:H13").merge();
  summary.getRange("E13").values = [["Baseline Sources"]];
  styleHeader(summary.getRange("E13:H13"), "#374151");
  summary.getRange("E14:H18").values = sourceUrls.map(([label, url]) => [label, url, null, null]);
  summary.getRange("F14:H18").merge(true);
  summary.getRange("E14:H18").format = {
    wrapText: true,
    verticalAlignment: "top",
    borders: { preset: "all", style: "thin", color: "#D1D5DB" },
  };

  const chart = summary.charts.add("bar", summary.getRange("A4:B10"));
  chart.title = "Roadmap Rows by Status";
  chart.hasLegend = false;
  chart.setPosition("E20", "H36");

  const deliverySheet = addRowsSheet(
    workbook,
    "Delivery Roadmap",
    roadmapHeaders,
    roadmap,
    [210, 190, 210, 330, 260, 310, 270, 225, 70, 100, 330, 260, 240],
    "DeliveryRoadmapTable",
    10,
  );
  roadmap.forEach((row, idx) => {
    const color = phaseColors[row[0]] || "#4B5563";
    deliverySheet.getRange(`A${idx + 2}`).format = {
      fill: color,
      font: { bold: true, color: "#FFFFFF" },
      wrapText: true,
      verticalAlignment: "top",
    };
  });

  addRowsSheet(
    workbook,
    "Built Inventory",
    builtInventoryHeaders,
    builtInventory,
    [180, 410, 110, 330, 230, 280],
    "BuiltInventoryTable",
    3,
  );

  addRowsSheet(
    workbook,
    "EOS Feature Mapping",
    eosHeaders,
    eosMapping,
    [190, 330, 135, 330, 330, 230, 80],
    "EOSFeatureMappingTable",
    3,
  );

  addRowsSheet(
    workbook,
    "Bhoonidhi ResourceSat Plan",
    bhoonidhiHeaders,
    bhoonidhiPlan,
    [190, 330, 120, 230, 360, 330],
    "BhoonidhiPlanTable",
    3,
  );

  addRowsSheet(
    workbook,
    "Risks & Decisions",
    riskHeaders,
    risks,
    [150, 430, 110, 230, 430],
    "RisksDecisionsTable",
    3,
  );

  const sheetsToRender = [
    "Executive Summary",
    "Delivery Roadmap",
    "Built Inventory",
    "EOS Feature Mapping",
    "Bhoonidhi ResourceSat Plan",
    "Risks & Decisions",
  ];
  for (const sheetName of sheetsToRender) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(
      path.join(outputDir, `${sheetName.replaceAll(" ", "_")}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }

  const summaryInspect = await workbook.inspect({
    kind: "table",
    range: "Executive Summary!A1:H18",
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 8,
    maxChars: 6000,
  });
  console.log(summaryInspect.ndjson);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
    maxChars: 4000,
  });
  console.log(errors.ndjson);

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  console.log(`EXPORT ${outputPath}`);
}

await build();
process.exit(0);
