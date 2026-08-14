# Bulk Creation — Create-or-Update Plan (Simple)

> **One-line goal:**  
> Find crop by **name** → create if missing, update if exists → refresh that crop’s **stages** from JSON.  
> Never skip just because the name exists. Never delete all crops.

---

## 1. Why we need this

### Today (problem)

In [`apps/api/app/bulk_creation.py`](../apps/api/app/bulk_creation.py):

| Case | What happens now |
|------|------------------|
| Crop name already in DB | Often **skipped** (no field update) |
| Same crop count in DB and JSON | **Skip entirely** even if JSON gained `stages` or new colors |
| Crop count changed | **Delete all** crops + varieties + vegetation_cycles, then re-insert |

So if we only **add growth stages** in JSON and crop **names stay the same**, the DB may never get those stages.

### What we want

```text
Names same + stages added in JSON
  → still run update
  → keep same crop row / same crop id
  → add or refresh stages for that crop
```

---

## 2. Core rule (easy)

**Match by name only. Not by every field.**

| Check | Used for |
|-------|----------|
| `name` (e.g. `"Wheat"`) | Find the crop: exists or not? |
| Other fields (color, seeding_type, stages…) | After find: **write** them from JSON |

```text
Look up crop by name
  missing  → create crop
  exists   → update crop fields from JSON
Then always refresh stages for that crop from JSON
```

There is no built-in FastAPI/SQLAlchemy `update_or_create`.  
We write this small logic ourselves in `bulk_creation.py`.

---

## 3. Current gap: stages are only in JSON, not in DB

| Layer | Stages status |
|-------|----------------|
| [`crop-akasha.json`](../scripts/data/crop-akasha.json) | **Yes** — each crop has `stages[]` |
| `Crop` model in [`models.py`](../apps/api/app/models.py) | **No** — no stages field, no stages relationship |
| DB table for stages | **No** — does not exist yet |
| `bulk_creation.generate_crops` | **Ignores** `stages` today |

**Important:** we do **not** put stages as a JSON column on `crops`.  
We add a **new child table** linked by `crop_id`, then migrate.

```text
crops (existing)
  id, name, color, seeding_type_id, ...

crop_growth_stages (NEW — needs migration)
  id, crop_id → crops.id, seq, name, duration
```

**Must do migration before** bulk creation can save stages.

---

## 4. Data we already have (JSON only)

Source file: [`scripts/data/crop-akasha.json`](../scripts/data/crop-akasha.json)

- 76 crops
- Each crop has `stages: [{ "name", "duration" }, ...]`
- ~650 stages total
- Stages belong **to each crop** (not a shared GrowthStageType)

Example:

```json
{
  "name_en": "Wheat",
  "color": "#F5DEB3",
  "seeding_type": 0,
  "stages": [
    { "name": "Germination & Emergence", "duration": "0-10" },
    { "name": "Tillering", "duration": "25-45" }
  ]
}
```

---

## 5. Target behavior

### Crops

```text
for each item in crop-akasha.json:
  name = item["name_en"]
  crop = DB find by name

  if crop is None:
      create Crop(name=name)
  else:
      use existing crop   # same id kept

  set from JSON:
    color, seeding_type_id, maturity_options,
    has_weather_risk, bbch_mode, characteristic, has_variety
```

### Stages (per crop)

```text
after crop row exists:
  delete stages for this crop_id only
  insert stages from JSON in order (seq = 1, 2, 3, ...)
```

- Parent crop is **not** deleted
- Only that crop’s stage rows are refreshed
- Simple and safe for reference data

### Real cases

| Situation | Result |
|-----------|--------|
| First login, empty DB | Create 76 crops + all stages |
| Login again, JSON unchanged | Find by name, rewrite same data (harmless, fast) |
| JSON adds stages, names same | Same crops kept → stages created/refreshed |
| JSON changes Wheat color | Wheat updated, **same id** |
| New crop added to JSON | That crop created + its stages |
| Crop renamed in JSON | Treated as new name (old name left as-is for v1) |

---

## 6. Performance (not a concern)

| Data | Count |
|------|------:|
| Crops | 76 |
| Stages | ~650 |

Expected: usually **under 1–2 seconds** on login/signup.

Optional later optimizations (not required for v1):

- One query loading all crops into a name→row map
- Skip rewrite if JSON file unchanged

---

## 7. What to build

### 7.1 FIRST: model + Alembic migration (required)

Stages are **not** on the `Crop` model today. Before any bulk stage save:

1. Add ORM model `CropGrowthStage` in [`models.py`](../apps/api/app/models.py)
2. Add Alembic revision creating `akasha.crop_growth_stages`
3. Run `python -m app.cli db upgrade`

Until this migration is applied, bulk creation **cannot** store stages.

### 7.2 New table: `crop_growth_stages`

| Column | Type | Notes |
|--------|------|--------|
| `id` | int/serial PK | |
| `crop_id` | FK → `crops.id` ON DELETE CASCADE | |
| `seq` | int | order 1..N |
| `name` | text | stage name |
| `duration` | text | raw duration from JSON |

- Unique: `(crop_id, seq)`
- Optional: relationship `Crop.growth_stages` (nice-to-have)
- **Do not** add a big JSON `stages` column on `crops` for v1

### 7.3 Change `generate_crops` in `bulk_creation.py`

**Remove**

- `if db_count == json_count: return 0`
- Delete-all path for vegetation_cycles / varieties / crops

**Add**

- Create-or-update crop by `name`
- After each crop: refresh its stages from `item["stages"]`

### 7.4 Login / signup path

[`ensure_reference_data()`](../apps/api/app/repositories/crops_repo.py) should run the upsert path so:

- not only “seed when empty”
- JSON changes (like new stages) apply on next login even when names are unchanged

### 7.5 Files touched (implementation)

| File | Change |
|------|--------|
| `apps/api/app/models.py` | add `CropGrowthStage` (Crop itself stays; no stages column on crop) |
| `apps/api/alembic/versions/...` | **migration** create `crop_growth_stages` |
| `apps/api/app/bulk_creation.py` | crop upsert + stage refresh |
| `apps/api/app/repositories/crops_repo.py` | ensure path runs upsert |
| tests | create / second-run / stages-added cases |

---

## 8. Implementation order

| Step | Work | Done when |
|------|------|-----------|
| 1 | Agree this plan | ← current |
| 2 | **Migrate first:** `CropGrowthStage` model + Alembic upgrade | `crop_growth_stages` table exists |
| 3 | Rewrite `generate_crops` to create-or-update by name | crops update without wipe |
| 4 | Refresh stages per crop from JSON into new table | stages land in DB |
| 5 | Wire `ensure_reference_data` / `generate_all` | login applies changes |
| 6 | Minimal tests + one manual login check | safe to use |

**Blocker:** step 4 depends on step 2. No stage bulk save without migration.

---

## 9. Out of scope (later)

- Shared `GrowthStageType` across many crops
- Parsing duration into day numbers
- “Current stage” on a field from sowing date
- Deleting crops removed from JSON
- Hash/mtime short-circuit

---

## 10. Summary

| Question | Answer |
|----------|--------|
| Match by what? | **Name only** |
| Name same, stages added? | **Update crop + refresh stages** |
| Stages on Crop model today? | **No** — need new table + **migration first** |
| Where to code? | model/migration, then `bulk_creation.py` |
| Delete all crops? | **No** |
| Slow? | **No** for 76 crops / ~650 stages |
| FastAPI magic method? | **No** — small create-or-update logic we write |

**Final rule:**  
**Same name → update that crop and add/refresh its stages. Names do not need to change for updates to run.**  
**First build step:** migrate `crop_growth_stages` because Crop has no stages yet.
