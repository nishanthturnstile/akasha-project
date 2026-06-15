import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = process.cwd();
const outputDir = path.join(repoRoot, "outputs", "akasha-delivery-tracker-refresh");
const inputPath = path.join(outputDir, "Akasha Delivery Tracker Refresh.xlsx");
const outputPath = path.join(outputDir, "Akasha Delivery Tracker Refresh - EOS Parity Reviewed.xlsx");

const blob = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(blob);

function sheet(name) {
  return workbook.worksheets.getItem(name);
}

function appendRows(sheetName, rows) {
  const ws = sheet(sheetName);
  const table = ws.tables.items?.[0];
  if (table?.rows?.add) {
    table.rows.add(null, rows);
    return;
  }
  const used = ws.getUsedRange(true);
  const startRow = used.rowIndex + used.rowCount;
  ws.getRangeByIndexes(startRow, 0, rows.length, rows[0].length).values = rows;
}

function writeCell(sheetName, address, value) {
  sheet(sheetName).getRange(address).values = [[value]];
}

writeCell("Executive Summary", "B8", 14);
writeCell("Executive Summary", "B9", 7);
writeCell("Executive Summary", "B10", 4);
writeCell(
  "Executive Summary",
  "F9",
  "EOS baseline expanded after detailed user-guide review: season guardrails, upload manager, field/task utilities, terrain layers, advanced indices, VRA savings, and team/settings/API hardening.",
);

const roadmapRows = [
  [
    "Phase 2 - Core EOS Monitoring Parity",
    "Field list, map search and workspace utilities",
    "Tools For Working With Fields And Tasks; Work With Crop Map",
    "Replicate EOS field/task navigation utilities: filters, sorting, search, field cards, find-field, find-location, zoom controls, measurements, split view, layers and contrast view.",
    "Field/task list filters, sorting, search, field card states, find-field/focus behavior, map search/location control, zoom tool affordances, split/contrast mode.",
    "BFF supports filtered/sorted field/task lists and stable map/field lookup contracts where UI cannot derive state locally.",
    "Frontend interaction tests and API filter/sort contract tests.",
    "Frontend - Rafiq; Backend/API - Sanoj",
    "P1",
    "Partial",
    "A user can locate fields/tasks quickly, filter/sort lists, focus the map from a field card, measure areas/distances, and compare layers using split/contrast tools.",
    "Existing field/task APIs and map metadata.",
    "Added after EOS guide review because these utilities were previously only implied by broad map/workspace rows.",
  ],
  [
    "Phase 2 - Core EOS Monitoring Parity",
    "Terrain layers and monitoring metadata",
    "Monitoring: elevation map; slope map; date line hover; cloud/shadow threshold; downloads",
    "Add terrain/elevation/slope monitoring parity where data/provider support is available, and expose richer date-line metadata.",
    "Elevation/slope layer entries, legends, hover values, TIFF download controls, date hover with cloud/shadow percentage and acquisition time, cloud/shadow threshold settings.",
    "DEM/terrain data source or provider adapter, terrain raster registration, source/date metadata fields, cloud/shadow threshold persistence.",
    "Data-source validation, tile/download smoke, threshold contract tests.",
    "Backend/API - Sanoj; Frontend - Rafiq; Architect / Fullstack / DevOps - Nishanth",
    "P2",
    "Planned",
    "Users can select elevation/slope layers, inspect values/legend, download outputs and understand image cloud/shadow metadata from the timeline.",
    "DEM/terrain source and cloud-threshold product decision.",
    "Sentinel/ResourceSat imagery parity can proceed before terrain layers; this is explicit EOS parity, not current launch gate.",
  ],
  [
    "Phase 2 - Core EOS Monitoring Parity",
    "Advanced indices and crop capability matrix",
    "Monitoring indexes: VMI, ReCI, available features for crops, yield estimation add-on",
    "Document and implement only source-supported advanced indices; defer proprietary/add-on behavior until formulas/data/license are confirmed.",
    "Index availability matrix by source/crop, disabled states for unsupported indices, crop feature matrix for disease risk/growth stages/weather risk/yield add-on availability.",
    "ReCI for sources with red-edge support, explicit unsupported response for ResourceSat, optional custom-index registry, crop capability metadata.",
    "Contract tests for supported/unsupported index behavior and crop-feature matrix fallbacks.",
    "Backend/API - Sanoj; Frontend - Rafiq; Team Lead - Karthi",
    "P3",
    "Deferred",
    "Unsupported indices are hidden or clearly disabled; supported advanced indices produce correct stats; VMI/yield add-on are not claimed without approved formula/data.",
    "Client decision on VMI formula, crop capability taxonomy, and whether yield-estimation add-on is in scope.",
    "ResourceSat LISS-3 cannot support red-edge indices such as NDRE/ReCI because it has no red-edge band.",
  ],
  [
    "Phase 3 - Seasonality & Field Manager",
    "Season rules and field transfer guardrails",
    "Seasonality: copy fields, edit/delete season, default season, season-driven analytics timeframe",
    "Complete EOS season behavior beyond CRUD: copy fields from a previous season, transfer fields on delete, enforce at least one season per field, and keep analytics bounded by season dates.",
    "Create/edit/delete season flows with copy-from-season toggle, field selection/removal guardrails, warnings when season dates affect sowing/harvest dates, season-scoped timeline behavior.",
    "Season deletion transfer logic, default season bootstrap, field-season invariants, date-bound analytics filters, sowing/harvest date adjustment rules.",
    "API tests for deletion/transfer, date edits, default season, and analytics timeframe filters; UI workflow tests.",
    "Backend/API - Sanoj; Frontend - Rafiq",
    "P1",
    "Partial",
    "A field always belongs to at least one season; deleting/editing a season preserves field continuity and analytics follow the selected season timeframe.",
    "Existing season lifecycle UI/API and crop metadata model.",
    "Added after reviewing the Seasonality guide in detail.",
  ],
  [
    "Phase 3 - Seasonality & Field Manager",
    "Field upload manager and drawing tools",
    "Add field: SHP/KML/KMZ/GeoJSON upload, parameter mapping, error types, multiple draw, circle, cut boundary, latest image layer",
    "Replicate EOS field creation flow beyond current GeoJSON/draw basics, including upload validation and advanced drawing actions.",
    "Upload manager with drag/drop, column mapping, date format selector, season/crop/group matching, upload error messages, multi-field draw, circular boundary, cut/exclusion tool and latest-image search during field creation.",
    "SHP/KML/KMZ parser, zip/shapefile validation, .prj handling, polygon-only validation, size/intersection/area limits, parameter mapping and season/crop/group assignment.",
    "Parser tests with valid/invalid fixtures, geometry validation tests, UI upload/drawing workflow tests.",
    "Frontend - Rafiq; Backend/API - Sanoj; Fullstack - Deva",
    "P1",
    "Partial",
    "Users can upload supported field formats with clear EOS-style validation, map columns to field metadata, draw multiple/circular/cut boundaries and save them to field list.",
    "Supported format priorities and file-size limit confirmation.",
    "Current Akasha supports drawing/editing and GeoJSON-oriented import/export; this row captures missing EOS parity details.",
  ],
  [
    "Phase 8 - VRA Maps",
    "VRA savings calculation and saved-map library",
    "VRA maps: calculate savings on variable-rate application; save created maps",
    "Add the EOS VRA follow-through after map generation: input rates by zone, calculate material savings and maintain saved VRA maps.",
    "Zone rate inputs, savings summary, saved-map list/detail, rename/delete/download actions.",
    "Persist VRA maps, zone rates, total input requirement, savings calculation and export metadata.",
    "Golden calculation tests, saved-map CRUD tests and export regression tests.",
    "Fullstack - Deva; Frontend - Rafiq",
    "P3",
    "Planned",
    "Users can save generated VRA maps, reopen them and see transparent savings calculations by zone.",
    "VRA map builder and client-approved units/export formats.",
    "Separated from base VRA map generation so commercial/agronomy assumptions are explicit.",
  ],
  [
    "Phase 9 - Production Hardening",
    "Team management, settings and API parity hardening",
    "Team Management; Settings; Account and Pricing; Access Through API",
    "Turn existing auth/account/API-key foundation into client-ready EOS-style admin/settings surfaces where in scope.",
    "Team invitation/add-user workflow, roles dashboard, actions, edit team name, switch team, settings/preferences, API access documentation view.",
    "Invitation/user-management APIs where missing, role enforcement audit, settings persistence, API key usage/rate-limit documentation.",
    "RBAC tests, settings tests, invite flow smoke, API key security checks.",
    "Backend/API - Sanoj; Frontend - Rafiq; Team Lead - Karthi",
    "P2",
    "Partial",
    "Client admins can manage team access and settings, and developers can understand API key usage without exposing internal service credentials.",
    "Linear/team member additions and client decision on whether Account/Pricing/Gift Field concepts are in scope.",
    "Existing auth shell remains Done; this row tracks EOS admin/settings parity that was previously under-mapped.",
  ],
];

appendRows("Delivery Roadmap", roadmapRows);

const mappingRows = [
  [
    "Field/Task List Utilities",
    "Filters, sorting, search, field card and find-field button.",
    "Partial",
    "Some map/list foundations exist.",
    "Complete EOS-style list utility behavior and focused map navigation.",
    "Frontend - Rafiq; Backend/API - Sanoj",
    "P1",
    null,
  ],
  [
    "Crop Map Utilities",
    "Find location, zoom tool, distance/area measurements, split view, layers and contrast view.",
    "Partial",
    "MapLibre workspace has layer and measurement foundations.",
    "Finish find-location, field focus, split/contrast and layer UX parity.",
    "Frontend - Rafiq",
    "P1",
    null,
  ],
  [
    "Seasonality Guardrails",
    "Copy fields from season, transfer fields on delete, default season, field must remain in at least one season, season dates bound analytics.",
    "Partial",
    "Season and field-season schema exists.",
    "Implement copy/transfer/delete guardrails and season-scoped analytics timeline.",
    "Backend/API - Sanoj; Frontend - Rafiq",
    "P1",
    null,
  ],
  [
    "Add Field Upload Manager Details",
    "SHP/KML/KMZ/GeoJSON upload, parameter mapping, date formats, season/crop/group matching, error types, circle and cut drawing tools.",
    "Partial",
    "Draw/edit and GeoJSON-oriented import/export exist.",
    "Build upload manager, parsers, validation errors, circular drawing and cut/exclusion workflow.",
    "Frontend - Rafiq; Backend/API - Sanoj; Fullstack - Deva",
    "P1",
    null,
  ],
  [
    "Terrain Layers",
    "Elevation map, slope map, hover values, legend and TIFF download.",
    "Planned",
    "No explicit terrain layer provider/DEM pipeline in current implementation.",
    "Select DEM/terrain source and expose layer metadata, tiles and downloads.",
    "Backend/API - Sanoj; Architect / Fullstack / DevOps - Nishanth",
    "P2",
    null,
  ],
  [
    "Advanced Indices & Crop Capability Matrix",
    "VMI, ReCI, crop feature availability, weather/disease/growth/yield availability by crop.",
    "Deferred",
    "Core indices exist; source-specific unsupported handling is in progress.",
    "Confirm formulas/data/license; implement ReCI where bands exist; document/defer VMI/yield add-ons.",
    "Backend/API - Sanoj; Team Lead - Karthi",
    "P3",
    null,
  ],
  [
    "VRA Savings & Saved Maps",
    "Calculate savings on variable-rate application and save created maps.",
    "Planned",
    "Base VRA is planned.",
    "Add zone rate inputs, savings calculation and saved-map library after VRA generation.",
    "Fullstack - Deva; Frontend - Rafiq",
    "P3",
    null,
  ],
  [
    "Account Setup / Gift Field / Pricing",
    "Create account, gift field and account/pricing guide concepts.",
    "Deferred",
    "Akasha auth/account exists, but EOS commercial/pricing concepts are not Akasha feature requirements today.",
    "Treat as non-goal unless client explicitly asks to replicate onboarding/pricing/gift-field flows.",
    "Team Lead - Karthi",
    "P3",
    null,
  ],
];

appendRows("EOS Feature Mapping", mappingRows);

appendRows("Risks & Decisions", [
  [
    "External input",
    "VMI formula, crop feature matrix, yield-estimation scope and any proprietary EOS-style add-ons.",
    "Needed",
    "Team Lead - Karthi",
    "Required before claiming VMI/yield/crop-capability parity.",
    null,
  ],
  [
    "External input",
    "DEM/terrain source for elevation and slope layers.",
    "Needed",
    "Architect / Fullstack / DevOps - Nishanth",
    "Required before terrain layer implementation and TIFF downloads.",
    null,
  ],
  [
    "Non-goal",
    "EOS Gift Field and Account/Pricing commercial flows are not Akasha delivery scope unless the client explicitly requests them.",
    "Always",
    "Team Lead - Karthi",
    "Keep product tracker focused on operational farm-management parity.",
    null,
  ],
  [
    "Non-goal",
    "Do not mark EOS parity as 100% complete until every EOS Feature Mapping row is Done/Validated or explicitly accepted as Deferred/Non-goal by the client.",
    "Always",
    "Team Lead - Karthi",
    "Use the EOS Feature Mapping sheet as the checklist for parity signoff.",
    null,
  ],
]);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

for (const name of [
  "Executive Summary",
  "Delivery Roadmap",
  "EOS Feature Mapping",
  "Risks & Decisions",
]) {
  const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(
    path.join(outputDir, `${name.replace(/[^A-Za-z0-9]+/g, "_")}_EOS_Review.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
