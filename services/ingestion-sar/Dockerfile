# Akasha Sentinel-1 SAR preprocessing image.
# Build context = repository root:
#   docker build -f services/ingestion-sar/Dockerfile -t akasha-ingestion-sar .
FROM python:3.11.14-slim-bookworm

ARG SNAP_INSTALLER_URL="https://download.esa.int/step/snap/13.0/installers/esa-snap_sentinel_linux-13.0.0.sh"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SNAP_HOME=/opt/snap \
    SNAP_USER_DIR=/snap-cache \
    SNAP_CACHE_SIZE=8G \
    SNAP_PARALLELISM=4 \
    AKASHA_S1_VV_RESCALE="-25,5" \
    AKASHA_S1_VH_RESCALE="-30,-5" \
    PATH="/opt/snap/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      fontconfig \
      libexpat1 \
      libgomp1 \
      openjdk-17-jre-headless \
      unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --retry 3 --retry-delay 5 --progress-bar \
  "${SNAP_INSTALLER_URL}" -o /tmp-snap-installer.sh \
    && sh /tmp-snap-installer.sh -q -dir "${SNAP_HOME}" -overwrite \
    && rm -f /tmp-snap-installer.sh \
    && mkdir -p "${SNAP_USER_DIR}" /app/data /app/scripts

RUN pip install --no-cache-dir --prefer-binary \
      "numpy>=1.26,<3" \
      rasterio==1.4.3 \
      rio-cogeo==5.4.2

COPY scripts/prepare_sentinel1_grd_cogs.py ./scripts/prepare_sentinel1_grd_cogs.py
COPY services/ingestion/snap ./services/ingestion/snap

VOLUME ["/app/data", "/snap-cache"]

HEALTHCHECK --interval=1m --timeout=20s --start-period=2m --retries=3 \
  CMD /opt/snap/bin/gpt -h >/dev/null 2>&1 && python scripts/prepare_sentinel1_grd_cogs.py --help >/dev/null

CMD ["python", "scripts/prepare_sentinel1_grd_cogs.py", "--help"]
