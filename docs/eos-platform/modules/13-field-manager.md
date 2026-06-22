# Module 13 — Field Manager

Guide page: <https://eos.com/user-guide/crop-monitoring/field-manager/>

## Purpose
Organize fields two ways: by season via the **Crop Rotation** calendar (sowing per
field per season), and by **Field Groups** (grouping fields by common
characteristics). Improves field management and crop-rotation planning.

## 13.A Crop Rotation
A fields × seasons calendar/grid for planning sowings by analyzing history in one
place. Left = all account fields. Top = season names, each season's duration, and the
proportion of hectares per crop.

Three per-cell field statuses:
1. Field **not available** in the season.
2. Field **available, no sowing** added.
3. Field **available, sowing added**.

### 13.1 Manage sowing
- **Add field to a season:** hover an empty season cell → **+ Add to season**.
- **Add sowing:** click **+ Add sowing/planting** in the season cell → fill the
  **Add sowing/planting** window → save.
- Sowing cell then shows only the parameters set: crop name, irrigation type, tillage
  type, sowing date – harvesting date, yield t/ha (actual yield if set, else target).
- **Edit:** sowing cell → more menu (⋮) → **Edit**.
- **Delete:** sowing cell → ⋮ → **Delete** (removes the field from the season only;
  it remains in the account).

### 13.2 Crop Allocation
Auto-distributes selected crops across fields in a season. Available for **active and
planned** seasons; includes only fields **without sown crops**.
- Crop Rotation → pick eligible season → **Crop Allocation** button.
- In the popup: select crops, enter **area per crop** and a **sowing date** (optional
  now, required later). Total selected area must not exceed the season's available area.
- **Allocate** → results list fields with assigned crops, each carrying a confidence
  indicator based on rotation-matrix + field history:
  - **Green** — allocated by rotation matrix; field has **≥3** consecutive seasons of
    supported crops in history.
  - **Yellow** — by matrix; **1–2** seasons of supported crops in history.
  - **Gray** — crop supported by matrix but no matching history; allocation by area only.
  - **No indicator** — crop not in the rotation matrix; allocation by input area only.
- In results you can set/adjust sowing dates and exclude fields. **Apply** to save,
  **Cancel** to discard.

## 13.B Field Groups
Group fields by shared characteristics. The Field group manager lists groups and the
field count per group.

### 13.3 Add group
- **+ Add new group** → enter name + add fields.
- A field belongs to **one group at a time**; adding a grouped field to a new group
  **moves** it. Grouped fields show a marker in the list.

### 13.4 Manage group
- **Manage** next to a group → see its fields; **+ Add fields**; remove a field via
  **X** (field stays in account, ungrouped); rename the group; **delete** the group
  (its fields remain in the account, ungrouped).

## Cross-references
- Sowing data drives Monitoring crop info (module 06), Season Analytics (module 09),
  and feeds Seasonality (module 04). Groups are used by filters everywhere (module 02).

## Notes for replica
- Crop Rotation = the editable matrix view of the `field × season → sowing` data
  (Seasonality owns the season entity; Field Manager is the planning UI over it).
- Crop Allocation = an allocator using a crop-rotation matrix + per-field crop history
  to suggest assignments, constrained by available season area, with confidence tiers.
- Field Groups = simple 1-field-to-1-group grouping with move-on-reassign semantics.
