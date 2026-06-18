# EOSDA Crop Monitoring — Feature & Module Reference

Goal: build a complete, faithful replica of the **EOSDA Crop Monitoring** platform.
This folder is the **source-of-truth catalog** of every module and feature of that
platform, reverse-engineered from the official user guide.

Primary source: <https://eos.com/user-guide/crop-monitoring/> (and its per-module
sub-pages, linked per module).

## How this is organized

We capture the platform **breadth-first**:

1. **Phase 1 — High-level module inventory (done).** Every top-level module
   (sidebar / panel item) and, under each, the immediate sub-features it contains.
   Goal: miss nothing. See
   [01-high-level-module-inventory.md](01-high-level-module-inventory.md).
2. **Phase 2 — Per-module deep dives (done).** One document per module under
   [modules/](modules/) fully specifying behavior, UI, states, inputs/outputs, edge
   cases, and implementation notes. (Pure EOS feature capture; Akasha gap analysis
   is deferred to a later pass.)
3. **Phase 3 — Source data tables (started).** Large tabular support data extracted
   from guide pages. Current data artifact:
   [Monitoring crop × feature matrix](data/crop-feature-support-matrix.md).

Legend for status columns:

- `captured` — listed at high level in Phase 1.
- `done` — expanded into a full module spec under `modules/`.

## Master module index

The 17 canonical guide pages below are the platform's high-level modules. Grouped
by functional area for readability; the **Guide page** column is the authoritative
top-level unit.

| # | Module | Functional area | Guide page | Deep-dive |
|---|--------|-----------------|-----------|-----------|
| 1 | Video Guide (onboarding) | Onboarding | `/video-guide/` | [done](modules/01-video-guide.md) |
| 2 | Tools for Working with Fields & Tasks | Map & Monitoring | `/tools-to-work-with-fields-and-tasks/` | [done](modules/02-tools-for-fields-and-tasks.md) |
| 3 | Work with Crop Map | Map & Monitoring | `/work-with-crop-map/` | [done](modules/03-work-with-crop-map.md) |
| 4 | Seasonality (Seasons) | Field Data Mgmt | `/seasonality/` | [done](modules/04-seasonality.md) |
| 5 | Add Field | Field Data Mgmt | `/add-field/` | [done](modules/05-add-field.md) |
| 6 | Fields / Monitoring (analytics) | Map & Monitoring | `/fields/` | [done](modules/06-fields-monitoring.md) |
| 7 | Weather | Analytics & Reporting | `/weather/` | [done](modules/07-weather.md) |
| 8 | Scouting | Planning & Operations | `/scouting/` | [done](modules/08-scouting.md) |
| 9 | Overview (Season Analytics, Leaderboard, Custom Report) | Analytics & Reporting | `/overview/` | [done](modules/09-overview.md) |
| 10 | VRA Maps (Zoning) | Planning & Operations | `/vra-maps/` | [done](modules/10-vra-maps.md) |
| 11 | Field Activity Log | Planning & Operations | `/field-activity-log/` | [done](modules/11-field-activity-log.md) |
| 12 | Data Manager (+ Connections) | Planning & Operations | `/data-manager/` | [done](modules/12-data-manager.md) |
| 13 | Field Manager (Crop Rotation, Field Groups) | Field Data Mgmt | `/field-manager/` | [done](modules/13-field-manager.md) |
| 14 | Team Management | Account & Platform | `/team-management/` | [done](modules/14-team-management.md) |
| 15 | Settings | Account & Platform | `/settings/` | [done](modules/15-settings.md) |
| 16 | Account & Pricing | Account & Platform | `/account-and-pricing/` | [done](modules/16-account-and-pricing.md) |
| 17 | Access Through API | Account & Platform | `/access-through-api/` | [done](modules/17-access-through-api.md) |

> Note: **Zoning** and **Field Leaderboard** appear as standalone items in the
> onboarding Video Guide, but in the product they live inside **VRA Maps** and
> **Overview** respectively. They are tracked as sub-features there (and
> cross-referenced) so nothing is lost.

## Conventions

- Descriptions are paraphrased from the official guide (not copied verbatim).
- Each feature is written so it can later become an implementable spec / ticket.
- Where the guide notes plan gating (Free / Essential / Professional / Enterprise /
  Add-on), we record it, since it affects feature availability.
