# Growth Stages — Simple Plan

> **Status:** Planning  
> **Date:** 2026-08-13  
> **Rule:** Finish backend/API first. UI only after API works.

API details: [feature-growth-stages-api.md](./feature-growth-stages-api.md)

---

## 1. What we already have

| Table | Meaning |
|-------|---------|
| `crops` | Crop list (Rice, Wheat, …) |
| `crop_growth_stages` | Default growth stages for each crop (name + duration) — already in code/migration |
| `vegetation_cycles` | One real crop planting on a field (field + season + year + crop + sowing/harvest) |

---

## 2. What we add now

### New tables: **1**

**`vegetation_cycle_growth_stages`**

This is the only new table.  
It stores the growth stages **for a vegetation cycle** after the user starts entering dates.

| Column | Why |
|--------|-----|
| `id` | Primary key (uuid) |
| `vegetation_cycle_id` | Which vegetation cycle |
| `crop_id` | Which crop (same crop as the cycle; stored for easy query/filter) |
| `seq` | Stage order (1, 2, 3…) |
| `name` | Stage name (copied from crop default when first saved) |
| `duration` | Reference duration text (copied from crop default) |
| `start_date` | User-entered start date |
| `created_at` / `updated_at` | Audit |

**No other new tables for MVP.**

---

## 3. How it works (product flow)

### Step 1 — Show list from crop defaults (read only)

When user opens Growth Stages for a vegetation cycle:

1. We know the cycle’s crop (`vegetation_cycles.crop_id`).
2. We load default stages from **`crop_growth_stages`** for that crop.
3. UI shows the list: **name + duration**.
4. At this point there may be **no rows yet** in `vegetation_cycle_growth_stages`.

```text
User opens Growth Stages
        │
        ▼
crop_growth_stages  (for this crop)
  1 Germination   0-21
  2 Tillering     35-65
  3 Flowering     85-100
        │
        ▼
UI shows this list (no user dates yet)
```

### Step 2 — User adds start dates → save new rows

When user enters start date(s) and saves **the first time**:

1. Create rows in **`vegetation_cycle_growth_stages`**.
2. Each row stores:
   - `vegetation_cycle_id`
   - `crop_id`
   - `seq`, `name`, `duration` (from crop default)
   - `start_date` (what user entered; can be null for stages not filled yet)

```text
User enters dates and saves
        │
        ▼
INSERT vegetation_cycle_growth_stages
  cycle_id | crop_id | seq | name        | duration | start_date
  C1       | Rice    | 1   | Germination | 0-21     | 2026-06-01
  C1       | Rice    | 2   | Tillering   | 35-65    | 2026-06-20
  C1       | Rice    | 3   | Flowering   | 85-100   | null
```

### Step 3 — User edits dates later → update same rows

When user opens Edit again and changes dates:

1. Rows already exist in `vegetation_cycle_growth_stages`.
2. **UPDATE** `start_date` (and `updated_at`) on those rows.
3. Do not recreate the whole list unless crop changes (see below).

```text
User changes Tillering start → 2026-06-22
        │
        ▼
UPDATE vegetation_cycle_growth_stages
  SET start_date = 2026-06-22
  WHERE id = stage-row-2
```

---

## 4. Read rule (important)

When loading Growth Stages for a cycle:

| Situation | What to show |
|-----------|----------------|
| **No rows** in `vegetation_cycle_growth_stages` yet | Show defaults from `crop_growth_stages` (names + durations, no dates) |
| **Rows exist** for this cycle | Show saved rows (name + duration + start_date) |

So:

- First visit = crop template list  
- After user saves dates = cycle table becomes source of truth for that cycle  

---

## 5. Other rules

| Event | Behavior |
|-------|----------|
| User never sets dates | Only crop defaults are shown; cycle growth-stage table stays empty |
| User saves dates | Insert cycle stage rows (name, duration, start_date) |
| User edits dates | Update `start_date` on existing rows |
| User changes crop on vegetation cycle | Delete old cycle stage rows (if any). Next view shows new crop defaults. User must save dates again for the new crop |
| Crop default list updated in seed/JSON | Changes `crop_growth_stages` only. Existing saved cycle rows are **not** auto-changed |

### Date rule

- User sets **start date** only.
- **No end date** for now (not stored, not returned, not shown in UI).

### MVP does not include

- End date (stored or calculated)
- User add/remove/rename custom stages
- Auto-fill dates from duration text
- BBCH / chart overlays

---

## 6. Picture (all tables)

```text
crops
  id=14  name=Rice
    │
    ├── crop_growth_stages          ← defaults (already exist / seed from JSON)
    │     seq name          duration
    │     1   Germination   0-21
    │     2   Tillering     35-65
    │
    └── vegetation_cycles           ← already exist
          id=C1  field=...  crop_id=14  sowing/harvest
            │
            └── vegetation_cycle_growth_stages   ← NEW (only when user saves dates)
                  vegetation_cycle_id=C1
                  crop_id=14
                  seq, name, duration, start_date
```

---

## 7. Work order

### Phase A — Backend / API first

1. Confirm `crop_growth_stages` seeded from `crop-akasha.json`
2. Add model + migration for `vegetation_cycle_growth_stages`  
   (`vegetation_cycle_id` + `crop_id` + seq/name/duration/start_date)
3. Crop APIs return default stages
4. Field/cycle read APIs:
   - if cycle has saved stages → return them  
   - else → return crop defaults (with null dates)
5. Save/update API:
   - first save → insert rows  
   - later save → update start dates
6. Backend tests

Details: [feature-growth-stages-api.md](./feature-growth-stages-api.md)

### Phase B — UI after API works

1. Show stage list (from API)
2. Empty state: names/durations, no dates
3. Edit/add start dates → call save API
4. Edit again → call update path (same API)

---

## 8. One-line summary

> Show growth stages from the **crop defaults** first.  
> When the user adds dates, **insert** into one new table `vegetation_cycle_growth_stages`  
> (`vegetation_cycle_id` + `crop_id` + name + duration + `start_date`).  
> Later edits **update** those start dates.
