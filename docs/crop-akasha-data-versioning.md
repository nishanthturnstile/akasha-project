# Crop-Akasha Data Versioning Plan

## How the hash-based change detection works

### The problem

When you edit `crop-akasha.json` (add a crop, change a seeding type, update a color), the existing `generate_crops` logic only checks **"does this crop name already exist in DB?"**. So it would skip existing names and never apply updates. Old crops removed from the JSON would also stay in the DB forever.

### The solution: SHA256 fingerprint comparison

```
generate_crops runs → reads crop-akasha.json → computes SHA256 hash
                           │
                           ▼
               compares with stored hash in DB
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   No hash stored    Hash matches     Hash differs
   (first run)       (no changes)     (file edited)
          │                │                │
          ▼                ▼                ▼
   Insert all 76     Skip — nothing    Delete old crops
   Save hash         to do             Re-insert all 76
                                       Update hash
```

### What is SHA256?

SHA256 is a cryptographic function that takes any file and produces a unique 64-character string (the "fingerprint" or "hash").

```
crop-akasha.json (before edit)
→ a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0

crop-akasha.json (change one comma)
→ f9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0
```

Even a single character change completely changes the hash. This is how we detect edits.

### Where is the hash stored?

In the **`app_settings`** DB table (`akasha.app_settings`), which already exists in the codebase.

```
akasha.app_settings table:
┌────────────────────────────────┬──────────────────────────────────────────────────┐
│ key                            │ value                                            │
├────────────────────────────────┼──────────────────────────────────────────────────┤
│ "crop_akasha_data_hash"        │ "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5..."          │
│ "some_other_setting"           │ "..."                                            │
└────────────────────────────────┴──────────────────────────────────────────────────┘
```

We use `AppSetting` because:
- It's **already in the DB** — no new tables or migrations needed (except the `has_variety` column)
- It **persists** across restarts
- It's **updated automatically** by the code — no manual steps
- Storing the hash **inside** the JSON file would create a chicken-and-egg problem (you can't detect changes to a file by reading a hash inside the same file)

### What code touches AppSetting?

Only two lines in `bulk_creation.py`:

```python
# Read stored hash
stored = session.get(AppSetting, "crop_akasha_data_hash")

# Save/update hash
session.merge(AppSetting(key="crop_akasha_data_hash", value=current_hash))
```

No new code in the `AppSetting` model itself — it's already defined in `models.py`.

### Flow diagram: what happens on each API start

```
1. generate_crops() called by ensure_reference_data()
2. Read crop-akasha.json from disk
3. Compute SHA256 → "abc123..."
4. Query: SELECT * FROM akasha.app_settings WHERE key = 'crop_akasha_data_hash'

   ┌──────────────────────────────────────────────────────────────┐
   │ CASE 1: First ever run (no row in app_settings)              │
   │                                                              │
   │   DB is empty → insert all 76 crops                          │
   │   INSERT INTO akasha.app_settings (key, value)               │
   │     VALUES ('crop_akasha_data_hash', 'abc123...')            │
   │                                                              │
   │ Result: 76 crops created, hash saved                         │
   ├──────────────────────────────────────────────────────────────┤
   │ CASE 2: Normal restart (hash matches)                        │
   │                                                              │
   │   Hash from file:    'abc123...'                             │
   │   Hash from DB:      'abc123...'                             │
   │   → Match → skip, nothing to do                              │
   │                                                              │
   │ Result: 0 crops inserted (fast exit)                         │
   ├──────────────────────────────────────────────────────────────┤
   │ CASE 3: JSON edited (hash differs)                           │
   │                                                              │
   │   Hash from file:    'xyz789...'  (new)                      │
   │   Hash from DB:      'abc123...'  (old)                      │
   │   → Mismatch → detect change                                 │
   │                                                              │
   │   1. DELETE FROM akasha.varieties                            │
   │   2. DELETE FROM akasha.crops                                │
   │   3. Insert all 76 crops from scratch                        │
   │   4. UPDATE akasha.app_settings SET value = 'xyz789...'      │
   │      WHERE key = 'crop_akasha_data_hash'                     │
   │                                                              │
   │ Result: all old crops replaced, hash updated                 │
   └──────────────────────────────────────────────────────────────┘
```

### The `data_changed` variable explained

```python
stored = session.get(AppSetting, CROP_DATA_HASH_KEY)
data_changed = stored is None or stored.value != current_hash
```

| `stored` value | `data_changed` | Meaning |
|---|---|---|
| `None` (no row) | `True` | First run — insert fresh |
| Hash matches | `False` | No changes — skip |
| Hash differs | `True` | File edited — replace all |

```python
if data_changed and stored is not None:
    # Only delete if this is NOT the first run
    # (first run means DB is already empty)
    session.query(Variety).delete()
    session.query(Crop).delete()
    session.flush()
```

### Summary

| Concept | Detail |
|---|---|
| **Detection method** | SHA256 hash of the entire `crop-akasha.json` file |
| **Storage location** | `akasha.app_settings` table (key-value store) |
| **Storage key** | `"crop_akasha_data_hash"` |
| **When checked** | Every time `generate_crops()` runs (on API start) |
| **What triggers a rebuild** | Any change to the JSON file — even whitespace |
| **User action needed** | None — edit JSON, restart API, changes applied automatically |
| **New tables needed** | None — `app_settings` already exists |
| **New column needed** | `has_variety` on `crops` table (via Alembic migration) |
