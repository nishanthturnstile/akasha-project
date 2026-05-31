"""rasterio-based dual-COG window reader (Slice 2 — Phase 2).

Reads the analytic COG window AND the SCL COG window for the SAME request
geometry. The two COGs share an identical grid (same CRS/transform/shape per the
prepared scene), so a single pixel window is used for both, which keeps the
arrays pixel-aligned for masked statistics.

rasterio is imported lazily: importing this module (and therefore the FastAPI
app) must not require GDAL/rasterio to be installed. The heavy import only
happens when an index-statistics request is actually served.

Supports `s3://bucket/key` (MinIO/S3 via GDAL /vsis3/), local file paths
(used by synthetic tests), and http(s) COGs.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from .errors import raster_backend_unavailable


@dataclass
class WindowRead:
    """Pixel-aligned analytic + SCL windows for one geometry."""

    band_arrays: dict[int, Any]  # 1-based position -> 2D numpy array (DN)
    scl: Any  # 2D numpy array (uint8)
    geometry_mask: Any  # 2D bool, True INSIDE polygon
    nodata: float | int
    height: int
    width: int
    intersects: bool


def gdal_s3_options() -> dict[str, str]:
    """GDAL/S3 options for reading MinIO COGs (server-side only).

    Mirrors the documented TiTiler env (AWS_S3_ENDPOINT, AWS_HTTPS,
    AWS_VIRTUAL_HOSTING, ...). Credentials come from the api service env and are
    never exposed to the browser.
    """
    opts: dict[str, str] = {
        "GDAL_DISABLE_READDIR_ON_OPEN": os.environ.get("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR"),
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": os.environ.get(
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff"
        ),
        "AWS_VIRTUAL_HOSTING": os.environ.get("AWS_VIRTUAL_HOSTING", "FALSE"),
        "AWS_HTTPS": os.environ.get("AWS_HTTPS", "NO"),
    }
    # Endpoint + creds (support both GDAL-style and Akasha-style var names).
    endpoint = os.environ.get("AWS_S3_ENDPOINT") or _strip_scheme(os.environ.get("S3_ENDPOINT_URL", ""))
    if endpoint:
        opts["AWS_S3_ENDPOINT"] = endpoint
    access = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("AWS_REGION") or os.environ.get("S3_REGION", "us-east-1")
    if access:
        opts["AWS_ACCESS_KEY_ID"] = access
    if secret:
        opts["AWS_SECRET_ACCESS_KEY"] = secret
    if region:
        opts["AWS_REGION"] = region
    return opts


def _strip_scheme(url: str) -> str:
    return url.split("://", 1)[-1] if "://" in url else url


def to_gdal_path(href: str) -> str:
    """Translate an asset href into a GDAL-openable path.

    s3://bucket/key -> /vsis3/bucket/key ; local + http(s) returned unchanged.
    """
    if href.startswith("s3://"):
        return "/vsis3/" + href[len("s3://") :]
    if href.startswith(("http://", "https://")):
        return "/vsicurl/" + href
    return href


def read_index_windows(
    *,
    analytic_href: str,
    scl_href: str,
    geometry: dict[str, Any],
    positions: list[int],
) -> WindowRead:
    """Read the analytic (selected positions) + SCL windows for a geometry.

    Raises AkashaError(503) if the raster backend (rasterio/GDAL or MinIO) is
    unavailable in this environment.
    """
    try:
        import numpy as np  # lazy
        import rasterio  # lazy
        from rasterio.features import bounds as feature_bounds
        from rasterio.features import geometry_mask
        from rasterio.warp import transform_geom
        from rasterio.windows import Window
    except ImportError as exc:  # pragma: no cover - environment guard
        raise raster_backend_unavailable(
            "Raster stack (rasterio/GDAL) is not installed in this environment.",
            reason=str(exc),
        ) from exc

    a_path = to_gdal_path(analytic_href)
    s_path = to_gdal_path(scl_href)
    env_opts = gdal_s3_options()

    try:
        with rasterio.Env(**env_opts):
            with rasterio.open(a_path) as a_ds:
                geom_ds = transform_geom("EPSG:4326", a_ds.crs, geometry)
                minx, miny, maxx, maxy = feature_bounds(geom_ds)
                inv = ~a_ds.transform
                c0, r0 = inv * (minx, maxy)  # upper-left
                c1, r1 = inv * (maxx, miny)  # lower-right
                col_off = max(0, int(math.floor(min(c0, c1))))
                row_off = max(0, int(math.floor(min(r0, r1))))
                col_end = min(a_ds.width, int(math.ceil(max(c0, c1))))
                row_end = min(a_ds.height, int(math.ceil(max(r0, r1))))
                width = col_end - col_off
                height = row_end - row_off
                if width <= 0 or height <= 0:
                    return WindowRead({}, None, None, a_ds.nodata or 0, 0, 0, intersects=False)
                win = Window(col_off, row_off, width, height)
                wt = a_ds.window_transform(win)
                band_arrays: dict[int, Any] = {}
                for pos in positions:
                    band_arrays[pos] = a_ds.read(pos, window=win)
                nodata = a_ds.nodata if a_ds.nodata is not None else 0
                mask = geometry_mask(
                    [geom_ds], out_shape=(height, width), transform=wt, invert=True
                )
            with rasterio.open(s_path) as s_ds:
                scl = s_ds.read(1, window=Window(col_off, row_off, width, height))
    except Exception as exc:  # noqa: BLE001
        # rasterio raises RasterioIOError (and friends) when MinIO/COGs are
        # unreachable — the expected Emergent-preview state.
        raise raster_backend_unavailable(
            "Could not read COG window from object storage.",
            reason=str(exc),
            analytic=analytic_href,
            scl=scl_href,
        ) from exc

    # Ensure SCL matches the analytic window shape (defensive).
    if scl.shape != (height, width):
        scl = np.asarray(scl)[:height, :width]
    return WindowRead(
        band_arrays=band_arrays,
        scl=scl,
        geometry_mask=mask,
        nodata=nodata,
        height=height,
        width=width,
        intersects=True,
    )
