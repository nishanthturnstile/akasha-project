# Akasha ingestion worker — Slice 0 (skeleton).
#
# Manual/seed ingestion first; scheduled CDSE/Bhoonidhi ingestion later.
# No public HTTP surface. Runs on demand (one-shot commands).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py ./

# Default command prints the worker's resolved configuration and exits.
# Real ingestion subcommands (COG conversion, STAC registration, MinIO upload)
# are implemented in Slice 1+.
CMD ["python", "worker.py", "info"]
