"""rasterio-based dual-COG window reader.

Reads the analytic COG window AND the source mask COG window for the SAME request
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

from .errors import AkashaError, raster_backend_unavailable, upstream_error


@dataclass
class WindowRead:
    """Pixel-aligned analytic + mask windows for one geometry."""

    band_arrays: dict[int, Any]  # 1-based position -> 2D numpy array (DN)
    mask: Any  # 2D numpy array (uint8)
    geometry_mask: Any  # 2D bool, True INSIDE polygon
    nodata: float | int
    height: int
    width: int
    intersects: bool
    footprint_corners: list[list[float]] | None = None  # TL, TR, BR, BL in lng/lat
    window_transform: Any | None = None
    crs: Any | None = None


def gdal_s3_options() -> dict[str, str]:
    """Non-credential GDAL options for reading MinIO COGs (server-side only).

    Rasterio/GDAL's AWS credential options must be supplied via AWSSession, not
    directly in rasterio.Env. Credentials come from the api service env and are
    never exposed to the browser.
    """
    return {
        "GDAL_DISABLE_READDIR_ON_OPEN": os.environ.get("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR"),
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": os.environ.get(
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff"
        ),
    }


def _s3_endpoint_url() -> str | None:
    endpoint_url = os.environ.get("S3_ENDPOINT_URL", "").strip()
    if endpoint_url:
        return _strip_scheme(endpoint_url)
    endpoint = os.environ.get("AWS_S3_ENDPOINT", "").strip()
    if not endpoint:
        return None
    return _strip_scheme(endpoint)


def rasterio_aws_session():
    """Build a Rasterio AWSSession for authenticated MinIO/S3 COG reads."""
    from rasterio.session import AWSSession  # lazy; pulls boto3 only when needed

    os.environ.setdefault("AWS_VIRTUAL_HOSTING", "FALSE")
    os.environ.setdefault("AWS_HTTPS", "NO")
    return AWSSession(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
        or os.environ.get("S3_SECRET_KEY"),
        region_name=os.environ.get("AWS_REGION") or os.environ.get("S3_REGION", "us-east-1"),
        endpoint_url=_s3_endpoint_url(),
    )


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
    mask_href: str,
    geometry: dict[str, Any],
    positions: list[int],
) -> WindowRead:
    """Read the analytic (selected positions) + mask windows for a geometry.

    Raises AkashaError(503) if the raster backend (rasterio/GDAL or MinIO) is
    unavailable in this environment.
    """
    try:
        import numpy as np  # lazy
        import rasterio  # lazy
        from rasterio.features import bounds as feature_bounds
        from rasterio.features import geometry_mask
        from rasterio.warp import transform as transform_coords
        from rasterio.warp import transform_geom
        from rasterio.windows import Window
    except ImportError as exc:  # pragma: no cover - environment guard
        raise raster_backend_unavailable(
            "Raster stack (rasterio/GDAL) is not installed in this environment.",
            reason=str(exc),
        ) from exc

    a_path = to_gdal_path(analytic_href)
    m_path = to_gdal_path(mask_href)
    env_opts = gdal_s3_options()

    try:
        with rasterio.Env(rasterio_aws_session(), **env_opts):
            with rasterio.open(a_path) as a_ds:
                analytic_crs = a_ds.crs
                analytic_transform = a_ds.transform
                analytic_width = a_ds.width
                analytic_height = a_ds.height
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
                native_corners = [
                    wt * (0, 0),
                    wt * (width, 0),
                    wt * (width, height),
                    wt * (0, height),
                ]
                xs, ys = transform_coords(
                    a_ds.crs,
                    "EPSG:4326",
                    [pt[0] for pt in native_corners],
                    [pt[1] for pt in native_corners],
                )
                footprint_corners = [
                    [round(float(lng), 10), round(float(lat), 10)]
                    for lng, lat in zip(xs, ys, strict=True)
                ]
                band_arrays: dict[int, Any] = {}
                for pos in positions:
                    band_arrays[pos] = a_ds.read(pos, window=win)
                nodata = a_ds.nodata if a_ds.nodata is not None else 0
                mask = geometry_mask(
                    [geom_ds], out_shape=(height, width), transform=wt, invert=True
                )
            with rasterio.open(m_path) as m_ds:
                if (
                    m_ds.crs != analytic_crs
                    or m_ds.transform != analytic_transform
                    or m_ds.width != analytic_width
                    or m_ds.height != analytic_height
                ):
                    raise upstream_error(
                        "Analytic and mask rasters are not on the same pixel grid.",
                        code="RASTER_GRID_MISMATCH",
                        analyticCrs=str(analytic_crs),
                        maskCrs=str(m_ds.crs),
                        analyticShape=[analytic_height, analytic_width],
                        maskShape=[m_ds.height, m_ds.width],
                    )
                mask_arr = m_ds.read(1, window=Window(col_off, row_off, width, height))
    except AkashaError:
        raise
    except Exception as exc:  # noqa: BLE001
        # rasterio raises RasterioIOError (and friends) when MinIO/COGs are
        # unreachable — the expected Emergent-preview state.
        raise raster_backend_unavailable(
            "Could not read COG window from object storage.",
            reason=str(exc),
        ) from exc

    # Ensure mask matches the analytic window shape (defensive).
    if mask_arr.shape != (height, width):
        mask_arr = np.asarray(mask_arr)[:height, :width]
    return WindowRead(
        band_arrays=band_arrays,
        mask=mask_arr,
        geometry_mask=mask,
        nodata=nodata,
        height=height,
        width=width,
        intersects=True,
        footprint_corners=footprint_corners,
        window_transform=wt,
        crs=analytic_crs,
    )
