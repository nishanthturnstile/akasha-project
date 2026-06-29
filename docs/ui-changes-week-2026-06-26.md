# UI Changes — Week of June 19–26, 2026

## 1. Crop Tab — Radio-Button Veg Cycle Cards

**Commit:** `7eb07c0`

- **CropTab.tsx**: Replaced "Crop rotation" text card + "All cycles" list with selectable radio-button cards for each vegetation cycle
- Yield card now reads from the radio-selected cycle instead of always the latest
- When no cycles exist, shows "No crop data added yet." with Add button
- After saving a new cycle via EditFieldDialog, it auto-selects as the active cycle
- `resolvedId` derivation handles selection persistence across data refreshes

## 2. Onboarding — Crop Saved as Vegetation Cycle

**Commit:** `7eb07c0`

- **OnboardingStep3.tsx**: After onboarding completes, the selected crop is saved as a `VegetationCycle` for the last created field via `useUpdateField`
- Maps selected crop name → crop ID via `useCrops()`, creates payload with `seasonId`, `cropType`, `year`, `sowingDate`

## 3. Field Delete Button Wiring

**Commit:** `7eb07c0`

- **FieldAnalyticsPage.tsx**: Added `useDeleteField` + `onDelete` prop to EditFieldDialog (was a silent no-op before)
- **EditFieldDialog.tsx**: Made `handleDelete` async — awaits `onDelete` promise before closing, shows error on failure

## 4. Season & Dialog Fixes

**Commit:** `0760525`

- **CreateSeasonDialog.tsx**: Debounced (300ms) client-side duplicate season name check via `useSeasons()`
- **OnboardingStep1.tsx**: Same duplicate check for season name during onboarding
- **CreateSeasonDialog freeze fix**: Moved `key` to `Dialog.Content` instead of wrapper to fix Radix overlay cleanup
- **Sheet.tsx**: Raised `SheetOverlay` z-index from `z-overlay` (30) to `z-popover` (60) to cover toolbar
- **EditFieldDialog identity fix**: Added `key={field.id}` in `FieldAnalyticsPage.tsx` and `GlobalViewPanel.tsx` to remount dialog with correct field state
- **Field duplicate check**: Only runs when name actually differs from `field.name` (was blocking veg-cycle saves)
- **Season card navigation**: Replaced `setGlobalViewOpen(true)` with `navigate()` to `/monitoring/field-analytics`
- **Season sheet tab**: `seasonTabFor()` helper auto-selects `active`/`planned`/`ended` tab based on season dates
- **`onCreated`**: Now passes full `Season` object

## 5. Veg-Cycle Persistence & Dialog Standardization

**Commit:** `76187fe`

- Wired EditFieldDialog from CropTab with `useUpdateField` mutation
- Standardized Save/Cancel buttons (`size=lg`, `min-w-[120px]`) across dialogs
- Added unsaved-changes AlertDialog confirmation on Cancel/X
- Fixed DatePicker z-index above Dialog overlay (`z-[999]`)
- Added `SeasonProvider` context to bridge AppShell seasonId to child routes
- Filtered AddFieldDropdown fields by current season
- Replaced AddFieldDropdown trigger Plus icon with ChevronDown only
- Added duplicate field name validation (frontend) in `FieldCreatePage` and `EditFieldDialog`
- First field `seasonId` passed as defaultSeasonId to skip season radio on create

## 6. Nav Rail Refinements

**Commit:** `423d79e`

- Fullscreen toggle button
- Collapsed nav restructure
- Amber highlight styling

## 7. Field Header & Global View Redesign

**Commit:** `f43e871`

- Shared `AddFieldDropdown` component
- Vertical dividers in field headers (`FieldContextHeader`, `FieldAnalyticsPage`)
- Edit button moved to left divider sequence
- Dividers are full card height (`self-stretch`)
- Global view: top-left logo + search bar
- Bumped text sizes: crop info 11→13px, timeline 11→13px, dates 9→14px
- Fixed MapPage FieldContextHeader removal

## 8. Field Analytics Panel Redesign

**Commit:** `5944177`

- Redesigned field analytics panel with tabbed layout
- Added crop info cards (crop rotation, growth stages, yield, risks, NDVI split)

## 9. Veg-Cycle Frontend Wiring

**Commits:** `709127b`, `76187fe`

- `useVegetationCycles` hook with `setFieldCycles` for atomic store seeding
- Custom searchable variety dropdown with auto-load more (20 per batch)
- Variety/crop type badges near crop name
- Cut-off checkbox before harvesting date
- Default sowing date to Jan 1 of current year
- Made `harvestingDate` nullable in form

---

**Files changed across all commits:**
`CropTab.tsx`, `OnboardingStep3.tsx`, `EditFieldDialog.tsx`, `FieldAnalyticsPage.tsx`, `GlobalViewPanel.tsx`, `CreateSeasonDialog.tsx`, `OnboardingStep1.tsx`, `AppShell.tsx`, `sheet.tsx`, `date-picker.tsx`, `AppShell.tsx`, `AddFieldDropdown.tsx`, `FieldCreatePage.tsx`, `FieldAnalyticsPanel.tsx`
