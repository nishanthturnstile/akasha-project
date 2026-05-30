# Emergent.sh Context

Use this file as the short prompt wrapper for Emergent.sh. The actual requirements live in the source-of-truth files linked from [`platform-plan.md`](./platform-plan.md).

## Prompt

Build the Akasha Railway MVP incrementally, one slice at a time. Use the docs in this folder as source of
truth, but include ONLY the documents/sections listed for the current slice in the prompt-slice table in
platform-plan.md. Build only the requested slice — do not implement future phases or Wave 2 features unless
they are explicitly included. Preserve the API/data contracts established by previous slices. Generate a
Dockerized multi-service application (not one collapsed service). Follow engineering-dos-donts.md as hard
guardrails.

Prove the raster slice (Slice 2) before any frontend polish: TiTiler renders one true-colour tile from a
COG in MinIO, and the BFF returns one cloud-masked, offset-corrected NDVI statistic for a polygon.
