# Bhoonidhi Daily Ingest — Execution Runbook

Purpose
-------
Step-by-step operational runbook to deploy, run, and troubleshoot the daily Bhoonidhi ingestion pipeline.

Preconditions & approval
------------------------
- Bhoonidhi API credentials (client id/secret) and API access approval.
- NRSC static-IP whitelist for worker egress IP(s).
- MinIO bucket and credentials.
- PostgreSQL database and a Celery broker (Redis or RabbitMQ).

Environment variables (example)

- `BHOONIDHI_API_BASE`
- `BHOONIDHI_CLIENT_ID`
- `BHOONIDHI_CLIENT_SECRET`
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`
- `DATABASE_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `STATIC_EGRESS_IP`

DB migration (example)

```sql
-- Run in apps/api migrations or a separate migration file
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

Celery Beat schedule (example)

```python
from celery import Celery
from celery.schedules import crontab

app = Celery('ingest')
app.conf.broker_url = os.environ['CELERY_BROKER_URL']

app.conf.beat_schedule = {
    'bhoonidhi-daily-ingest': {
        'task': 'ingest.tasks.search_and_ingest',
        'schedule': crontab(minute=0, hour=12),
    }
}
```

Core Celery task (sketch)

```python
from celery import shared_task
from .client import BhoonidhiClient
from .storage import upload_to_minio
from .db import upsert_product, get_last_success_timestamp

@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def search_and_ingest(self):
    client = BhoonidhiClient()
    since = get_last_success_timestamp()
    products = client.search(aoi=AOI, from_time=since)
    for p in products:
        try:
            ingest_single_product(p)
        except Exception as exc:
            # increment attempts and log; retry the task
            raise self.retry(exc=exc)

def ingest_single_product(product):
    scene_key = compute_scene_key(product)
    # idempotent guard: upsert row with status 'in_progress' using DB lock
    if already_ingested(scene_key):
        return
    tmp_path = download_stream_to_tempfile(product.download_url)
    checksum, size = compute_sha256_and_size(tmp_path)
    s3_key = build_s3_key(product)
    upload_to_minio(tmp_path, bucket=MINIO_BUCKET, key=s3_key)
    upsert_product(scene_key, product, s3_key, size, checksum, status='completed')
    cleanup_tmp(tmp_path)
```

Bhoonidhi client best-practice (sketch)

```python
class BhoonidhiClient:
    def __init__(self):
        self.base = os.environ['BHOONIDHI_API_BASE']
        self.token = None

    def authenticate(self):
        if self.token and not expired(self.token):
            return self.token
        r = requests.post(self.base + '/auth/token', data={...})
        r.raise_for_status()
        self.token = r.json()['access_token']
        return self.token

    def search(self, aoi, from_time=None):
        token = self.authenticate()
        headers = {'Authorization': f'Bearer {token}'}
        params = {...}
        r = requests.get(self.base + '/search', headers=headers, params=params, timeout=60)
        r.raise_for_status()
        return r.json()['results']

    def download_stream(self, download_url, dest_path):
        token = self.authenticate()
        with requests.get(download_url, headers={'Authorization': f'Bearer {token}'}, stream=True) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as fh:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    fh.write(chunk)
```

Download & upload notes
- Always stream downloads to disk; do not load entire file into memory.
- Compute SHA256 while streaming or in a single pass after download.
- Use multipart upload if MinIO endpoint and file size require it.
- Validate size and checksum if Bhoonidhi exposes checksums.
- On failure, remove partial object from MinIO and mark DB row `status='failed'`.

Batch Job — download and convert to TIF/COG
-----------------------------------------

Use the repository's `scripts/prepare_sentinel2_l2a_cogs.py` to prepare Sentinel-2 L2A SAFE ZIPs into `analytic.tif` (9-band) and `scl.tif` (1-band) COGs and a `prepare_manifest.json` describing outputs. Run this inside the ingestion container to avoid local GDAL dependency issues.

Single-product conversion (dev):

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
    python scripts/prepare_sentinel2_l2a_cogs.py --zip-path data/raw/sentinel-2-l2a/<PRODUCT_ID>/<PRODUCT_ID>.SAFE.zip --overwrite
```

Batch conversion via selection manifest:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm ingestion-worker \
    python scripts/prepare_sentinel2_l2a_cogs.py --selection-manifest data/seed/selection.json --overwrite
```

Integration patterns:
- Inline: the ingest worker downloads, runs `prepare_*`, uploads the COG outputs, then upserts DB row.
- Decoupled: ingest worker stages raw archive to MinIO and enqueues a `prepare-cogs` batch task (separate worker type) that performs conversion and final upload. This isolates heavy GDAL work to dedicated hosts.

Validation & artifacts:
- The script validates COGs (via `rio_cogeo`) by default — check the produced `prepare_manifest.json` for raster summaries and bounding geometry.
- Store the `prepare_manifest.json` alongside the COGs in MinIO for auditing and quick verification.

Resource guidance:
- Limit concurrent conversions per host (2–4), mount ample ephemeral disk (tens of GBs per concurrent job), and clean up temporary files after successful conversion.

Idempotency and concurrency
- Compute `scene_key` (deterministic from product metadata) and enforce `UNIQUE(scene_key)`.
- Use DB upsert (`ON CONFLICT(scene_key) DO UPDATE`) when writing metadata.
- Optionally use Redis distributed lock per `scene_key` during download+upload to avoid duplicate concurrent ingestion.

Monitoring, metrics & alerts
- Metrics to expose: `bhoonidhi_ingest_success_total`, `bhoonidhi_ingest_failure_total`, `bhoonidhi_download_bytes_total`, `bhoonidhi_ingest_duration_seconds`.
- Example Prometheus alert:

```yaml
- alert: BhoonidhiIngestFailures
  expr: increase(bhoonidhi_ingest_failure_total[1h]) > 0
  for: 15m
  labels:
    severity: page
  annotations:
    summary: "Bhoonidhi ingest failures detected"
```

- Send exceptions to Sentry and push critical alerts to Slack/PagerDuty.

Testing & local validation

Run a local/dev stack (MinIO + Postgres + Redis) and run Celery in eager mode for CI:

```bash
# start local services (example using docker-compose)
docker compose -f infra/docker/local-stack.yml up -d

# run unit + integration tests
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=minio
export MINIO_SECRET_KEY=minio123
export DATABASE_URL=postgresql://user:pass@localhost:5432/akasha
export CELERY_BROKER_URL=redis://localhost:6379/0
pytest tests/test_bhoonidhi_ingest.py -q

# run the celery worker locally (dev)
celery -A ingest.app worker --loglevel=info -Q default
# run beat
celery -A ingest.app beat --loglevel=info
```

Troubleshooting checklist

1. Task never started: check Celery Beat logs, confirm schedule/timezone, check broker health.
2. Authentication errors: check Bhoonidhi credentials and client secret; test `curl` to auth endpoint.
3. Download failures: inspect worker logs, check network egress, verify NRSC whitelist and test external IP from worker host:

```bash
curl https://api.ipify.org
curl -v --header "Authorization: Bearer $TOKEN" "${BHOONIDHI_API_BASE}/some/health"
```

4. Upload failures: check MinIO logs, credentials, and bucket policy; reproduce with `mc` or `aws s3` CLI.
5. Partial objects: delete partial keys from MinIO, mark DB row `failed`, re-queue ingestion.

Re-run & recovery
- To re-run a failed product: set `status='pending'` and enqueue `ingest_single_product` task for that `scene_key`.
- To re-run an entire day: set `since` to start of day and run `search_and_ingest` manually.

Lifecycle & cleanup
- Apply MinIO lifecycle policies to move older objects to cheaper storage or delete after retention period.

Emergency rollback
- If mass-corruption detected, pause Celery Beat, remove affected objects, revert DB rows, and re-run from a verified date window.

References
- Bhoonidhi API docs (internal).
- MinIO multipart upload docs.
- Celery docs: task retrying and beat scheduling.
