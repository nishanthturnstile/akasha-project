# Plan: Field and FieldSeason Tables Implementation

## Overview

Implement two new API-owned tables in the `akasha` schema:
1. **Field** - User-scoped farm field boundaries (distinct from Plot)
2. **FieldSeason** - Junction table linking Fields to Seasons (many-to-many)

**Key distinction:**
- `Field` = farm field entity that can be assigned to multiple seasons
- `Plot` = geographic area for satellite imagery analysis (has agronomic metadata, single season_label string)

## Table Designs

### Field Table
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key using `UuidPkMixin` convention |
| `user_id` | UUID (FK) | Required reference to `akasha.users.id` |
| `name` | text | Required, non-blank name |
| `area_ha` | float | Field area in hectares |
| `geometry` | PostGIS geometry | POLYGON/MULTIPOLYGON, SRID 4326 |
| `group_id` | UUID (FK, nullable) | Optional reference to `akasha.field_groups.id` |
| `created_at` | timestamp | Auto-timestamp |
| `updated_at` | timestamp | Auto-timestamp via trigger |

### FieldSeason Table (Junction)
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key (not composite) |
| `field_id` | UUID (FK) | Required reference to `akasha.fields.id` |
| `season_id` | UUID (FK) | Required reference to `akasha.seasons.season_id` |
| Unique constraint on `(season_id, field_id)` | Prevents duplicate assignments |

## Implementation Steps

### Step 1: Add Migrations
Create `apps/api/alembic/versions/20260612_0004_add_fields_and_field_seasons.py`:
- Create `akasha.fields` table with all constraints
- Create `akasha.field_seasons` junction table
- Add indexes: `idx_fields_user_id`, `idx_field_seasons_season_id`, `idx_field_seasons_field_id`
- Add GIST index on geometry for spatial queries
- Add updated_at trigger for fields table
- Add unique constraint for season_id/field_id pair

### Step 2: Add ORM Models
Update `apps/api/app/models.py`:
- Add `Field` model using `UuidPkMixin, TimestampMixin, Base` with explicit `user_id` (required) and `group_id` (nullable)
- Add `FieldSeason` model as standalone entity with UUID PK
- Follow Season's user-scoped pattern (not Plot's OwnerTeamMixin)
- Add GIST index on `Field.geometry`

Note: Field uses user-scoped ownership (like Season), not team-scoped (like Plot).

### Step 3: Add Repository Layer
Create `apps/api/app/fields_repo.py`:
- `create_field(user_id, name, geometry, area_ha, group_id, season_ids)` → dict (with seasons list)
- `list_fields(user_id)` → list[dict]
- `get_field(field_id, user_id)` → dict | None
- `update_field(field_id, user_id, **kwargs)` → dict | None (syncs season_ids)
- `delete_field(field_id, user_id)` → bool (CASCADE removes field_seasons)
- `list_fields_for_season(season_id, user_id)` → list[dict]
- `add_field_to_season(season_id, field_id, user_id)` → dict
- `remove_field_from_season(season_id, field_id, user_id)` → bool

### Step 4: Add API Routes
Create `apps/api/app/fields.py`:
- `GET /api/fields` - list all fields for user
- `POST /api/fields` - create field (requires owner/admin/member role)
- `GET /api/fields/{field_id}` - get single field
- `PATCH /api/fields/{field_id}` - update field
- `DELETE /api/fields/{field_id}` - delete field
- `GET /api/seasons/{season_id}/fields` - list fields for a season
- `POST /api/seasons/{season_id}/fields` - add field to season
- `DELETE /api/seasons/{season_id}/fields/{field_id}` - remove field from season

### Step 5: Wire Routes in main.py
Add `fields_router` import and `app.include_router(fields_router)` in `apps/api/app/main.py`

## Notes

- Field uses user-scoped ownership (like Season), only `user_id` required
- `group_id` references existing `field_groups.id` FK (not creating new groupings)
- Use `season_id` as FK column name (matches Season model's primary key column)
- Follow existing error patterns: `{ "error": { code, message, details } }`
- Add CASCADE delete on seasons.user_id (fields orphaned when user deleted)
