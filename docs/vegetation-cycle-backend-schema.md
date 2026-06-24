# Vegetation Cycle — Transaction Table Schema & CRUD Integration

## Design Decisions (confirmed)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | veg cycle data location | **Own table** `akasha.vegetation_cycles` | Field table stays untouched; normalized schema |
| 2 | API surface | **Inside field POST/PATCH** as optional `yearsData` array | Atomicity — field + veg cycles in one transaction |
| 3 | Replace strategy | **Delete-all-insert-new** when `yearsData` present | Matches existing FieldSeason pattern; client always sends complete list |
| 4 | `yearsData` field | **Separate section** in body, not mixed into field properties | Clean separation of concerns |
| 5 | Model location | **`models.py`** | Consistent with all other models |
| 6 | Endpoints | **Both POST and PATCH** accept `yearsData` | Same as `seasonIds` pattern |

---

## 1. Target Schema

All tables in `akasha` schema.

### New table: `vegetation_cycle`

| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK, `gen_random_uuid()` |
| field_id | uuid | FK → akasha.fields.id ON DELETE CASCADE, NOT NULL |
| season_id | uuid | FK → akasha.seasons.season_id ON DELETE CASCADE, NOT NULL |
| year | integer | NOT NULL |
| crop_id | integer | FK → akasha.crops.id ON DELETE RESTRICT, NOT NULL |
| variety_id | integer | FK → akasha.varieties.id ON DELETE RESTRICT, nullable |
| sowing_date | date | nullable |
| harvesting_date | date | nullable |
| target_yield | double precision | nullable |
| actual_yield | double precision | nullable |
| irrigation_type_id | integer | FK → akasha.irrigation_types.id ON DELETE RESTRICT, nullable |
| tillage_type_id | integer | FK → akasha.tillage_types.id ON DELETE RESTRICT, nullable |
| maturity | text | nullable |
| fertilizer | text | nullable |
| hybrid | text | nullable |
| ndvi_list | text | nullable |
| notes | text | nullable |
| is_cut_off | boolean | nullable |
| user_id | uuid | FK → akasha.users.id ON DELETE CASCADE, NOT NULL |
| created_at | timestamptz | NOT NULL, default now() |
| updated_at | timestamptz | NOT NULL, default now() |

**Unique constraint:** `(field_id, season_id, year, crop_id)`

**Indexes:** `vegetation_cycles_field_idx` (field_id), `vegetation_cycles_season_idx` (season_id), `vegetation_cycles_user_idx` (user_id)

---

## 2. API Contract

### POST `/api/fields` — Create field with optional veg cycles

```json
{
  "name": "Field 7",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "areaHa": 0.34,
  "seasonIds": ["<uuid>"],
  "yearsData": [
    {
      "seasonId": "<uuid>",
      "year": 2026,
      "cropType": 269,
      "cropVariety": 110626,
      "sowingDate": "2026-01-02",
      "harvestingDate": "2026-06-10",
      "targetYield": 1.0,
      "actualYield": 0.4,
      "irrigationType": 10,
      "tillageType": 8,
      "maturity": null,
      "fertilizer": "",
      "hybrid": null,
      "ndviList": "",
      "notes": "saddasdada",
      "isCutOff": null
    }
  ]
}
```

### PATCH `/api/fields/{id}` — Update field, optionally replace veg cycles

- `yearsData` present → replace all veg cycles for this field
- `yearsData` absent → leave existing veg cycles untouched

### Response `FieldResponse`

```json
{
  "id": "<uuid>",
  "name": "Field 7",
  "seasons": [{ "seasonId": "<uuid>", "name": "rainy", "canDelete": true }],
  "yearsData": [
    {
      "id": "<uuid>",
      "seasonId": "<uuid>",
      "year": 2026,
      "cropType": 269,
      "cropVariety": 110626,
      "sowingDate": "2026-01-02",
      "harvestingDate": "2026-06-10",
      "targetYield": 1.0,
      "actualYield": 0.4,
      "irrigationType": 10,
      "tillageType": 8,
      "maturity": null,
      "fertilizer": "",
      "hybrid": null,
      "ndviList": "",
      "notes": "saddasdada",
      "isCutOff": null,
      "createdAt": "2026-06-24T00:00:00Z",
      "updatedAt": "2026-06-24T00:00:00Z"
    }
  ],
  "createdAt": "...",
  "updatedAt": "..."
}
```

---

## 3. Transactional Integrity

```
session_scope():
    1. Create / update Field row
    2. Replace FieldSeason links
    3. If yearsData:
         a. Validate FK refs (crop, variety, irrigation, tillage)
         b. DELETE all existing VegetationCycle rows for this field
         c. INSERT new VegetationCycle rows
    4. commit  ← all or nothing
```

Any failure in steps 1–3 rolls back the entire operation. No orphan data.

---

## 4. Implementation Steps

| # | Step | Files | What to do |
|---|------|-------|------------|
| 1 | ORM model | `models.py` | Add `VegetationCycle` class (UuidPkMixin + TimestampMixin, all columns + FKs + unique constraint + indexes) |
| 2 | Migration | `alembic/versions/20260624_0004_vegetation_cycle.py` | `create_all` in upgrade; `DROP TABLE` in downgrade |
| 3 | Pydantic schemas | `schemas/fields.py` | `VegetationCycleCreate`, `VegetationCycleResponse`; add `yearsData` to `FieldCreate`, `FieldUpdate`, `FieldResponse` |
| 4 | Repo logic | `repositories/fields_repo.py` | `_validate_vegetation_cycles()`, insert/delete inside `create_field()` / `update_field()`; add `yearsData` to `_row_to_field()` |
| 5 | Apply migration | CLI | `python -m app.cli db upgrade` |
| 6 | Run tests | CLI | `cd apps/api && python -m pytest -q` |
| 7 | Frontend types | `types/api.ts` | `VegetationCyclePayload`; `yearsData` on `Field`, `FieldCreatePayload`, `FieldUpdatePayload` |
| 8 | Frontend hook | `hooks/useVegetationCycles.ts` | Update `VegetationCycleForm` to match API shape |
| 9 | Dialog save | `EditFieldDialog.tsx` | `handleSave` passes `yearsData` |
| 10 | Parent handler | `GlobalViewPanel.tsx` | Pass `yearsData` to mutation |

---

## 5. Dependency Graph

```
vegetation_cycle
├── field_id              → fields.id                (UUID)
├── season_id             → seasons.season_id         (UUID)
├── crop_id               → crops.id                  (integer)
├── variety_id            → varieties.id              (integer, nullable)
├── irrigation_type_id    → irrigation_types.id       (integer, nullable)
├── tillage_type_id       → tillage_types.id          (integer, nullable)
└── user_id               → users.id                  (UUID)
```

All referenced tables already exist. No new reference data needed.
