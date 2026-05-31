"""TiTiler RGB tile URL building + same-origin proxy (Slice 2 — Phase 2).

The BFF exposes a friendly same-origin route
    GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png
and proxies it to the internal TiTiler service. This keeps MinIO object URLs and
credentials server-side (never exposed to the browser) and works behind the
Emergent ingress (which only routes /api/* to the backend).

Uses stdlib urllib for the proxy fetch (no extra dependency).
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request

from .errors import raster_backend_unavailable, upstream_error

# TiTiler 1.0 COG tile route. WebMercatorQuad is the default tile matrix set.
TILE_MATRIX_SET = "WebMercatorQuad"


def titiler_base_url() -> str:
    return os.environ.get("TITILER_URL", "").strip().rstrip("/")


def default_rgb_rescale() -> str:
    """Per-band rescale (raw uint16 DN) for a sensible true-colour stretch.

    Sentinel-2 L2A surface reflectance ~0..0.3 corresponds to DN ~0..3000
    (scale 0.0001). Overridable via AKASHA_RGB_RESCALE ("min,max").
    """
    return os.environ.get("AKASHA_RGB_RESCALE", "0,3000")


def build_rgb_tile_url(
    *,
    analytic_href: str,
    rgb_positions: list[int],
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    rescale: str | None = None,
    fmt: str = "png",
) -> str:
    """Build the internal TiTiler request URL for one true-colour RGB tile.

    Uses positional band selection (bidx) for B04/B03/B02 = [1, 8, 9] from the
    frozen analytic order. The analytic COG url stays server-side.
    """
    base = (titiler_url or titiler_base_url()).rstrip("/")
    rescale = rescale or default_rgb_rescale()
    path = f"/cog/tiles/{TILE_MATRIX_SET}/{z}/{x}/{y}.{fmt}"
    params: list[tuple[str, str]] = [("url", analytic_href)]
    for pos in rgb_positions:
        params.append(("bidx", str(pos)))
    # One rescale per band keeps the stretch consistent across R/G/B.
    for _ in rgb_positions:
        params.append(("rescale", rescale))
    return f"{base}{path}?{urllib.parse.urlencode(params)}"


def fetch_tile(url: str, timeout: float = 20.0) -> tuple[bytes, str]:
    """Server-side GET of a rendered tile from TiTiler. Returns (body, content_type)."""
    if not titiler_base_url():
        raise raster_backend_unavailable(
            "TiTiler is not configured (TITILER_URL unset) in this environment."
        )
    req = urllib.request.Request(url, headers={"Accept": "image/png,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "image/png")
            return body, ctype
    except Exception as exc:  # noqa: BLE001
        raise upstream_error(
            "TiTiler tile request failed.", code="TITILER_ERROR", reason=str(exc)
        ) from exc
