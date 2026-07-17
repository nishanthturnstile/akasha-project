# Four-source production readiness

This runbook covers Sentinel-2 L2A and ResourceSat-2A LISS-3, LISS-4, and AWiFS.

## Runtime topology

- The developer MacBook is a thin client only.
- The Azure dev VM is used for source edits, tests, image builds, and local containers.
- `akasha-control` runs Coolify and the public web/BFF stack.
- `akasha-staging` runs standalone ingestion, Celery scheduler/workers, provider access,
  raster processing, storage, and readiness.
- Bhoonidhi downloads and raster processing must not move to the MacBook or `akasha-control`.

## Deployment prerequisites

The ingestion deployment preflight rejects a release unless all four schedules and readiness
contracts are enabled, Bhoonidhi credentials are present, provider execution is explicitly
approved, API authentication is configured, and signed URLs use a non-default secret.

Coolify must define `INGESTION_API_URL` and `INGESTION_API_KEY`. Field-index and readiness are
enabled by default, and ResourceSat cutover must contain exactly these IDs:

- `resourcesat-2a-liss3-boa`
- `resourcesat-2a-liss4-mx70-l2`
- `resourcesat-2a-awifs-boa`

The private ingestion URL must be reachable from the `api` container on `akasha-control`.

## Live acceptance

Run this on `akasha-control` or another trusted host that can reach both services. Put secrets in
environment variables or the shell's secret manager; do not put them in command arguments.

```bash
export AKASHA_APP_URL=https://<public-app-host>
export AKASHA_INGESTION_URL=https://<private-ingestion-host>
export AKASHA_INGESTION_API_KEY=<secret>
export AKASHA_APP_USERNAME=<acceptance-user>
export AKASHA_APP_PASSWORD=<secret>
export AKASHA_INGESTION_AOI_ID=bangalore_60km_geodesic_aoi
export AKASHA_ACCEPTANCE_FIELD_ID=<optional-owned-field-id>
python scripts/validate_four_source_runtime.py
```

The check fails unless every source is `AVAILABLE` with dates in ingestion, appears as
`pipelineBacked` in the product API, has an app-facing date, has a usable field date, and returns
NDVI statistics with matching source provenance.

Production-ready evidence consists of a passing deployment preflight, green repository test/build
suites, and a passing live acceptance run against the deployed VMs. Unit or mocked results do not
replace the live acceptance result.
