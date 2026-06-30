# Akasha ingestion worker — Slice 1 image.
# Manual/seed ingestion: pgSTAC migrate, idempotent STAC + MinIO seeding.
# No public HTTP surface. Build context = repository ROOT (needs data/seed).
#   docker build -f services/ingestion/Dockerfile -t akasha-ingestion .
FROM python:3.11.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libraries and build dependencies required by rasterio/GDAL wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gdal-bin \
        libgdal-dev \
        python3-dev \
        libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY services/ingestion/requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Worker code + ingestion package + committed seed assets (no large rasters).
COPY services/ingestion/worker.py ./
COPY services/ingestion/akasha_ingest ./akasha_ingest
COPY scripts/prepare_sentinel2_l2a_cogs.py ./scripts/prepare_sentinel2_l2a_cogs.py
COPY scripts/prepare_resourcesat_liss3_boa_cogs.py ./scripts/prepare_resourcesat_liss3_boa_cogs.py
COPY scripts/prepare_eos04_sar_mrs_l2b_cogs.py ./scripts/prepare_eos04_sar_mrs_l2b_cogs.py
COPY data/seed ./data/seed

# Default command prints resolved config, then exits.
# Seeding/verification are run on demand:
#   python worker.py seed     (idempotent: pgSTAC migrate -> load -> MinIO)
#   python worker.py verify   (ResourceSat default; pass --collection-id for legacy sources)
CMD ["python", "worker.py", "info"]
