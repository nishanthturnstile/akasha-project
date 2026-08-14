# Akasha BFF (api) — image.
# Thin FastAPI orchestration layer. Private service (never public).
FROM python:3.11.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libraries and build dependencies required by rasterio/GDAL wheels (Slice 2 BFF statistics).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gdal-bin \
        libgdal-dev \
        python3-dev \
        libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Application code + Alembic app-schema baseline/revisions.
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Container/Compose health check target: GET /health
# The service listens on $PORT (defaults to 8000 to match the documented
# internal URL http://api:8000).
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/health').status==200 else 1)"

CMD ["sh", "-c", "attempt=0; until python -m app.cli db upgrade; do attempt=$((attempt+1)); if [ $attempt -ge 30 ]; then echo 'db upgrade failed after 30 attempts' >&2; exit 1; fi; echo \"postgis not ready (attempt $attempt/30), retrying in 2s\" >&2; sleep 2; done; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
