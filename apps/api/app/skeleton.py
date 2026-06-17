"""Canonical Slice 0 skeleton metadata for the Akasha MVP.

This module is the single source of truth for:
  * the multi-service topology (service registry)
  * pinned container image versions
  * the documented environment-variable matrix (placeholders only)
  * the slice/phase roadmap and explicit in/out-of-scope lists

It is intentionally pure data + tiny helpers so it can be imported by the
live Emergent preview backend AND shipped inside the `api` container image
identically (no filesystem dependency).
"""

# ruff: noqa: E501
from __future__ import annotations

from typing import Any

APP_NAME = "Akasha"
SLICE = 0
SLICE_NAME = "Skeleton"

# --------------------------------------------------------------------------
# Pinned container images (engineering-dos-donts.md: pin GDAL/rasterio/
# rio-tiler/TiTiler; do not use floating `latest` for raster services).
# --------------------------------------------------------------------------
PINNED_IMAGES: dict[str, str] = {
    "gateway (web)": "caddy:2.10-alpine",
    "api base": "python:3.11-slim",
    "titiler": "ghcr.io/developmentseed/titiler:1.0.0",
    "stac-api": "ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2",
    "postgis": "postgis/postgis:16-3.5",
    "minio": "minio/minio:RELEASE.2025-09-07T16-13-09Z",
    "ingestion base": "python:3.11.14-slim-bookworm",
    "frontend build": "node:24-alpine",
}

# --------------------------------------------------------------------------
# Service registry (architecture-tech-stack.md topology). Only `web` is
# publicly reachable; everything else is private (internal Docker network).
# `internalPort` is the port the service listens on inside the private network.
# --------------------------------------------------------------------------
SERVICES: list[dict[str, Any]] = [
    {
        "id": "web",
        "name": "Web Gateway",
        "role": "Serves the built React SPA and reverse-proxies /api -> api and /tiles -> titiler. The only public origin.",
        "public": True,
        "runtime": "Caddy + static React (Vite build)",
        "image": "caddy:2.10-alpine",
        "build": "infra/gateway/Dockerfile (multi-stage: build apps/frontend, serve via Caddy)",
        "internalPort": 80,
        "healthPath": "/health",
        "healthType": "http",
        "persistentVolume": False,
        "dependsOn": ["api", "titiler"],
    },
    {
        "id": "api",
        "name": "FastAPI BFF",
        "role": "App config, catalog queries, plot CRUD, index orchestration, masked statistics (later slices). Thin BFF only.",
        "public": False,
        "runtime": "Uvicorn / FastAPI",
        "image": "python:3.11.14-slim-bookworm",
        "build": "apps/api/Dockerfile",
        "internalPort": 8000,
        "healthPath": "/health",
        "healthType": "http",
        "persistentVolume": False,
        "dependsOn": ["postgis", "stac-api", "titiler"],
    },
    {
        "id": "titiler",
        "name": "TiTiler",
        "role": "RGB display tiles + optional index display overlays from COGs in MinIO. Not used for masked statistics.",
        "public": False,
        "runtime": "TiTiler (rio-tiler / GDAL)",
        "image": "ghcr.io/developmentseed/titiler:1.0.0",
        "build": "services/titiler/Dockerfile",
        "internalPort": 8000,
        "healthPath": "/healthz",
        "healthType": "http",
        "persistentVolume": False,
        "dependsOn": ["minio"],
    },
    {
        "id": "stac-api",
        "name": "STAC API (pgSTAC)",
        "role": "Catalog collections/items, date/source discovery, asset metadata via stac-fastapi-pgstac.",
        "public": False,
        "runtime": "stac-fastapi-pgstac",
        "image": "ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2",
        "build": "services/stac-api/Dockerfile",
        "internalPort": 8080,
        "healthPath": "/_mgmt/ping",
        "healthType": "http",
        "persistentVolume": False,
        "dependsOn": ["postgis"],
    },
    {
        "id": "postgis",
        "name": "PostgreSQL + PostGIS",
        "role": "Stored plots, pgSTAC catalog backend, app metadata.",
        "public": False,
        "runtime": "PostgreSQL 16 + PostGIS 3.5",
        "image": "postgis/postgis:16-3.5",
        "build": "image (no custom Dockerfile)",
        "internalPort": 5432,
        "healthPath": None,
        "healthType": "pg_isready",
        "persistentVolume": True,
        "dependsOn": [],
    },
    {
        "id": "minio",
        "name": "MinIO",
        "role": "S3-compatible COG object storage. Console disabled; private only.",
        "public": False,
        "runtime": "MinIO (S3-compatible)",
        "image": "minio/minio:RELEASE.2025-09-07T16-13-09Z",
        "build": "image (no custom Dockerfile)",
        "internalPort": 9000,
        "healthPath": "/minio/health/live",
        "healthType": "http",
        "persistentVolume": True,
        "dependsOn": [],
    },
    {
        "id": "ingestion-worker",
        "name": "Ingestion Worker",
        "role": "Manual/seed ingestion first; scheduled CDSE/Bhoonidhi ingestion later. No public HTTP surface.",
        "public": False,
        "runtime": "Python worker (CLI)",
        "image": "python:3.11-slim",
        "build": "services/ingestion/Dockerfile",
        "internalPort": None,
        "healthPath": None,
        "healthType": "process",
        "persistentVolume": False,
        "dependsOn": ["postgis", "stac-api", "minio"],
    },
]

# --------------------------------------------------------------------------
# Environment variable matrix (infra/selfhosted/env.example). Placeholders only.
# Do NOT add aliases beyond this matrix (per the deployment docs).
# --------------------------------------------------------------------------
ENV_MATRIX: dict[str, dict[str, str]] = {
    "web": {
        "PUBLIC_APP_NAME": "Akasha",
        "PUBLIC_DEFAULT_AOI_NAME": "Bangalore",
        "API_UPSTREAM_URL": "http://api:8000",
        "TITILER_UPSTREAM_URL": "http://titiler:8000",
        "VITE_BASEMAP_PROVIDER": "esri",
        "VITE_ESRI_API_KEY": "<referrer-restricted ArcGIS Location Platform key>",
        "VITE_ESRI_BASEMAP_STYLE": "arcgis/imagery",
        "VITE_ESRI_BASEMAP_STYLE_FAMILY": "arcgis",
        "VITE_ESRI_BASEMAP_PLACES": "none",
        "VITE_ESRI_BASEMAP_SESSION_SECONDS": "43200",
        "GATEWAY_BASIC_AUTH": "",
    },
    "api": {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://<user>:<password>@postgis:5432/<db>",
        "STAC_API_URL": "http://stac-api:8080",
        "TITILER_URL": "http://titiler:8000",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "AWS_ACCESS_KEY_ID": "<minio-access-key>",
        "AWS_SECRET_ACCESS_KEY": "<minio-secret-key>",
        "AWS_S3_ENDPOINT": "minio:9000",
        "AWS_VIRTUAL_HOSTING": "FALSE",
        "AWS_HTTPS": "NO",
        "AWS_REGION": "us-east-1",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
        "AKASHA_RGB_RESCALE": "0,3000",
        "DEFAULT_SOURCE_ID": "resourcesat-2a-liss3-boa",
        "DEFAULT_AOI_ID": "",
        "AOI_CONFIG_PATH": "/app/data/seed/bangalore-60km-aoi.geojson",
        "AOI_CONFIG_DIR": "/app/data/seed/aois",
        "BASEMAP_PROVIDER": "esri",
        "ESRI_BASEMAP_STYLE": "arcgis/imagery",
        "ESRI_BASEMAP_STYLE_FAMILY": "arcgis",
        "ESRI_BASEMAP_USAGE_MODEL": "session",
        "ESRI_BASEMAP_PLACES": "none",
        "ESRI_BASEMAP_SESSION_SECONDS": "43200",
        "USABLE_PIXEL_THRESHOLD_PERCENT": "70",
        "MAX_POLYGON_AREA_HA": "50",
        "MAX_POLYGON_VERTICES": "5000",
        "INDEX_REQUEST_TIMEOUT_SECONDS": "30",
        "RATE_LIMIT_INDEX_PER_MINUTE": "30",
        "MAX_REQUEST_BODY_BYTES": "1048576",
        "CORS_ALLOWED_ORIGINS": "https://<web-public-domain>",
        "AUTH_MODE": "enabled",
        "AUTH_ALLOW_DISABLED": "false",
        "AUTH_SESSION_COOKIE_NAME": "akasha_session",
        "AUTH_SESSION_TTL_MINUTES": "480",
        "AUTH_REMEMBER_TTL_DAYS": "30",
        "AUTH_PASSWORD_PEPPER": "<generated-secret>",
        "AUTH_ALLOW_SIGNUP": "false",
        "AUTH_COOKIE_SECURE": "true",
        "AUTH_LOGIN_RATE_LIMIT_PER_MINUTE": "10",
        "AUTH_SIGNUP_RATE_LIMIT_PER_HOUR": "20",
    },
    "titiler": {
        "PORT": "8000",
        "AWS_ACCESS_KEY_ID": "<minio-access-key>",
        "AWS_SECRET_ACCESS_KEY": "<minio-secret-key>",
        "AWS_S3_ENDPOINT": "minio:9000",
        "AWS_VIRTUAL_HOSTING": "FALSE",
        "AWS_HTTPS": "NO",
        "AWS_REGION": "us-east-1",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    },
    "stac-api": {
        "POSTGRES_HOST_READER": "postgis",
        "POSTGRES_HOST_WRITER": "postgis",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "<user>",
        "POSTGRES_PASS": "<password>",
        "POSTGRES_DBNAME": "<db>",
    },
    "postgis": {
        "POSTGRES_USER": "<generated>",
        "POSTGRES_PASSWORD": "<generated>",
        "POSTGRES_DB": "<db>",
    },
    "minio": {
        "MINIO_ROOT_USER": "<generated-user>",
        "MINIO_ROOT_PASSWORD": "<generated-password>",
        "MINIO_BROWSER": "off",
        "MINIO_SERVER_URL": "http://minio:9000",
    },
    "ingestion-worker": {
        "DATABASE_URL": "postgresql://<user>:<password>@postgis:5432/<db>",
        "STAC_API_URL": "http://stac-api:8080",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_ACCESS_KEY": "<access-key>",
        "S3_SECRET_KEY": "<secret-key>",
        "AOI_CONFIG_PATH": "/app/data/seed/bangalore-60km-aoi.geojson",
    },
}

# --------------------------------------------------------------------------
# Slice / phase roadmap (mvp-execution-plan.md). Slice 0 is active.
# --------------------------------------------------------------------------
ROADMAP: list[dict[str, str]] = [
    {"id": "slice0", "phase": "Phase 0", "name": "Repository & service skeleton", "status": "done"},
    {
        "id": "slice1",
        "phase": "Phase 1",
        "name": "Database, catalog & object storage",
        "status": "done",
    },
    {
        "id": "slice2",
        "phase": "Phase 2",
        "name": "Raster de-risk (tile + masked NDVI stat)",
        "status": "active",
    },
    {"id": "slice3", "phase": "Phase 3", "name": "BFF API implementation", "status": "planned"},
    {"id": "slice4", "phase": "Phase 4", "name": "Frontend map & layer UX", "status": "planned"},
    {"id": "slice5", "phase": "Phase 5", "name": "Plot & index UX", "status": "planned"},
    {
        "id": "slice6",
        "phase": "Phase 6",
        "name": "Deployment hardening",
        "status": "planned",
    },
    {"id": "slice7", "phase": "Phase 7", "name": "Acceptance & QA", "status": "planned"},
]

IN_SCOPE: list[str] = [
    "Monorepo structure: apps/{frontend,api}, services/{titiler,stac-api,ingestion}, infra/{gateway,docker,selfhosted}, docs, scripts",
    "Dockerfile per deployable service (web gateway, api, titiler, stac-api, ingestion)",
    "Local docker-compose.yml mirroring the deployment topology (private networking + volumes)",
    "Per-service Dockerfiles and a documented env matrix for deployment",
    ".env.example files with placeholders only (no secrets / no default credentials)",
    "Health endpoints + documented health paths for web, api, titiler, stac-api",
    "Shared formatting/linting conventions (ruff/black/isort, prettier, editorconfig)",
]

OUT_OF_SCOPE: list[str] = [
    "Storage/catalog logic: PostGIS schema, pgSTAC migrations, MinIO bucket structure (Slice 1)",
    "Raster: COG/SCL handling, TiTiler expressions, masked statistics, index math (Slice 2)",
    "BFF product contracts: /api/config, /api/sources, /api/layers/default, plot CRUD, /api/indices/statistics (Slice 3)",
    "Frontend product UX: MapLibre map, Terra Draw, layer/index panels (Slices 4-5)",
    "Deployment hardening & full smoke test, custom domains (Slice 6)",
    "Wave 2 features, user accounts/roles, ISRO/SAR sources, automated ingestion",
]


def service_registry(live_service_id: str = "api") -> list[dict[str, Any]]:
    """Return the service registry with a runtime `status` overlay.

    Only the currently-running service (the `api` answering this request) is
    reported as `live`. Every other service is `defined` because it only runs
    under Docker Compose (local) or as a separate deployed service. This is
    intentionally honest: we do not fake health for services that are not up.
    """
    out: list[dict[str, Any]] = []
    for svc in SERVICES:
        item = dict(svc)
        item["status"] = "live" if svc["id"] == live_service_id else "defined"
        item["liveInThisEnvironment"] = svc["id"] == live_service_id
        out.append(item)
    return out
