# Bhoonidhi Daily Ingestion — Plan

Summary
-------
Daily scheduled pipeline (12:00 PM) that queries the Bhoonidhi API for newly available satellite products, downloads them, stores the files in MinIO (S3-compatible), and records ingestion metadata in PostgreSQL. This system must be idempotent, observable, and run from a static egress IP whitelisted by NRSC.

Architecture (logical)
----------------------

    +----------------+
    | Celery Beat    |
    | (12:00 PM)     |
    +-------+--------+
            |
            v
    +----------------+
    | Celery Worker  |
    +-------+--------+
            |
            v
    +----------------+
    | Bhoonidhi API  |
    | Auth/Search    |
    +-------+--------+
            |
            v
    +----------------+
    | Download File  |
    +-------+--------+
            |
            v
    +----------------+
    | MinIO Storage  |
    +-------+--------+
            |
            v
    +----------------+
    | PostgreSQL     |
    | Metadata       |
    +----------------+

Goals
-----
- Discover and ingest new Bhoonidhi products once per day at 12:00 PM (timezone-aware).
- Avoid duplicate ingestion via deterministic keys and idempotent upserts.
- Stream large downloads, verify checksum, and upload to MinIO.
- Persist canonical metadata and ingestion status in PostgreSQL.
- Emit metrics and alerts for failures and SLA breaches.

Constraints & Assumptions
-------------------------
- Bhoonidhi access requires API approval and NRSC static-IP whitelisting — obtain before production.
- Worker egress must come from static IP(s) (VM with reserved IP, cloud NAT, or managed egress).
- Secrets (Bhoonidhi creds, MinIO keys, DB URL) are stored in a secrets manager or k8s secrets.

Static IP / Whitelisting Options
--------------------------------
- Reserved VM public IP (simplest).
- Cloud NAT / NAT Gateway attached to VPC or k8s cluster.
- Managed static egress / proxy service.
- Avoid ephemeral PaaS egress that cannot provide stable IPs.

Functional requirements (summary)
---------------------------------
- Auth: token-based authentication with automatic refresh.
- Search: query Bhoonidhi for products newer than the last successful ingestion or within a configurable window.
- Download: streamed, checksum-verified, temp-file write, then upload.
- Store: MinIO object key pattern and metadata tagging.
- Metadata: canonical DB record per product (status transitions and attempts tracking).
- Observability: Prometheus metrics, structured logs, Sentry for exceptions, Slack/PagerDuty alerts.

Non-functional requirements
--------------------------
- Idempotency: repeated schedules don't duplicate objects or DB rows.
- Concurrency: configurable (e.g., 4 parallel downloads default).
- Runtime target: typical run finishes within 3 hours; alert if job crosses threshold.
- Security: TLS for all endpoints; least-privilege service accounts.

Suggested data model (minimal)
------------------------------

```sql
CREATE TYPE ingest_status AS ENUM ('pending','in_progress','completed','failed');

CREATE TABLE bhoonidhi_products (
  id SERIAL PRIMARY KEY,
  scene_key TEXT UNIQUE NOT NULL,
  product_id TEXT,
  collection TEXT,
  s3_bucket TEXT NOT NULL,
  s3_key TEXT NOT NULL,
  size BIGINT,
  checksum_sha256 TEXT,
  acquired_at TIMESTAMPTZ,
  ingested_at TIMESTAMPTZ DEFAULT now(),
  status ingest_status DEFAULT 'pending',
  attempts INT DEFAULT 0,
  last_error TEXT,
  properties JSONB
);
CREATE INDEX ON bhoonidhi_products (acquired_at);
```

Batch Job — Download & Convert to TIF
------------------------------------

Purpose: convert raw downloaded satellite products (SAFE ZIPs or vendor archives) into production-grade GeoTIFF/COG artifacts (`analytic.tif` and `scl.tif`) and produce a prepare manifest describing outputs.

Approach options:
- Inline conversion (recommended): Celery worker downloads the product, runs the conversion job locally (or in a sidecar/container), produces COGs, then uploads the resulting TIFs and manifest to MinIO before upserting metadata.
- Decoupled batch: worker stages the raw product in MinIO and enqueues a separate "prepare" batch job to convert staged archives into COGs (useful for heavy CPU/GDAL workloads).

Tools and implementation notes:
- Use the existing repository utility `scripts/prepare_sentinel2_l2a_cogs.py` for Sentinel-2 L2A SAFE ZIP → `analytic.tif` + `scl.tif` conversion; it produces validated COGs and a `prepare_manifest.json` per product. Run it inside the ingestion container to avoid local GDAL problems.
- GDAL/rasterio/rio-cogeo are the primary dependencies. Prefer the repo's ingestion Docker image (contains pinned GDAL stack).
- Ensure `COG` creation uses tiled, compressed GeoTIFFs with overviews (rio-cogeo) and validate with `rio_cogeo.cogeo.cog_validate`.
- Write outputs to a deterministic key layout: `bhoonidhi/{acq_date}/{scene_key}/analytic.tif` and `.../scl.tif` and `.../prepare_manifest.json`.

Resource considerations & concurrency:
- Conversion is CPU- and I/O-intensive — limit concurrent conversions per host (suggest default 2–4) and use ephemeral disk space mounted for temp intermediates.
- Use per-product temp directories and delete intermediates on success to free space.

Idempotency:
- The `prepare_manifest.json` and deterministic output keys allow the conversion step to be idempotent (`--overwrite` toggles behavior). Use DB `UNIQUE(scene_key)` and `ON CONFLICT` upserts to avoid duplicates.

Testing & run commands (example):

Run a single product conversion in the ingestion container:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
        python scripts/prepare_sentinel2_l2a_cogs.py --zip-path data/raw/sentinel-2-l2a/<PRODUCT_ID>/<PRODUCT_ID>.SAFE.zip --overwrite
```

Run a batch from a downloader selection manifest:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
        python scripts/prepare_sentinel2_l2a_cogs.py --selection-manifest data/seed/stac/selection.json --overwrite
```

Integration with ingest pipeline:
- Option A (single-task): `search_and_ingest` downloads and calls the conversion function before uploading final objects and upserting DB.
- Option B (two-stage): `search_and_ingest` stages raw archives in MinIO and enqueues `prepare_and_ingest` batch tasks which perform conversion and finalization.

Implementation milestones
------------------------
0. Approvals & infra planning — request Bhoonidhi API access and NRSC whitelist (blocking). (1–10 days)
1. Provision infra: MinIO bucket, Postgres, Celery broker (Redis/RabbitMQ), worker host with static egress. (1–2 days)
2. Implement Bhoonidhi client (auth + search) + unit tests. (2–3 days)
3. Implement download/upload pipeline (streaming, checksum) + integration tests. (2–4 days)
4. Wire Celery Beat + Worker, scheduling, retries, and idempotency locks. (1–2 days)
5. Add monitoring, logging, and alerting. (1–2 days)
6. Staging validation and production rollout. (1–3 days)

Risks & mitigations
-------------------
- API approval / NRSC delays — start approval early; run staging with a mirror dataset.
- Large downloads causing disk pressure — stream to disk, enforce per-worker concurrency, use ephemeral worker volumes.
- Partial uploads / corrupted objects — verify checksum; delete partial objects and retry.
- Egress IP change — document process to update NRSC whitelist and automate notifications.

Success criteria
----------------
- New products are discovered and ingested daily with a single canonical DB row per product.
- No silent failures: failures are alerted within 15 minutes.
- System can re-run failed ingests and recover partial states.

Owners & contacts
-----------------
- Infra owner: TBD
- Backend owner: TBD
- On-call for ingestion failures: TBD

Deliverables
------------
- DB migration for `bhoonidhi_products`.
- Bhoonidhi client library (auth, search, download helpers).
- Celery tasks for search + ingest (with tests).
- Monitoring dashboards and alert rules.
- Ops runbook for recovery.

Next steps / owner actions
-------------------------
1. Provide chosen egress host or NAT gateway and start NRSC static IP whitelist request.
2. Provide or allow creation of MinIO bucket and service account credentials.
3. Confirm AOI/product filters (cloud cover threshold, collections of interest).
