# Module 02 — Tools for Working with Fields & Tasks

Guide page: <https://eos.com/user-guide/crop-monitoring/tools-to-work-with-fields-and-tasks/>

## Purpose
Shared list-management utilities that operate on BOTH the Fields list and the
Scouting tasks list. These are cross-cutting helpers used throughout the product to
find, narrow, and jump to a specific field or task quickly.

## Sub-features

### 2.1 Filters
- Customizable search criteria applied to the Fields list or Scouting tasks list
  (toggle which list via the Monitoring/Scouting tab).
- Filter dimensions: **crop name** and **group name**.
- UI: a panel of checkboxes; user checks/unchecks values, then clicks **APPLY**.
- Used as the entry point for narrowing the multi-field map Layers as well
  (cross-referenced by Work with Crop Map layers).

### 2.2 Sorting
- Reorders the Fields list or Scouting tasks list.
- Available orders: Newest, Oldest, field name ascending, field name descending,
  field area Low→High, field area High→Low.
- UI: sorting control on the right of the list.

### 2.3 Field Search
- Free-text search to locate a specific field or task by name without scrolling.
- Applies to fields or to scouting tasks (depending on active tab).

### 2.4 Field Card
- Compact profile of a single field showing its core data:
  - Field name
  - Area / "square" (in ha)
  - Group (shown only if the field belongs to a group)
  - Crop (currently growing crop)
  - Location (district and country)
- The card is the per-field list item and the launch point for actions (e.g. Find field).

### 2.5 Find Field button
- Instantly zooms the map to a specific field.
- Works within whichever multi-field layer is active (My Crops, Vegetation, Water
  Stress, Vegetation Rating, Crop Classification) — i.e. it frames the field while
  preserving the current analytical layer.
- Lets the user view several adjacent fields within an AOI at once (glanceable area
  status) instead of opening field cards one by one — e.g. water-stress across
  neighbors.
- Also a "return to field" convenience: after zooming/scrolling away, press Find
  field to re-center and zoom back to the field.

## States / notes
- All four list tools (filter, sort, search, card) are shared by the Fields and the
  Scouting lists, so the replica should build them as a reusable list component
  parameterized by data source (fields vs tasks).
- Default tab is Monitoring (Fields); Scouting tab switches the same tools to tasks.

## Notes for replica
- Implement as a generic "entity list" with: search box, sort dropdown, filter
  panel (crop + group facets), and a card renderer. Field card fields map cleanly to
  existing field metadata (name, areaHa, group, crop, district/country location).
- "Find field" = map fly-to bounds of the field geometry, preserving active overlay.
