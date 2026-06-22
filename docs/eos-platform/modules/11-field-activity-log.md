# Module 11 — Field Activity Log

Guide page: <https://eos.com/user-guide/crop-monitoring/field-activity-log/>

## Purpose
Plan and monitor all field activities (fertilizing, tillage, planting, spraying,
harvesting, etc.) for one or many fields on a single interactive calendar, including
planned-vs-actual cost tracking. Separate tab on the sidebar.

## Sub-features

### 11.1 Location & Demo Field
- Lives in its own sidebar tab.
- A **Demo Field** is available to learn the feature before adding real fields.

### 11.2 Log Structure (3 columns)
- **Field column** (left) — list of fields; sort by name A→Z / Z→A.
- **Sowing Dates** (middle) — most recent sowing date per field; sort earliest→latest.
- **Activity Calendar** (right, largest) — interactive calendar of planned/completed
  activities, **split in half by the current-date column**: completed on the left,
  planned on the right.

### 11.3 Activity status & color
Color encodes completion status:
- **Single-day activity:** future = **gray striped**; when the current date reaches
  the planned start, it auto-changes gray → **red** (no confirmation it started).
  Add completion **Start + End** dates (click activity → "+" → set dates → Save) to
  turn **red → green** (completed).
- **Multiple-day activity:** add the completion **Start** date when work begins →
  day cells turn gray → **blue** (in progress) one by one; add the **End** date when
  done → the whole completion period turns **green**.
- **Behind/ahead of schedule:** missed days stay **red**; finishing late marks the
  extra days red; finishing early leaves the extra days **gray**. A completion start
  date cannot be earlier than the planned start date (start earlier ⇒ add a new
  activity).
- **Completed-in-past activity:** added retroactively, distinct **yellow** color (to
  distinguish unscheduled from scheduled).

### 11.4 Add activity
Two entry points: the **"+"** button (bottom-right) or clicking a calendar cell.
- Choose **completed** vs **planned**; select **activity type** + planned start/end.
- Planned activities can't use **past** dates; completed activities can't use
  **future** dates. Completed activities can be backdated to **Jan 2016**+.
- **Multiple fields:** one activity can be added to several fields at once.
- **Cost:** estimated (planned) or actual (completed) — enables planned-vs-actual
  comparison.
- **Description:** optional.

### 11.5 Organize activities
- Filter the calendar by **year, field group, crop type, activity type** (top bar).

### 11.6 Edit activity
- Click an activity → **pencil** icon → edit in a window.

## Cross-references
- Activity statuses + costs feed the **Season Analytics** widgets (module 09).
- Activity types align with VRA/Data Manager activities; Demo field ties to Settings.

## Notes for replica
- Data model: `Activity { id, fieldIds[], type, plannedStart, plannedEnd,
  completionStart, completionEnd, cost(planned/actual), description }`.
- The color state machine is the core complexity: derive state from (planned dates,
  completion dates, today) → {planned-gray, due-red, in-progress-blue,
  completed-green, past-completed-yellow, overdue-red}.
- Calendar split at "today"; multi-field add; filters; backdate floor at 2016.
