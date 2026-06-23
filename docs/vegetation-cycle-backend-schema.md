# Vegetation Cycle — Backend Schema & Bulk Creation Plan

## Status

- **Decisions made on all design questions** (see §6)
- **JSON/data files ready:** `docs/reference-data.json`, `docs/crop-catalog.json`, `docs/vegetation-cycle-api.json`
- **Ready to implement** — step-by-step task list at §4
- **Deferred:** `vegetation_cycle` transaction table (not yet planned)

---

## 1. Confirmed Schema

All tables in `akasha` schema.

### `irrigation_type`

| Column | Type | Constraints |
|--------|------|-------------|
| id | integer | PK, serial |
| name | text | NOT NULL, UNIQUE |
| description | text | nullable |

### `tillage_type`

| Column | Type | Constraints |
|--------|------|-------------|
| id | integer | PK, serial |
| name | text | NOT NULL, UNIQUE |
| description | text | nullable |

### `seeding_type` (pre-seeded)

| Column | Type | Constraints |
|--------|------|-------------|
| id | integer | PK, serial |
| name | text | NOT NULL, UNIQUE |
| description | text | nullable |

Pre-seeded with 5 rows: `direct_seed`, `transplant`, `planting_cutting`, `vine`, `perennial_tree`.

### `crop`

| Column | Type | Constraints |
|--------|------|-------------|
| id | integer | PK, serial |
| name | text | NOT NULL, UNIQUE |
| seeding_type_id | integer | FK → seeding_type.id, NOT NULL |
| color | text | nullable |
| maturity_options | jsonb | nullable — e.g. `["very_early","early","middle","late"]` |
| has_weather_risk | boolean | NOT NULL, default false |
| bbch_mode | text | nullable |
| characteristic | text | nullable |

### `variety`

| Column | Type | Constraints |
|--------|------|-------------|
| id | integer | PK, serial |
| crop_id | integer | FK → crop.id, NOT NULL |
| name | text | NOT NULL |
| maturity_options | jsonb | nullable |
| UNIQUE | (crop_id, name) | |

---

## 2. Endpoints — GET only (read for frontend dropdowns)

No POST/PUT/PATCH/DELETE endpoints. Data is loaded by scripts (see §3).

```
GET /api/irrigation-types      → [{ id, name }]
GET /api/tillage-types         → [{ id, name }]
GET /api/seeding-types         → [{ id, name, description }]
GET /api/crops                 → [{ id, name, seedingTypeId, color, maturityOptions, hasWeatherRisk, bbchMode, characteristic }]
GET /api/crops/:id/varieties   → [{ id, cropId, name, nameUk, maturityOptions }]
```

---

## 3. Bulk Generation — modular pattern (the key design choice)

Instead of a single monolithic seed script, each entity has its own independent generator function in a shared module. This lets you call all of them together, or just one at a time from anywhere (CLI, tests, admin panel, etc.).

### Module: `apps/api/app/bulk_creation.py` (new file)

Each generator reads its JSON source, checks if each row already exists (by name), and inserts missing rows. All are idempotent and return the count of new rows.

```python
from app.db import session_scope
from app.models import IrrigationType, TillageType, SeedingType, Crop, Variety

DATA_DIR = Path(__file__).resolve().parent / "data"

def _load_json(filename: str) -> Any:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Irrigation types ──────────────────────────────────────────
# Source: scripts/data/irrigation-types.json
# No dependencies.
def generate_irrigation_types(session: Session) -> int:
    data = _load_json("irrigation-types.json")
    count = 0
    for item in data:
        if session.query(IrrigationType).filter_by(name=item["name"]).first():
            continue
        session.add(IrrigationType(name=item["name"], description=item.get("description")))
        count += 1
    return count

# ── Tillage types ─────────────────────────────────────────────
# Source: scripts/data/tillage-types.json
# No dependencies.
def generate_tillage_types(session: Session) -> int:
    data = _load_json("tillage-types.json")
    count = 0
    for item in data:
        if session.query(TillageType).filter_by(name=item["name"]).first():
            continue
        session.add(TillageType(name=item["name"], description=item.get("description")))
        count += 1
    return count

# ── Seeding types ─────────────────────────────────────────────
# Source: hardcoded tuple (only 5, no external file)
# No dependencies.
SEEDING_TYPES = [
    ("direct_seed", "Seeds sown directly in the field"),
    ("transplant", "Started in nursery, moved to field"),
    ("planting_cutting", "Vegetative propagation by cuttings or tubers"),
    ("vine", "Perennial vine crop"),
    ("perennial_tree", "Long-lived tree or shrub crop"),
]

def generate_seeding_types(session: Session) -> int:
    count = 0
    for name, desc in SEEDING_TYPES:
        if session.query(SeedingType).filter_by(name=name).first():
            continue
        session.add(SeedingType(name=name, description=desc))
        count += 1
    return count

# ── Crops ─────────────────────────────────────────────────────
# Source: scripts/data/crops.json (286 crops)
# Depends on: seeding_type rows existing
def generate_crops(session: Session) -> int:
    data = _load_json("crops.json")
    seeding_map = {st.name: st.id for st in session.query(SeedingType).all()}
    count = 0
    for item in data:
        if session.query(Crop).filter_by(name=item["name_en"]).first():
            continue
        seeding_type_id = seeding_map.get(item["seeding_type"])
        maturity_options = [m["name"] for m in (item.get("maturities") or [])] or None
        session.add(Crop(
            name=item["name_en"],
            seeding_type_id=seeding_type_id,
            color=item.get("color"),
            maturity_options=maturity_options,
            has_weather_risk=item.get("has_weather_risks", False),
            bbch_mode=item.get("bbch_mode"),
            characteristic=item.get("characteristic"),
        ))
        count += 1
    return count

# ── Varieties ─────────────────────────────────────────────────
# Source: scripts/data/varieties.json (37K varieties across 47 crops)
# Depends on: crop rows existing (keyed by crop name from crops.json → crop.id)
def generate_varieties(session: Session) -> int:
    data = _load_json("varieties.json")
    crop_map = {c.name: c.id for c in session.query(Crop).all()}
    count = 0
    for crop_name, varieties in data.items():
        crop_id = crop_map.get(crop_name)
        if not crop_id:
            continue
        for item in varieties:
            if session.query(Variety).filter_by(crop_id=crop_id, name=item["name"]).first():
                continue
            maturity_options = item.get("maturity_options") or item.get("maturities")
            session.add(Variety(
                crop_id=crop_id,
                name=item["name"],
                maturity_options=maturity_options or None,
            ))
            count += 1
    return count
```

### `generate_all()` — each entity in its own transaction

Each generator gets its own `session_scope()` so a failure in one doesn't roll back the others. Varieties failing won't lose crops, seeding types, etc.

```python
def generate_all() -> dict[str, int]:
    """Run every generator. Each entity commits independently.
    Returns {entity_name: count_inserted}."""
    counts = {}
    with session_scope() as s:
        counts["seeding_types"] = generate_seeding_types(s)
    with session_scope() as s:
        counts["irrigation_types"] = generate_irrigation_types(s)
    with session_scope() as s:
        counts["tillage_types"] = generate_tillage_types(s)
    with session_scope() as s:
        counts["crops"] = generate_crops(s)
    with session_scope() as s:
        counts["varieties"] = generate_varieties(s)
    return counts
```

**Transaction isolation per entity:**

| Entity | If it fails | What's saved | What's rolled back |
|--------|-------------|-------------|-------------------|
| `seeding_types` | Yes | nothing | seeding_types |
| `irrigation_types` | Yes | seeding_types | irrigation_types |
| `tillage_types` | Yes | seeding_types + irrigation_types | tillage_types |
| `crops` | Yes | everything above | crops |
| `varieties` | Yes | everything above | varieties |

**Rules:**
- Each function is **idempotent** — checks `filter_by(name)` before inserting; safe to run repeatedly
- Each returns the count of new rows inserted
- Each can be called standalone — if dependency tables are empty, FK lookup returns 0 matches (graceful skip, no crash)

### CLI usage (via `scripts/seed_all.py`):

```python
from app.bulk_creation import generate_all, generate_crops
from app.db import session_scope

# Seed everything (each entity in its own transaction):
python scripts/seed_all.py
#   → calls generate_all()

# Seed only crops + varieties (also independent tx each):
with session_scope() as s:
    generate_seeding_types(s)
with session_scope() as s:
    generate_crops(s)
with session_scope() as s:
    generate_varieties(s)
```

### Importable from anywhere:

```python
# In a test:
from app.bulk_creation import generate_seeding_types, generate_crops

def test_crop_seeding():
    with session_scope() as session:
        count = generate_seeding_types(session)
        assert count == 5
        count = generate_crops(session)
        assert count == 286

# In an Alembic migration (if needed):
from app.bulk_creation import generate_seeding_types
```

### Dependency graph

```
generate_irrigation_types()    — no deps
generate_tillage_types()       — no deps
generate_seeding_types()       — no deps
generate_crops()               — needs seeding_type rows
generate_varieties()           — needs crop rows
```

---

## 4. Implementation Steps (ordered execution)

| # | Step | File(s) | Description |
|---|------|---------|-------------|
| 1 | Create `scripts/data/` directory | `scripts/data/` | Move 3 JSON files from `docs/` → `scripts/data/` with renamed files |
| 2 | Define 5 ORM models | `apps/api/app/models.py` | IrrigationType, TillageType, SeedingType, Crop, Variety (serial PKs, no OwnerTeamMixin, no TimestampMixin, no name_uk) |
| 3 | Create Alembic migration | `apps/api/alembic/versions/` | CREATE TABLE for all 5 tables, indexes, unique constraints |
| 4 | Write bulk generators | `apps/api/app/bulk_creation.py` | 5 idempotent functions + `generate_all()`, reads JSON from `scripts/data/` |
| 5 | Write CLI script | `scripts/seed_all.py` | Imports `generate_all` from `app.bulk_creation`, calls it |
| 6 | Define Pydantic schemas | `apps/api/app/schemas/crops.py` | Response shapes for GET endpoints |
| 7 | Define repositories | `apps/api/app/repositories/crops_repo.py` | List queries (no create/update/delete) |
| 8 | Define GET router | `apps/api/app/routers/crops_router.py` | 5 list endpoints, all read-only |
| 9 | Register router | `apps/api/app/main.py` | `app.include_router(crops_router)` |
| 10 | Apply migration | `python -m app.cli db upgrade` | Creates tables in the DB |
| 11 | Run seed | `python scripts/seed_all.py` | Populates all data from JSON files |
| 12 | Verify mapping | run SQL check | Confirm every variety has a matching crop |

---

## 5. Variety → Crop → Maturity mapping

This is the critical data relationship in the system. Understanding it ensures varieties are linked to the right crop and carry the right maturity info.

### How the mapping works

```
crops.json                              varieties.json
┌──────────────────────┐                ┌──────────────────────┐
│ {id: 1, name: "Wheat",│               │ "Wheat": [           │
│  maturity_options:    │←── key ───────│   {name: "AAC Brandon",│
│   ["very_early",...]} │   match       │    maturity_options:  │
│ {id: 2, name: "Maize",│               │     ["middle","late"]},│
│  maturity_options:    │               │   {name: "AAC Scotia",│
│   ["very_early",...]} │               │    maturity_options:  │
└──────────────────────┘               │     ["early","mid"]},  │
                                       │   ...                  │
                                       │ ]                      │
                                       │ "Maize": [             │
                                       │   {name: "DKC 3909",   │
                                       │    maturity_options:   │
                                       │     ["middle"]},       │
                                       │   ...                  │
                                       │ ]                      │
                                       └──────────────────────┘
```

### Step-by-step resolution

1. **`generate_crops()`** inserts all 286 crops from `crops.json`. Each row gets:
   - `crop.name` = `name_en` from the JSON
   - `crop.maturity_options` = array of maturity `name` values from `maturities[]`, e.g. `["very_early","early","middle","late"]`
   - If `maturities` is missing or empty → `maturity_options` stays `NULL`

2. **`generate_varieties()`** reads `varieties.json`. Each top-level key is a crop name:
   - Looks up `crop_map[crop_name]` → `crop.id`
   - Each variety entry gets `variety.crop_id` = that crop ID
   - Each variety's `maturity_options` comes from the variety entry's own `maturity_options` or `maturities` field
   - If the variety has no maturities → `maturity_options` stays `NULL` (inherits nothing — frontend falls back to crop-level options)

### What's stored where

| Concept | Lives in | Example |
|---------|----------|---------|
| General maturity stages for a crop | `crop.maturity_options` | `["very_early","early","middle","late"]` |
| Variety-specific maturity (overrides) | `variety.maturity_options` | `["middle","late"]` |
| Link from variety to crop | `variety.crop_id` → `crop.id` | via crop name key match |

### Verification check

To verify the mapping is correct after seeding:
```sql
-- Check every variety has a matching crop
SELECT v.name, c.name AS crop_name
FROM akasha.varieties v
JOIN akasha.crops c ON c.id = v.crop_id
WHERE c.id IS NULL;

-- Should return 0 rows. If not, the JSON crop names don't match.
```

---

## 6. Data Files (ready)

Seeding types are hardcoded (5 rows, no file). Other data lives in `scripts/data/`:

| File | Contents | Used by |
|------|----------|---------|
| `scripts/data/irrigation-types.json` | 10 irrigation types (array of `{name, description}`) | `generate_irrigation_types()` |
| `scripts/data/tillage-types.json` | 10 tillage types (array of `{name, description}`) | `generate_tillage_types()` |
| `scripts/data/crops.json` | 286 crops with maturity/seeding metadata | `generate_crops()` |
| `scripts/data/varieties.json` | 37,369 varieties keyed by crop name | `generate_varieties()` |

---

## 7. Design Decisions (confirmed)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Creation pattern | **Alembic = DDL only + `bulk_creation.py` seeds all data** | Single pattern, no data in migrations, avoids 37K-variety migration file |
| 2 | Seeding type — text or model? | **Model (separate `seeding_type` table + FK)** | Normalized, extensible (descriptions/translations per type), FK enforces referential integrity |
| 3 | Maturity options — JSONB or text? | **JSONB array** | Maps directly to frontend list type, supports `@>` array operators, no parsing needed |
| 4 | PK type — UUID or serial? | **serial integer** | Reference tables with stable external IDs; UUID adds overhead for no benefit; data already uses integer IDs |
| 5 | Modular generators | **`generate_*` functions, importable from anywhere** | Each entity is a standalone function; `generate_all()` for bulk; works from CLI, tests, admin |
| 6 | `vegetation_cycle` | **Deferred** | Not planned yet |
| 7 | OwnerTeamMixin | **Not used** | Global lookup data, not team-scoped |
| 8 | No CRUD endpoints | **GET only** | Data loaded by scripts, no POST/PUT/PATCH/DELETE |
