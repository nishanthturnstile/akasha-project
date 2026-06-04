# Akasha Documentation

Start with [`platform-plan.md`](./platform-plan.md). It is the index for the split, non-overlapping documentation pack.

`platform-plan.md` also contains a prompt-slice table for incremental, functionality-by-functionality prompting.

Operational runbooks:

- [`sentinel-2-l2a-cog-prep-runbook.md`](./sentinel-2-l2a-cog-prep-runbook.md) — repeatable process for coverage-manifest discovery, Sentinel-2 L2A SAFE ZIP download, COG preparation, and manifest-driven ingestion.
- [`sentinel-1-grd-cog-prep-runbook.md`](./sentinel-1-grd-cog-prep-runbook.md) — Sentinel-1 GRD SAFE ZIP preprocessing with SNAP GPT into SAR backscatter COGs.

Research notes:

- [`eos/eos-crop-monitoring-replication-research.md`](./eos/eos-crop-monitoring-replication-research.md) — EOSDA Crop Monitoring feature inventory, EOS API mapping, baseline replication priorities, and India-specific productization notes.

Implementation plans:

- [`eos/feature-eos-crop-monitoring-parity-1.md`](./eos/feature-eos-crop-monitoring-parity-1.md) — sequenced EOSDA Crop Monitoring functional-parity roadmap with dependencies, tasks, files, testing, and risks.
- [`eos/feature-eos-crop-monitoring-parity-phase-1-field-foundation.md`](./eos/feature-eos-crop-monitoring-parity-phase-1-field-foundation.md) — standalone Phase 1 field-foundation implementation plan and acceptance checks.
- [`eos/eos-parity-acceptance-matrix.md`](./eos/eos-parity-acceptance-matrix.md) — Phase 0 execution checklist: per-module EOS parity acceptance matrix, provider-strategy classification, first-demo acceptance path, and non-goals.
- [`eos/eos-api-integration-review-summary.md`](./eos/eos-api-integration-review-summary.md) — internal engineering review of the EOSDA API Connect integration status, guardrails, gaps, and next steps.

Prompt packs:

- [`eos/eos-parity-phase-wise-agent-prompts.md`](./eos/eos-parity-phase-wise-agent-prompts.md) — copy/paste Copilot CLI prompts for planning, reviewing, implementing, and validating each EOS parity phase.
