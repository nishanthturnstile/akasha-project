"""Akasha BFF (FastAPI) — Slice 0 skeleton.

Scope (Slice 0):
  * GET /health                       -> liveness for Railway/Compose health checks
  * GET /api/health                   -> same payload, reachable through the gateway/ingress
  * GET /api/_skeleton/services       -> multi-service topology + live status overlay
  * GET /api/_skeleton/manifest       -> slice metadata, pinned images, scope, repo tree
  * GET /api/_skeleton/env-matrix     -> documented env-var matrix (placeholders only)

Intentionally NOT implemented in Slice 0 (later slices): /api/config, /api/sources,
/api/layers/default, plot CRUD, /api/indices/statistics, and any raster/catalog logic.
The `_skeleton` namespace keeps these ops endpoints separate from the future product
API contract so contracts stay clean.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from . import skeleton
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("akasha.api")

APP_VERSION = "0.0.0-slice0"
LIVE_SERVICE_ID = "api"


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Akasha BFF skeleton started (slice=%s, env=%s, version=%s)",
        skeleton.SLICE,
        settings.app_env,
        APP_VERSION,
    )
    yield


app = FastAPI(
    title="Akasha BFF",
    version=APP_VERSION,
    description="Akasha Railway MVP — Slice 0 (skeleton). Thin BFF; no product contracts yet.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Health (root) ---------------------------------------------------------
# Railway/Compose health checks hit `/health` directly on the api container.


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
            "(railway-deployment-guide.md)."
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
