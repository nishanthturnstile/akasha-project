# Akasha Documentation

Start with [`platform-plan.md`](./platform-plan.md). It is the current documentation index and
source-of-truth boundary map for Akasha.

## Active source-of-truth docs

- [`architecture-tech-stack.md`](./architecture-tech-stack.md) — services, BFF API contracts, frontend architecture, and deployment topology.
- [`data-ingestion-and-satellite-rules.md`](./data-ingestion-and-satellite-rules.md) — imagery sources, COG/STAC metadata, masks, index math, and source onboarding rules.
- [`satellite-ingestion-orchestration-and-scheduler.md`](./satellite-ingestion-orchestration-and-scheduler.md) — how the provider-agnostic ingestion scheduler works, how to trigger/control it, and the checklist for adding a new satellite.
- [`engineering-dos-donts.md`](./engineering-dos-donts.md) — implementation guardrails and anti-pattern checklist.
- [`auth-team-admin-plan.md`](./auth-team-admin-plan.md) — hand-rolled auth, teams, RBAC, and account-management design.
- [`india-specific-productization-plan.md`](./india-specific-productization-plan.md) — India-specific product modules and validation priorities.
- [`design-system.md`](./design-system.md) — current Akasha visual design direction and UI tokens.
- [`map-screen-redesign.md`](./map-screen-redesign.md) — active map-screen redesign plan; keep visible until completed or superseded.

## Operational runbooks

- [`developer-setup-guide.md`](./developer-setup-guide.md) — macOS/Windows local setup, backend/frontend hot reload workflow, rebuild rules, and Alembic migration process.
- [`staging-ingestion-developer-guide.md`](./staging-ingestion-developer-guide.md) — staging ingestion job workflow for team-triggered ingestion.
- [`eos04-sar-mrs-l2b-cog-prep-runbook.md`](./eos04-sar-mrs-l2b-cog-prep-runbook.md) — EOS-04 SAR MRS L2B COG preparation.
- [`nisar-ssar-beta-gcov-cog-prep-runbook.md`](./nisar-ssar-beta-gcov-cog-prep-runbook.md) — NISAR SSAR beta GCOV COG preparation.

Legacy Sentinel runbooks are archived and should be used only for explicit regression or migration work:

- [`archive/sentinel-2-l2a-cog-prep-runbook.md`](./archive/sentinel-2-l2a-cog-prep-runbook.md)
- [`archive/sentinel-1-grd-cog-prep-runbook.md`](./archive/sentinel-1-grd-cog-prep-runbook.md)

## Active implementation plans

- [`impl-plan/`](./impl-plan/) — focused plans for work that is current, pending, or intentionally still visible.
- [`impl-plan/archive/`](./impl-plan/archive/) — completed or superseded implementation plans retained for traceability.

## Reference and archive

- [`reference/`](./reference/) — durable reference material and matrices.
- [`eos-platform/`](./eos-platform/) — EOS Platform reference notes used for product comparisons.
- [`archive/`](./archive/) — historical product/MVP docs, legacy runbooks, completed prompt packs, and informal notes.
