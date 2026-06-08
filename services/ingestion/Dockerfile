# Akasha ingestion worker — Slice 1 image.
# Manual/seed ingestion: pgSTAC migrate, idempotent STAC + MinIO seeding.
# No public HTTP surface. Build context = repository ROOT (needs data/seed).
#   docker build -f services/ingestion/Dockerfile -t akasha-ingestion .
FROM python:3.11.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libraries required by rasterio/GDAL wheels for SAFE JP2 decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY services/ingestion/requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Worker code + ingestion package + committed seed assets (no large rasters).
COPY services/ingestion/worker.py ./
COPY services/ingestion/akasha_ingest ./akasha_ingest
COPY scripts/prepare_sentinel2_l2a_cogs.py ./scripts/prepare_sentinel2_l2a_cogs.py
COPY data/seed ./data/seed

# Default command prints resolved config + sample scene, then exits.
# Seeding/verification are run on demand:
#   python worker.py seed     (idempotent: pgSTAC migrate -> load -> MinIO)
#   python worker.py verify   (Slice 1 exit criteria)
CMD ["python", "worker.py", "info"]
