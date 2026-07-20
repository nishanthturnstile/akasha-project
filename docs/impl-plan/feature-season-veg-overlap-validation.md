# Feature: Season & Vegetation Date Validation

## Validation 1: Season Edit Impact on Vegetation Data

### Problem

After onboarding, users can edit an existing season. Changing a season's start/end dates may leave vegetation cycle dates outside the new season boundaries with no warning or adjustment.

### Solution

#### Frontend — `apps/frontend/src/components/seasons/EditSeasonDialog.tsx`

1. Before calling the save callback, scan `allFields` (already passed as a prop) for any field whose `vegetationData` contains a cycle with `seasonId === season.id`.

2. If vegetation data exists, show a confirmation `<AlertDialogRoot>`:

   - **Title:** "Edit season start/end dates"
   - **Message:** "This season already contains vegetation data. Updating the season dates will automatically update the vegetation cycle start date and end date for all vegetation records that fall outside the new season duration. Do you want to continue?"
   - **Buttons:** "Cancel" (closes modal, no save) / "Save" (calls `onSave`)

3. If no vegetation data exists, skip the modal and save directly (current behavior).

#### Backend — `apps/api/app/repositories/seasons_repo.py`

After the season's `start_date` / `end_date` is updated, query all `VegetationCycle` records for this season and clamp:

| Condition | Action |
|-----------|--------|
| `sowing_date < new_start_date` | Set `sowing_date = new_start_date` |
| `harvesting_date > new_end_date` | Set `harvesting_date = new_end_date` |

Only dates that actually changed are adjusted (if only `start_date` changed, only `sowing_date` is touched; likewise for `end_date`).

---

## Validation 2: Prevent Overlapping Vegetation Crop Dates

### Problem

Users can add multiple crops under the same vegetation data. Each crop has a planting date and a harvesting date. Nothing prevents date ranges from overlapping across cycles within the same season.

### Solution

#### DatePicker Enhancement — `apps/frontend/src/components/ui/date-picker.tsx`

Add a new optional prop:

```typescript
disabledRanges?: Array<{
  start: string;   // "YYYY-MM-DD"
  end: string;     // "YYYY-MM-DD"
  reason: 'overlap' | 'season';
}>;
```

- Days falling within any range's `[start, end]` (inclusive) are disabled.
- When `reason = 'overlap'`, apply `bg-red-50/40 text-red-500/60 line-through`.
- When `reason = 'season'` (or no reason), keep the existing muted disabled style.
- The existing `minDate` / `maxDate` props still apply; disabled ranges are additive.

#### Overlap Detection — `apps/frontend/src/components/seasons/EditFieldDialog.tsx`

1. For each season section, compute occupied date ranges from all cycles in that season **except the cycle being edited**.

2. Pass these occupied ranges as `disabledRanges` to both the planting date and harvesting date `<DatePicker>`.

3. Show a validation message below the date picker when overlap is detected:
   > "The selected planting and harvesting dates overlap with another crop's vegetation cycle. Please choose a non-overlapping date range."

4. Disable the Save button when any overlap exists across cycles in the same season.

**Overlap algorithm:**

```
Cycle A range: [plantingDate, harvestingDate]
               (if harvestingDate is empty, range = [plantingDate, plantingDate])
Cycle B range: [plantingDate, harvestingDate]

Overlap if: A.start <= B.end AND B.start <= A.end
```

#### Date management notes

- Existing constraint: harvesting date must be > planting date (`minDate = plantingDate + 1d`, enforced by `updateCycle` which clears harvesting date if it falls before planting date).
- The overlap check uses the same string comparison as the rest of the codebase (ISO dates sort lexicographically).

---

## Files Changed

| File | Change |
|------|--------|
| `apps/frontend/src/components/ui/date-picker.tsx` | Add `disabledRanges` prop with red-tint + strikethrough styling for overlap dates |
| `apps/frontend/src/components/seasons/EditFieldDialog.tsx` | Compute occupied ranges per season; pass to DatePickers; show inline validation; disable save on overlap |
| `apps/frontend/src/components/seasons/EditSeasonDialog.tsx` | Check for vegetation data before save; show confirmation modal |
| `apps/api/app/repositories/seasons_repo.py` | After season date update, clamp vegetation cycle dates to new boundaries |
