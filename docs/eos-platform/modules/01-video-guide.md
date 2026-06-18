# Module 01 — Video Guide (Onboarding)

Guide page: <https://eos.com/user-guide/crop-monitoring/video-guide/>

## Purpose
An onboarding / learning hub. Not a functional tool itself — it is a curated set
of short walkthrough videos that teach a new user the core workflows. In a replica
this becomes the in-app "Help / Getting started" or a learning center surfaced to
new users (and reachable later from a Help menu).

## Behavior
- Presents a vertical list of titled video tutorials, each an embedded player.
- Each entry is a self-contained topic that maps to a real functional module
  elsewhere in the product (so it doubles as a feature index for newcomers).
- Intended as the first stop after account creation.

## Tutorial topics (the onboarding curriculum)
Order as presented in the guide. Each maps to the functional module noted.

| # | Tutorial | Maps to module |
|---|----------|----------------|
| 1 | Create an Account | Account/signup |
| 2 | A Gift Field | Demo/gift field (free trial field) |
| 3 | Adding a Field | 05 Add Field |
| 4 | Field Analytics | 06 Fields / Monitoring |
| 5 | Monitoring Indexes | 06 Fields / Monitoring (Indices) |
| 6 | Historical Weather | 07 Weather |
| 7 | Weather Forecast | 07 Weather |
| 8 | Scouting | 08 Scouting |
| 9 | Field Leaderboard | 09 Overview |
| 10 | Zoning | 10 VRA Maps |
| 11 | Field Activity Log | 11 Field Activity Log |
| 12 | Data Manager | 12 Data Manager |

## Notes for replica
- A "Gift Field" / demo field is an onboarding device: a pre-loaded sample field so
  a free user can try paid-feeling features without drawing their own field. This
  ties into Settings (show/hide demo content) and plan gating.
- The curriculum order is a good default onboarding flow: account → demo field →
  add real field → analytics → indices → weather → scouting → leaderboard → zoning
  → activity log → data manager.
- Implementation: a simple CMS-driven list of `{title, videoId, linkedModuleRoute}`.
  Low logic complexity; value is in coverage of the right topics.

## Open questions for deep build
- Should onboarding be interactive (in-product tour) in addition to videos? EOS uses
  videos only here.
