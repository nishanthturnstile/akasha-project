# Akasha Documentation

Start with [`platform-plan.md`](./platform-plan.md). It is the index for the split, non-overlapping documentation pack.

`platform-plan.md` also contains a prompt-slice table for incremental, functionality-by-functionality prompting.

Operational runbooks:

- [`sentinel-2-l2a-cog-prep-runbook.md`](./sentinel-2-l2a-cog-prep-runbook.md) — repeatable process for coverage-manifest discovery, Sentinel-2 L2A SAFE ZIP download, COG preparation, and manifest-driven ingestion.
- [`sentinel-1-grd-cog-prep-runbook.md`](./sentinel-1-grd-cog-prep-runbook.md) — Sentinel-1 GRD SAFE ZIP preprocessing with SNAP GPT into SAR backscatter COGs.

Research and productization notes:

- [`india-specific-productization-plan.md`](./india-specific-productization-plan.md) — India-specific product modules and validation priorities.

Implementation plans:

- [`mvp-execution-plan.md`](./mvp-execution-plan.md) — MVP execution scope and sequencing.
- [`impl-plan/`](./impl-plan/) — focused implementation plans for retained native data and UI work.

Prompt packs:

- [`prompts/`](./prompts/) — slice-specific implementation prompts for the Akasha-native platform.
