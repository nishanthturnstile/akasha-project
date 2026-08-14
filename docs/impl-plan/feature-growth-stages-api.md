# Growth Stages — API Plan

> Overview: [feature-growth-stages-plan.md](./feature-growth-stages-plan.md)  
> **UI only after these APIs work.**

---

## 1. Goal

| Need | How |
|------|-----|
| Show default stages for the cycle’s crop | Read `crop_growth_stages` |
| First time user saves dates | **Insert** into `vegetation_cycle_growth_stages` (name, duration, start_date + cycle id + crop id) |
| User edits dates later | **Update** `start_date` on existing rows |
| Read for UI | If cycle has saved rows → return them; else return crop defaults |

---

## 2. New table (model)

### `vegetation_cycle_growth_stages`

| Column | Type | Notes |
|--------|------|--------|
| `id` | uuid PK | |
| `vegetation_cycle_id` | uuid FK → `vegetation_cycles.id` ON DELETE CASCADE | required |
| `crop_id` | int FK → `crops.id` ON DELETE RESTRICT | required; same crop as cycle |
| `seq` | int | order |
| `name` | text | copied from crop default on first save |
| `duration` | text null | copied from crop default |
| `start_date` | date null | user value |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Constraints**

- Unique `(vegetation_cycle_id, seq)`
- Index on `vegetation_cycle_id`
- Index on `crop_id` (optional but useful)

**ORM sketch**

```text
class VegetationCycleGrowthStage
  id
  vegetation_cycle_id
  crop_id
  seq
  name
  duration
  start_date
  created_at
  updated_at
```

---

## 3. Response shapes

### 3.1 Crop default stage

```json
{
  "id": 101,
  "seq": 1,
  "name": "Germination & Nursery",
  "duration": "0-21"
}
```

### 3.2 Cycle growth stage (for UI)

Used on vegetation cycle responses and on save response.

```json
{
  "id": "stage-uuid-or-null",
  "seq": 1,
  "name": "Germination & Nursery",
  "duration": "0-21",
  "startDate": "2026-06-01",
  "cropId": 14,
  "saved": true
}
```

| Field | Meaning |
|-------|---------|
| `id` | Saved row id if exists; `null` when still showing crop default only |
| `name` | Stage name |
| `duration` | Reference duration text |
| `startDate` | User start date, or `null` |
| `saved` | `true` if row exists in `vegetation_cycle_growth_stages` |
| `cropId` | Crop for this cycle |

**No `endDate` for now** (not stored, not calculated, not returned).

---

## 4. APIs we use

### A. Show crop default stages — extend existing

- `GET /api/crops`
- `GET /api/crops/{cropId}`

Add `stages` from `crop_growth_stages`:

```json
{
  "id": 14,
  "name": "Rice",
  "stages": [
    { "id": 101, "seq": 1, "name": "Germination & Nursery", "duration": "0-21" },
    { "id": 102, "seq": 2, "name": "Tillering", "duration": "35-65" }
  ]
}
```

---

### B. Show stages for a field cycle — extend existing

- `GET /api/fields/{fieldId}`
- `GET /api/fields/{fieldId}/vegetation-cycles`

Each vegetation cycle includes `growthStages`.

**Read logic**

```text
if cycle has rows in vegetation_cycle_growth_stages:
    return those rows (name, duration, startDate, id)
else:
    return crop_growth_stages for cycle.crop_id
    (id=null, startDate=null, saved=false)
```

Example — **before user saved any dates** (from crop defaults):

```json
{
  "id": "cycle-uuid",
  "cropType": 14,
  "cropName": "Rice",
  "sowingDate": "2026-06-01",
  "harvestingDate": "2026-10-15",
  "growthStages": [
    {
      "id": null,
      "seq": 1,
      "name": "Germination & Nursery",
      "duration": "0-21",
      "startDate": null,
      "cropId": 14,
      "saved": false
    }
  ]
}
```

Example — **after user saved dates**:

```json
{
  "id": "cycle-uuid",
  "cropType": 14,
  "growthStages": [
    {
      "id": "stage-uuid-1",
      "seq": 1,
      "name": "Germination & Nursery",
      "duration": "0-21",
      "startDate": "2026-06-01",
      "cropId": 14,
      "saved": true
    }
  ]
}
```

---

### C. Create field / vegetation cycle — existing write APIs

- `POST /api/fields`
- `PATCH /api/fields/{fieldId}`

**MVP behavior**

- Creating a vegetation cycle does **not** insert growth-stage rows automatically.
- Stages are only written when user saves dates (API D).
- If crop on a cycle changes and old saved stages exist → delete those cycle stage rows.

No extra growth-stage payload on field create in MVP.

---

### D. Save / update start dates — **new API**

```http
PATCH /api/vegetation-cycles/{cycleId}/growth-stages
```

This one API handles **first save (insert)** and **later edit (update)**.

#### Request

Client sends the full ordered stage list with start dates (from the list user sees):

```json
{
  "stages": [
    {
      "seq": 1,
      "name": "Germination & Nursery",
      "duration": "0-21",
      "startDate": "2026-06-01"
    },
    {
      "seq": 2,
      "name": "Tillering",
      "duration": "35-65",
      "startDate": "2026-06-20"
    },
    {
      "seq": 3,
      "name": "Flowering",
      "duration": "85-100",
      "startDate": null
    }
  ]
}
```

Optional: client may also send existing `id` when updating known rows.

#### Server behavior

```text
Load vegetation cycle → get crop_id

If NO rows exist yet for this cycle:
  INSERT one row per stage:
    vegetation_cycle_id, crop_id, seq, name, duration, start_date

If rows ALREADY exist for this cycle:
  UPDATE matching rows by id or seq:
    set start_date (and updated_at)
  (MVP: do not rename/reorder; names/durations stay as saved)
```

#### Response

Full `growthStages` list after save (same shape as read, with real ids).

#### Rules

- Auth: same as editing that field/cycle
- `crop_id` on rows = cycle’s current `crop_id`
- Start dates that are set should be in order by `seq` (no later stage before earlier)
- Partial empty dates allowed (`startDate: null`)

#### Errors

| Code | When |
|------|------|
| `VEGETATION_CYCLE_NOT_FOUND` | Bad cycle id |
| `GROWTH_STAGE_DATE_ORDER_INVALID` | Dates out of order by seq |
| `GROWTH_STAGE_NOT_FOUND` | Update referenced unknown id (if id sent) |

---

## 5. API summary (what we use)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/crops` | Crop list + default `stages` |
| `GET` | `/api/crops/{cropId}` | One crop + default `stages` |
| `GET` | `/api/fields/{fieldId}` | Field + cycles + `growthStages` (saved **or** crop defaults) |
| `GET` | `/api/fields/{fieldId}/vegetation-cycles` | Same `growthStages` logic |
| `POST` / `PATCH` | `/api/fields` … | Create/update cycles; clear cycle stages if crop changes |
| `PATCH` | `/api/vegetation-cycles/{cycleId}/growth-stages` | **First save = insert, later = update start dates** |

---

## 6. Backend build steps

| Step | Work | Done when |
|------|------|-----------|
| 1 | Ensure `crop_growth_stages` seeded from JSON | Defaults exist per crop |
| 2 | Model + migration for `vegetation_cycle_growth_stages` with `vegetation_cycle_id` + `crop_id` | Table exists |
| 3 | Extend crop GET with `stages` | Defaults readable |
| 4 | Read helper: saved stages else crop defaults | Field/cycle GET correct |
| 5 | PATCH save: insert if empty, update if exists | Dates persist |
| 6 | Crop change on cycle clears saved stages | No wrong crop stages left |
| 7 | Tests | Cases below pass |

### Tests

1. Cycle with no saved stages → GET returns crop default **name + duration**, `startDate` null (no end date)  
2. First PATCH with dates → rows inserted with `vegetation_cycle_id` + `crop_id` + name + duration + start_date  
3. Second PATCH → start dates updated, same row ids  
4. GET after save → returns saved rows with name + duration + startDate only  
5. Out-of-order start dates → error  
6. Change cycle crop → saved stages deleted; GET shows new crop defaults  
7. Update crop template seed → already-saved cycle rows unchanged  

---

## 7. What UI will call (later)

| UI action | API |
|-----------|-----|
| Open Growth Stages card | `GET /api/fields/{fieldId}` → `vegetationData[].growthStages` |
| First time set dates + Save | `PATCH /api/vegetation-cycles/{cycleId}/growth-stages` (insert) |
| Edit dates + Save | same PATCH (update) |
| Optional: crop picker defaults | `GET /api/crops` |

---

## 8. One-line API summary

> **Show** stages from crop defaults until the user saves.  
> **Save** creates rows in `vegetation_cycle_growth_stages` (`vegetation_cycle_id` + `crop_id` + name + duration + `start_date`).  
> **Edit** updates those start dates.
