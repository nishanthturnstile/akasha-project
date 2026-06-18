# Module 16 — Account & Pricing

Guide page: <https://eos.com/user-guide/crop-monitoring/account-and-pricing/>

## Purpose
Subscription plans and the add-on marketplace that gate access to paid features. The
Pricing page opens via the **arrow button** (bottom-right of the screen).

## Sub-features

### 16.1 Plans
- **Free** — base tier (demo field, limited imagery/features; trials on demo field).
- **Essential** — monitor up to **1000 ha**; unlocks paid features (e.g. historical
  imagery from 2016, leaderboard, risks).
- **Professional** — choose how many hectares to monitor; add more hectares for an
  additional price; full feature set.
- **Enterprise** — custom solutions + tailored pricing for farms **> 5000 ha**,
  cooperatives, advisors, IT companies, etc.

### 16.2 Pricing page
- Opened via the upgrade arrow; details per-plan functionality.

### 16.3 Add-ons (Marketplace)
- Add-ons store reachable via an icon on the right side menu, or from the Pricing
  page. Add-ons extend functionality beyond the base plan (examples surfaced
  elsewhere: Disease risk, Yield estimation, additional indices, PlanetScope source).

## Cross-references
- This module defines the **plan-gating model** referenced throughout (Pro-only
  layers in module 03, Essential/Pro imagery & risks in module 06, Leaderboard/Custom
  Report Pro gating in module 09, hide-demo Pro in module 15).

## Notes for replica
- Model: `Plan { tier(Free/Essential/Professional/Enterprise), hectareLimit,
  features[] }` + `Addon { id, name, gatedFeatures[] }` + per-account entitlements.
- A central entitlement check should drive feature gating consistently across modules.
- Hectare accounting (limits, over-acreage Pro markers in module 03) is part of this.
