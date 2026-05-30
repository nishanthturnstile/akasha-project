# `services/ingestion` — Ingestion worker

Python worker for getting Sentinel-2 data into the catalog + object store.
**Private, no public HTTP surface.** Runs on demand (manual/seed first;
scheduled CDSE/Bhoonidhi ingestion later).

- Base image: `python:3.11-slim`.
- No HTTP health endpoint; `worker.py healthcheck` validates required env vars.

## Slice 0 (skeleton)

`worker.py` is a no-op CLI:

```bash
python worker.py info          # print resolved config (secrets redacted)
python worker.py healthcheck   # exit 0 if required env vars present
```

Real subcommands (SAFE/JP2/TIF → validated COG + SCL COG, STAC item
registration, MinIO upload) are implemented from **Slice 1** onward. In Docker
Compose this runs one-shot (`info`) and exits.
