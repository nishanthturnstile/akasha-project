# Module 08 — Scouting

Guide page: <https://eos.com/user-guide/crop-monitoring/scouting/>

## Purpose
Create, assign, and complete on-the-ground field inspection tasks, and capture the
inspection results as a structured report. Tasks appear on the map and in the
Scouting list (which reuses the shared filter/sort/search tools from module 02).
Tightly coupled with Team Management (who creates vs. who scouts).

## Sub-features

### 8.1 Task Description (General / Report split)
- Selecting a task on the **Scouting** tab opens it split into two views:
  **General** and **Report**.

### 8.2 General (task owner's view)
- For the person who sets the task. Allows:
  - edit task **name** / **description**
  - upload a **field photo**
  - **close** the task when completed

### 8.3 Report (scout's view)
- For the scout performing the inspection. Captures:
  - **inspection date**
  - **client** (e.g. field owner) and **field number**
  - field **area**, **crop name**, **hybrid**, **sowing date**
  - **developmental phases** with **root thickness** and **leaf count**
  - **plant density**
  - **final review** of crop state + an **expert comment**
- The assignee then **closes** the task (if complete) or **updates** it.

### 8.4 Download / Export
- **Export** button at the top of the Task tab → report as a spreadsheet
  (processed automatically).

### 8.5 Closed Tasks
- Completing a task auto-moves it to the **Closed** tab of the task list and shows it
  as closed on the map.

## Roles & lifecycle (cross-ref Team Management, module 14)
- Task creators (owner/admin/scout) vs. assignees who complete; Observer can only
  complete tasks assigned to them.
- Lifecycle: created → assigned → (in progress) → closed (or updated).

## Notes for replica
- Data model: `ScoutTask { id, fieldId, name, description, photo, assigneeId,
  status(open/closed) }` + `ScoutReport { date, client, fieldNumber, area, crop,
  hybrid, sowingDate, phases[{rootThickness, leafCount}], plantDensity, review,
  comment }`.
- Two-audience UI: General (owner) vs Report (scout) tabs on the same task.
- Map integration: open vs closed task pins; list uses shared list tools (module 02).
- Export = spreadsheet of the report.
