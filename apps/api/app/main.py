"""Akasha BFF (FastAPI).

Scope:
  Slice 0 (skeleton):
    * GET /health, GET /api/health
    * GET /api/_skeleton/{services,manifest,env-matrix}
  Slice 2 (Phase 2 raster de-risk) — product surface:
    * GET  /api/config
    * GET  /api/sources
    * GET  /api/sources/{sourceId}/dates
    * GET  /api/layers/default
    * GET  /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png  (BFF->TiTiler proxy)
    * POST /api/indices/statistics                                      (BFF masked NDVI)
  Slice 3 (Phase 3 BFF API) — plots:
    * GET/POST /api/plots, GET/PATCH/DELETE /api/plots/{plotId}
    * POST /api/plots/import/geojson, GET /api/plots[/{plotId}]/export.geojson

The `_skeleton` namespace stays separate from the product API so contracts stay
clean. Heavy geospatial deps (rasterio/shapely/pyproj) are imported lazily in
`app.raster.*` so importing this module never requires them (keeps the live
Emergent preview healthy).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ExceptionHandler

from . import skeleton
from .config import settings
from .ingestion_jobs import router as ingestion_jobs_router
from .raster.errors import (
    AkashaError,
    akasha_error_handler,
    request_validation_error_handler,
)
from .routers.account_router import router as account_router
from .routers.analytics_router import router as field_analytics_router
from .routers.auth_router import router as auth_router
from .routers.bhoonidhi_router import router as bhoonidhi_diagnostics_router
from .routers.crops_router import router as crops_router
from .routers.data_manager_router import router as data_manager_router
from .routers.field_exports_router import router as field_exports_router
from .routers.field_group_router import router as field_groups_router
from .routers.field_router import router as fields_router
from .routers.observations_router import router as observations_router
from .routers.operation_router import router as operations_router
from .routers.pipeline_proxy import router as pipeline_proxy_router
from .routers.plot_router import router as plots_router
from .routers.product_router import router as product_router
from .routers.report_router import router as reports_router
from .routers.risk_router import router as risk_router
from .routers.scout_task_router import router as scout_tasks_router
from .routers.season_router import router as seasons_router
from .source_monitoring import router as source_monitoring_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("akasha.api")

APP_VERSION = "0.3.0-slice3"
LIVE_SERVICE_ID = "api"


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Akasha BFF started (slice=%s, env=%s, version=%s)",
        skeleton.SLICE,
        settings.app_env,
        APP_VERSION,
    )
    yield


app = FastAPI(
    title="Akasha BFF",
    version=APP_VERSION,
    description=(
        "Akasha BFF. Serves health, skeleton visibility, product, "
        "plot, auth, operations, reporting, and raster-statistics APIs."
    ),
    lifespan=lifespan,
    # The public gateway only proxies /api/* to this service, so the OpenAPI
    # schema and interactive docs must live under that prefix to be reachable
    # at the same origin (e.g. http://<host>/api/docs).
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_max_request_body(request: Request, call_next):
    """Reject oversized JSON bodies before raster/stat work starts."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_request_body_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": "Request body exceeds MAX_REQUEST_BODY_BYTES.",
                    "details": {"maxRequestBodyBytes": settings.max_request_body_bytes},
                }
            },
        )
    return await call_next(request)


# --- Health (root) ---------------------------------------------------------
# Container/Compose health checks hit `/health` directly on the api container.


def _health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "api",
        "app": skeleton.APP_NAME,
        "slice": skeleton.SLICE,
        "sliceName": skeleton.SLICE_NAME,
        "version": APP_VERSION,
        "env": settings.app_env,
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    return _health_payload()


# --- /api router -----------------------------------------------------------
api_router = APIRouter(prefix="/api")


@api_router.get("/health", tags=["health"])
async def api_health() -> dict[str, Any]:
    """Same liveness payload, reachable through the gateway/ingress (`/api/*`)."""
    return _health_payload()


# --- /api/_skeleton router (Slice 0 ops/visibility only) -------------------
skeleton_router = APIRouter(prefix="/api/_skeleton", tags=["skeleton"])


@skeleton_router.get("/services")
async def get_services() -> dict[str, Any]:
    services: list[dict[str, Any]] = skeleton.service_registry(LIVE_SERVICE_ID)
    return {
        "app": skeleton.APP_NAME,
        "slice": skeleton.SLICE,
        "publicRule": (
            "Only the `web` gateway is publicly reachable; /api/* and /tiles/* "
            "are proxied same-origin to internal services."
        ),
        "liveServiceId": LIVE_SERVICE_ID,
        "count": len(services),
        "services": services,
    }


@skeleton_router.get("/env-matrix")
async def get_env_matrix() -> dict[str, Any]:
    return {
        "note": (
            "Placeholders only. Do not add aliases beyond this matrix "
            "(infra/selfhosted/env.example)."
        ),
        "services": skeleton.ENV_MATRIX,
    }


def _find_repo_root() -> Path | None:
    """Walk up from this file looking for the monorepo root.

    The root is identified by containing both `docs/` and `apps/`. Returns None
    inside the slim `api` container (where only `app/` is copied), in which case
    callers fall back to the embedded canonical manifest.
    """
    override = os.environ.get("REPO_ROOT")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.extend(Path(__file__).resolve().parents)
    for base in candidates:
        try:
            if (base / "docs").is_dir() and (base / "apps").is_dir():
                return base
        except OSError:
            continue
    return None


def _repo_tree(root: Path) -> dict[str, Any]:
    """Shallow, bounded tree (2 levels) of the monorepo for the dashboard."""
    top = ["apps", "services", "infra", "docs", "scripts"]
    tree: dict[str, Any] = {}
    for name in top:
        d = root / name
        if not d.is_dir():
            continue
        children: list[str] = []
        try:
            for child in sorted(d.iterdir()):
                if child.name.startswith("."):
                    continue
                children.append(child.name + ("/" if child.is_dir() else ""))
        except OSError:
            pass
        tree[name + "/"] = children
    return tree


@skeleton_router.get("/manifest")
async def get_manifest() -> dict[str, Any]:
    root = _find_repo_root()
    repo_tree = _repo_tree(root) if root else None
    return {
        "app": skeleton.APP_NAME,
        "slice": skeleton.SLICE,
        "sliceName": skeleton.SLICE_NAME,
        "version": APP_VERSION,
        "roadmap": skeleton.ROADMAP,
        "pinnedImages": skeleton.PINNED_IMAGES,
        "inScope": skeleton.IN_SCOPE,
        "outOfScope": skeleton.OUT_OF_SCOPE,
        "repoTree": repo_tree,
        "repoTreeSource": "filesystem" if repo_tree else "embedded",
    }


app.include_router(api_router)
app.include_router(skeleton_router)

# --- Field Analytics API ---------------------------------------------------
app.include_router(field_analytics_router)

# --- Pipeline stats/tile proxy API (Phase 5: opaque proxy) -----------------
app.include_router(pipeline_proxy_router)

# --- Field Exports API -----------------------------------------------------
app.include_router(field_exports_router)

# --- Reports API -----------------------------------------------------------
app.include_router(reports_router)

# --- Risk/Crop Intelligence API -------------------------------------------
app.include_router(risk_router)

# --- Reference / Lookup Data API -----------------------------------------
app.include_router(crops_router)

# --- Auth/Team/Admin/Notifications API ------------------------------------
app.include_router(auth_router)
app.include_router(account_router)

# --- Operations/Data APIs --------------------------------------------------
app.include_router(operations_router)
app.include_router(scout_tasks_router)
app.include_router(data_manager_router)
app.include_router(field_groups_router)
app.include_router(fields_router)
app.include_router(ingestion_jobs_router)
app.include_router(source_monitoring_router)

# --- Temporary staging diagnostics ----------------------------------------
app.include_router(bhoonidhi_diagnostics_router)

# --- Seasons API ------------------------------------------------------------
app.include_router(seasons_router)

# --- Product API (Slice 2: config/sources/dates/layers/tiles/statistics) ---
app.include_router(product_router)

# --- Observations API (Phase 11: best-observation resolver) ----------------
app.include_router(observations_router)

# --- Plot API (Slice 3: plot CRUD + GeoJSON import/export) -----------------
app.include_router(plots_router)

# Standard Akasha error shape: { "error": { code, message, details } }.
app.add_exception_handler(AkashaError, cast(ExceptionHandler, akasha_error_handler))
app.add_exception_handler(
    RequestValidationError,
    cast(ExceptionHandler, request_validation_error_handler),
)
