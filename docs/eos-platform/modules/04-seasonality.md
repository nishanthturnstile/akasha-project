# Module 04 — Seasonality (Seasons)

Guide page: <https://eos.com/user-guide/crop-monitoring/seasonality/>

## Purpose
Seasons make all platform data and analytics align to the user's real agricultural
calendar. A season is a named date range (start/end) that scopes which imagery,
crops, activities, and analytics are shown. Every field must belong to at least one
season. Reachable from the **Seasons** item in the side menu.

## Core concept (how seasonality affects the whole product)
- A season has a duration (start/end) chosen to match the user's farming schedule.
- All data/analytics render **within the selected season's timeframe**.
- After a season ends, **new field imagery stops appearing in the timeline** (tied
  to end of harvest / no crops in fields).
- To get current imagery + analytics for a new agricultural cycle, the user must
  create a new season and either add new fields to it or transfer existing fields
  from a completed season.
- To fully activate a season the user also: selects the fields with activities in
  that season, adds crops where planting is due, and schedules activities.

## Sub-features

### 4.1 Create Season
Side menu → Seasons → shows the list of all seasons → **+ Create season**. The
create dialog captures:
- **Season Name** — unique name.
- **Start Date – End Date** — duration; defaults to the current calendar year.
- **Copy fields from the season** (optional toggle) — pick an existing season to
  copy all its fields into the new one; leave off if not needed.
- **Field list** (bottom) — all account fields; choose which to include.
- On **Create season**, the new season appears in the list containing only the
  selected fields.

### 4.2 Edit Season
Seasons list → **Edit** next to a season. Editable:
- **Season Name**.
- **Season Duration** (start/end). Changing duration **auto-readjusts** sowing /
  harvesting dates of fields that fall outside the new range (crops cannot be sown
  before the season start). A warning is shown when this auto-adjust will happen.
- **Field list** — add/remove fields. Constraint: a field that belongs to **only
  one** season cannot be removed from that season (every field must always belong to
  ≥1 season).

### 4.3 Delete Season
Seasons list → **Delete** next to a season.
- The system always keeps **at least one** season (e.g. with 5, you may delete 4).
- Deleting a season removes all its data, but **fields are not deleted** from the
  account — only removed from that season.
- If a deleted season was a field's only season, the user is **prompted to choose a
  destination season** to transfer the field(s) to.

### 4.4 Default season (account bootstrap)
- On new-account registration the system auto-creates **one default season** matched
  to the current calendar season. It is editable but **cannot be removed**.

## Rules / invariants (important for replica)
- Invariant: **every field belongs to ≥1 season at all times.**
- Invariant: **≥1 season always exists in the account.**
- Editing a season's dates cascades to field sowing/harvest dates (clamp to season).
- Season scopes imagery/timeline, crops, activities, and analytics throughout the app.

## Notes for replica
- Data model: `Season { id, name, start, end, isDefault }`, with a many-to-many
  `field_season` join (fields ↔ seasons) carrying per-season crop/sowing data.
- Deletion flow needs the "reassign orphaned fields" prompt.
- The cascade-clamp on date edits is the trickiest behavior to replicate faithfully.
