# Module 15 — Settings

Guide page: <https://eos.com/user-guide/crop-monitoring/settings/>

## Purpose
Account-level preferences for the platform UI and demo content.

## Sub-features
- **Interface language** — choose UI language.
- **Metric system** — choose units (metric/imperial; e.g. ha vs ac, °C, mm).
- **Demo content visibility** — show/hide demo content. Hiding is **Pro only**.
  - Demo content = a **demo field**, **demo scouting tasks**, and a **dataset** for
    the Data Manager feature.

## Cross-references
- Units propagate everywhere areas/temperatures/precip are shown (modules 06/07/etc.).
- Demo content interacts with onboarding/gift field (module 01) and Free-account
  trials (Leaderboard demo, module 09).
- Cloudiness threshold for the Monitoring date line is also changed in account
  settings (see module 06 §6.2) — confirm whether this lives here or in a separate
  account-settings surface during build.

## Notes for replica
- Small but cross-cutting: a per-user preferences object `{ language, unitSystem,
  showDemoContent }`. Gate `showDemoContent=false` behind Pro.
