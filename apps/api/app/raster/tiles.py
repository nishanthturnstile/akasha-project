"""TiTiler URL building plus direct RGB tile rendering helpers.

The BFF exposes a friendly same-origin route
    GET /api/tiles/{sourceId}/{acquisitionDate}/rgb/{z}/{x}/{y}.png
and proxies it to the internal TiTiler service. This keeps MinIO object URLs and
credentials server-side (never exposed to the browser) and works behind the
Emergent ingress (which only routes /api/* to the backend).

Uses stdlib urllib for the proxy fetch (no extra dependency).
"""

from __future__ import annotations

import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .errors import mosaic_tiles_unavailable, raster_backend_unavailable, upstream_error
from .raster_reader import gdal_s3_options, rasterio_aws_session

# TiTiler 1.0 COG tile route. WebMercatorQuad is the default tile matrix set.
TILE_MATRIX_SET = "WebMercatorQuad"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", crc)


def _transparent_png() -> bytes:
    """Return a valid 1x1 RGBA transparent PNG."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack("!IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    # One scanline: filter byte 0, then transparent RGBA pixel.
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return (
        signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")
    )


# Used for TiTiler 404 tile misses at COG/scene edges so MapLibre can continue
# rendering without noisy failed tile requests. The COG URL and storage details
# remain server-side.
TRANSPARENT_PNG = _transparent_png()

MASKED_OVERLAY_RGBA = (208, 213, 221, 255)

_NDVI_REFERENCE_CLASSES: tuple[tuple[float, float, tuple[int, int, int]], ...] = (
    (-1.0, 0.0, (19, 24, 125)),
    (0.0, 0.15, (128, 70, 26)),
    (0.15, 0.30, (213, 0, 35)),
    (0.30, 0.45, (255, 83, 13)),
    (0.45, 0.60, (250, 201, 9)),
    (0.60, 0.75, (111, 202, 7)),
    (0.75, 0.90, (22, 153, 43)),
    (0.90, 1.0, (0, 88, 37)),
)

_OVERLAY_COLOR_STOPS: dict[str, tuple[tuple[float, tuple[int, int, int]], ...]] = {
    "NDVI": (
        (0.0, (215, 48, 39)),
        (0.5, (254, 224, 139)),
        (1.0, (26, 152, 80)),
    ),
    "NDRE": (
        (0.0, (215, 48, 39)),
        (0.5, (254, 224, 139)),
        (1.0, (26, 152, 80)),
    ),
    "MSAVI": (
        (0.0, (215, 48, 39)),
        (0.5, (254, 224, 139)),
        (1.0, (26, 152, 80)),
    ),
    "NDMI": (
        (0.0, (138, 90, 34)),
        (0.5, (216, 201, 138)),
        (1.0, (31, 111, 139)),
    ),
    "NDWI_GREEN_NIR": (
        (0.0, (202, 168, 106)),
        (0.5, (232, 224, 176)),
        (1.0, (22, 96, 168)),
    ),
}


def overlay_display_range(index_type: str) -> tuple[float, float]:
    """Return the semantic display range used for field overlay colorization."""
    if index_type.upper() == "NDVI":
        return -1.0, 1.0
    from .indices import get_index

    return get_index(index_type).display_rescale


def _ndvi_reference_palette(values):
    import numpy as np

    rgb = np.zeros(values.shape + (3,), dtype=np.uint8)
    for idx, (lower, upper, color) in enumerate(_NDVI_REFERENCE_CLASSES):
        if idx == len(_NDVI_REFERENCE_CLASSES) - 1:
            selected = (values >= lower) & (values <= upper)
        else:
            selected = (values >= lower) & (values < upper)
        rgb[selected] = np.array(color, dtype=np.uint8)
    rgb[values < _NDVI_REFERENCE_CLASSES[0][0]] = np.array(
        _NDVI_REFERENCE_CLASSES[0][2], dtype=np.uint8
    )
    rgb[values > _NDVI_REFERENCE_CLASSES[-1][1]] = np.array(
        _NDVI_REFERENCE_CLASSES[-1][2], dtype=np.uint8
    )
    return rgb


def _colorize_index_rgb(index_type: str, values, *, thresholds=(), palette=()):
    """Map index values to RGB using the EOS-style reference palette per index.

    NDVI uses the discrete reference classes; other indices use their continuous
    diverging ramp clamped to the index's display range.
    """
    import numpy as np

    if len(thresholds) == 5 and len(palette) == 6:
        colors = np.asarray(
            [tuple(int(value[i : i + 2], 16) for i in (1, 3, 5)) for value in palette],
            dtype=np.uint8,
        )
        bins = np.digitize(values, np.asarray(thresholds), right=False)
        return colors[np.clip(bins, 0, len(colors) - 1)]

    if index_type.upper() == "NDVI":
        return _ndvi_reference_palette(values)
    lo, hi = overlay_display_range(index_type)
    normalized = np.clip((values - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    palette = _OVERLAY_COLOR_STOPS.get(index_type.upper(), _OVERLAY_COLOR_STOPS["NDVI"])
    return _interpolate_palette(normalized, palette)


def titiler_base_url() -> str:
    return os.environ.get("TITILER_URL", "").strip().rstrip("/")


def default_rgb_rescale() -> str:
    """Per-band rescale (raw uint16 DN) for a sensible true-colour stretch.

    Sentinel-2 L2A surface reflectance ~0..0.3 corresponds to DN ~0..3000
    (scale 0.0001). Overridable via AKASHA_RGB_RESCALE ("min,max").
    """
    return os.environ.get("AKASHA_RGB_RESCALE", "0,3000")


def _parse_rescale_ranges(rescale: str, band_count: int) -> tuple[tuple[float, float], ...]:
    parts = [part.strip() for part in rescale.split(",")]
    if len(parts) != 2:
        raise ValueError(f"invalid rescale range: {rescale!r}")
    lower = float(parts[0])
    upper = float(parts[1])
    return tuple((lower, upper) for _ in range(band_count))


def render_rgb_tile(
    *,
    analytic_href: str,
    rgb_positions: list[int],
    z: int,
    x: int,
    y: int,
    rescale: str | None = None,
) -> tuple[bytes, str]:
    """Render a single-scene RGB/FCC tile directly in the BFF with rio-tiler.

    This bypasses the TiTiler HTTP endpoint for single-scene RGB/FCC requests.
    It keeps the same browser contract while avoiding TiTiler's intermittent
    HTTP 500 "Read failed" responses for valid interior tiles on some COGs.
    """
    try:
        import rasterio  # lazy
        from rio_tiler.io import Reader  # lazy
    except ImportError as exc:  # pragma: no cover - environment guard
        raise raster_backend_unavailable(
            "Raster stack (rio-tiler/rasterio) is not installed in this environment.",
            reason=str(exc),
        ) from exc

    if not rgb_positions:
        raise upstream_error(
            "RGB tile request is missing band positions.", code="MISSING_RGB_BANDS"
        )

    stretch = _parse_rescale_ranges(rescale or default_rgb_rescale(), len(rgb_positions))
    try:
        with rasterio.Env(rasterio_aws_session(), **gdal_s3_options()):
            with Reader(analytic_href) as cog:
                image = cog.tile(x, y, z, indexes=tuple(rgb_positions))
                image.rescale(stretch)
                return image.render(img_format="PNG"), "image/png"
    except Exception as exc:  # noqa: BLE001
        raise upstream_error(
            "Direct RGB tile render failed.", code="RGB_TILE_RENDER_ERROR"
        ) from exc


def _rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    """Encode an RGBA image buffer into a PNG without extra dependencies."""
    if width <= 0 or height <= 0:
        return TRANSPARENT_PNG
    stride = width * 4
    if len(rgba) != stride * height:
        raise ValueError("RGBA buffer size does not match width*height*4.")

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)
    scanlines = bytearray()
    for row in range(height):
        start = row * stride
        scanlines.append(0)
        scanlines.extend(rgba[start : start + stride])
    idat = zlib.compress(bytes(scanlines))
    return (
        signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")
    )


def _interpolate_palette(
    normalized_values,
    stops: tuple[tuple[float, tuple[int, int, int]], ...],
):
    import numpy as np

    rgb = np.zeros(normalized_values.shape + (3,), dtype=np.uint8)
    if len(stops) < 2:
        return rgb

    for idx, (left_stop, right_stop) in enumerate(zip(stops, stops[1:], strict=True)):
        left_value, left_color = left_stop
        right_value, right_color = right_stop
        if idx == len(stops) - 2:
            segment = (normalized_values >= left_value) & (normalized_values <= right_value)
        else:
            segment = (normalized_values >= left_value) & (normalized_values < right_value)
        if not np.any(segment):
            continue
        width = max(right_value - left_value, 1e-6)
        factor = (normalized_values[segment] - left_value) / width
        for channel in range(3):
            rgb[..., channel][segment] = np.clip(
                np.round(
                    left_color[channel] + (right_color[channel] - left_color[channel]) * factor
                ),
                0,
                255,
            ).astype(np.uint8)

    low_color = np.array(stops[0][1], dtype=np.uint8)
    high_color = np.array(stops[-1][1], dtype=np.uint8)
    rgb[normalized_values <= stops[0][0]] = low_color
    rgb[normalized_values >= stops[-1][0]] = high_color
    return rgb


def render_field_index_overlay_png(
    *,
    index_type: str,
    index_values,
    valid_mask,
    masked_mask,
    thresholds=(),
    palette=(),
) -> tuple[bytes, str]:
    """Render a field-clipped index overlay as RGBA PNG.

    `valid_mask` identifies pixels to colorize from `index_values`. `masked_mask`
    identifies pixels inside the field that should render as light-grey
    cloud/nodata holes. Everything else stays fully transparent.
    """
    import numpy as np

    values = np.asarray(index_values, dtype="float64")
    valid = np.asarray(valid_mask, dtype=bool)
    masked = np.asarray(masked_mask, dtype=bool)
    if values.ndim != 2 or valid.shape != values.shape or masked.shape != values.shape:
        raise ValueError("Overlay inputs must be 2D arrays with matching shapes.")
    if values.size == 0:
        return TRANSPARENT_PNG, "image/png"

    height, width = values.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)

    if np.any(masked):
        rgba[masked] = MASKED_OVERLAY_RGBA

    finite_valid = valid & np.isfinite(values)
    if np.any(finite_valid):
        rgb = _colorize_index_rgb(index_type, values, thresholds=thresholds, palette=palette)
        rgba[finite_valid, :3] = rgb[finite_valid]
        rgba[finite_valid, 3] = 255

    invalid_valid = valid & ~np.isfinite(values)
    if np.any(invalid_valid):
        rgba[invalid_valid] = MASKED_OVERLAY_RGBA

    if not np.any(rgba[..., 3]):
        return TRANSPARENT_PNG, "image/png"
    return _rgba_png(width, height, rgba.tobytes()), "image/png"


def _overlay_supersample() -> int:
    try:
        return max(1, int(os.environ.get("AKASHA_OVERLAY_SUPERSAMPLE", "3") or 3))
    except ValueError:
        return 3


def _overlay_max_dim() -> int:
    try:
        return max(256, int(os.environ.get("AKASHA_OVERLAY_MAX_DIM", "2048") or 2048))
    except ValueError:
        return 2048


def encode_rgba_png(rgba) -> bytes:
    """Encode an (H, W, 4) uint8 RGBA ndarray to PNG bytes (transparent if empty)."""
    import numpy as np

    arr = np.ascontiguousarray(np.asarray(rgba, dtype=np.uint8))
    if arr.ndim != 3 or arr.shape[2] != 4 or arr.size == 0:
        return TRANSPARENT_PNG
    if not arr[..., 3].any():
        return TRANSPARENT_PNG
    height, width = arr.shape[:2]
    return _rgba_png(width, height, arr.tobytes())


def reproject_index_overlay_web_mercator(
    *,
    index_type: str,
    index_values,
    data_valid,
    data_masked,
    src_transform,
    src_crs,
    geometry,
    supersample: int | None = None,
    max_dim: int | None = None,
    thresholds=(),
    palette=(),
):
    """Reproject a field index window to a north-up Web Mercator overlay.

    EOS-style pixel-perfect overlay: the native analytic window (UTM, ~24 m for
    ResourceSat LISS-3) is reprojected to EPSG:3857 and supersampled so the
    heatmap is smooth, the index is bilinearly resampled, and the field polygon
    is rasterized crisply at the fine output grid so the clip hugs the boundary
    instead of stair-stepping at the native pixel size. Because the output is a
    north-up Web Mercator raster, the returned corners form an axis-aligned
    rectangle that aligns exactly with the MapLibre basemap (no quad rotation
    from the source UTM grid). `data_valid`/`data_masked` are per-pixel and must
    NOT pre-clip to the polygon; the polygon clip is applied here at fine
    resolution.

    Returns `(rgba_ndarray, corners)` where corners are [TL, TR, BR, BL] lng/lat.
    """
    import numpy as np
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.transform import array_bounds, from_bounds
    from rasterio.warp import reproject, transform, transform_bounds, transform_geom

    supersample = _overlay_supersample() if supersample is None else max(1, supersample)
    max_dim = _overlay_max_dim() if max_dim is None else max(1, max_dim)

    values = np.asarray(index_values, dtype="float64")
    valid = np.asarray(data_valid, dtype=bool)
    masked = np.asarray(data_masked, dtype=bool)
    height, width = values.shape

    left, bottom, right, top = array_bounds(height, width, src_transform)
    dst_crs = "EPSG:3857"
    mleft, mbottom, mright, mtop = transform_bounds(
        src_crs, dst_crs, left, bottom, right, top, densify_pts=21
    )

    src_res = (abs(src_transform.a) + abs(src_transform.e)) / 2.0 or 1.0
    out_res = max(src_res / supersample, 1.0)
    out_w = max(1, int(round((mright - mleft) / out_res)))
    out_h = max(1, int(round((mtop - mbottom) / out_res)))
    scale = max(out_w / max_dim, out_h / max_dim, 1.0)
    if scale > 1.0:
        out_w = max(1, int(out_w / scale))
        out_h = max(1, int(out_h / scale))
    out_transform = from_bounds(mleft, mbottom, mright, mtop, out_w, out_h)

    common = {
        "src_transform": src_transform,
        "src_crs": src_crs,
        "dst_transform": out_transform,
        "dst_crs": dst_crs,
    }
    out_index = np.full((out_h, out_w), np.nan, dtype="float64")
    reproject(
        values,
        out_index,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
        **common,
    )
    out_valid = np.zeros((out_h, out_w), dtype="float32")
    reproject(valid.astype("float32"), out_valid, resampling=Resampling.bilinear, **common)
    out_masked = np.zeros((out_h, out_w), dtype="float32")
    reproject(masked.astype("float32"), out_masked, resampling=Resampling.bilinear, **common)

    geom_3857 = transform_geom("EPSG:4326", dst_crs, geometry)
    poly = rasterize(
        [(geom_3857, 1)],
        out_shape=(out_h, out_w),
        transform=out_transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    ).astype(bool)

    rgba = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    valid_b = poly & (out_valid >= 0.5) & np.isfinite(out_index)
    masked_b = poly & ~valid_b & (out_masked >= 0.5)
    if np.any(valid_b):
        rgb = _colorize_index_rgb(index_type, out_index, thresholds=thresholds, palette=palette)
        rgba[valid_b, :3] = rgb[valid_b]
        rgba[valid_b, 3] = 255
    if np.any(masked_b):
        rgba[masked_b] = MASKED_OVERLAY_RGBA

    xs, ys = transform(
        dst_crs,
        "EPSG:4326",
        [mleft, mright, mright, mleft],
        [mtop, mtop, mbottom, mbottom],
    )
    corners = [[round(float(x), 10), round(float(y), 10)] for x, y in zip(xs, ys, strict=True)]
    return rgba, corners


def default_sar_vv_rescale() -> str:
    """Default VV backscatter dB display stretch for SAR context layers."""
    return os.environ.get("AKASHA_SAR_VV_RESCALE") or os.environ.get(
        "AKASHA_S1_VV_RESCALE", "-25,5"
    )


def build_sar_vv_grayscale_tile_url(
    *,
    backscatter_href: str,
    vv_position: int = 1,
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    rescale: str | None = None,
    fmt: str = "png",
) -> str:
    """Build the internal TiTiler request URL for a SAR VV grayscale tile."""
    base = (titiler_url or titiler_base_url()).rstrip("/")
    rescale = rescale or default_sar_vv_rescale()
    path = f"/cog/tiles/{TILE_MATRIX_SET}/{z}/{x}/{y}.{fmt}"
    params: list[tuple[str, str]] = [
        ("url", backscatter_href),
        ("bidx", str(vv_position)),
        ("rescale", rescale),
        ("colormap_name", "gray"),
    ]
    return f"{base}{path}?{urllib.parse.urlencode(params)}"


def default_sentinel1_vv_rescale() -> str:
    """Backward-compatible alias for the legacy Sentinel-1 helper name."""
    return default_sar_vv_rescale()


def build_sentinel1_vv_tile_url(
    *,
    backscatter_href: str,
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    rescale: str | None = None,
    fmt: str = "png",
) -> str:
    """Backward-compatible alias for the legacy Sentinel-1 helper name."""
    return build_sar_vv_grayscale_tile_url(
        backscatter_href=backscatter_href,
        z=z,
        x=x,
        y=y,
        titiler_url=titiler_url,
        rescale=rescale,
        fmt=fmt,
    )


def build_context_tile_url(
    *,
    asset_href: str,
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    rescale: str | None = None,
    bidx: list[int] | None = None,
    colormap_name: str | None = None,
    fmt: str = "png",
) -> str:
    """Build an internal TiTiler URL for a source-declared context COG."""
    base = (titiler_url or titiler_base_url()).rstrip("/")
    path = f"/cog/tiles/{TILE_MATRIX_SET}/{z}/{x}/{y}.{fmt}"
    params: list[tuple[str, str]] = [("url", asset_href)]
    for pos in bidx or []:
        params.append(("bidx", str(pos)))
    if rescale:
        repeats = max(1, len(bidx or []))
        for _ in range(repeats):
            params.append(("rescale", rescale))
    if colormap_name:
        params.append(("colormap_name", colormap_name))
    return f"{base}{path}?{urllib.parse.urlencode(params)}"


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


def build_index_tile_url(
    *,
    analytic_href: str,
    expression: str,
    rescale: str,
    colormap_name: str,
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    fmt: str = "png",
) -> str:
    """Build an internal TiTiler URL for one colorized index tile.

    TiTiler computes the index from the analytic COG via a band-math ``expression``
    (reflectance correction baked in by the caller), stretches it across ``rescale``
    and applies ``colormap_name``. The analytic COG url stays server-side.
    """
    base = (titiler_url or titiler_base_url()).rstrip("/")
    path = f"/cog/tiles/{TILE_MATRIX_SET}/{z}/{x}/{y}.{fmt}"
    params: list[tuple[str, str]] = [
        ("url", analytic_href),
        ("expression", expression),
        ("rescale", rescale),
        ("colormap_name", colormap_name),
    ]
    return f"{base}{path}?{urllib.parse.urlencode(params)}"


def build_mosaic_rgb_tile_url(
    *,
    analytic_hrefs: list[str],
    rgb_positions: list[int],
    z: int,
    x: int,
    y: int,
    titiler_url: str | None = None,
    rescale: str | None = None,
    fmt: str = "png",
) -> str:
    """Build an RGB tile URL only when the date resolves to one COG.

    TiTiler 1.0.0's deployed image has not been verified to accept ad-hoc
    multi-COG mosaics via repeated ``url=`` parameters. Until a supported
    MosaicJSON/pgSTAC backend is configured, multi-scene dates fail explicitly
    without exposing asset hrefs to the browser.
    """
    if len(analytic_hrefs) == 1:
        return build_rgb_tile_url(
            analytic_href=analytic_hrefs[0],
            rgb_positions=rgb_positions,
            z=z,
            x=x,
            y=y,
            titiler_url=titiler_url,
            rescale=rescale,
            fmt=fmt,
        )

    raise mosaic_tiles_unavailable(
        "Date-level RGB tiles for multiple scenes require a configured mosaic backend.",
        sceneCount=len(analytic_hrefs),
        supportedSceneCount=1,
    )


def fetch_feature_overlay(
    *,
    analytic_href: str,
    feature: dict,
    expression: str,
    rescale: str,
    colormap_name: str,
    width: int,
    height: int,
    resampling: str = "bilinear",
    titiler_url: str | None = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    """Render an index image CLIPPED to a GeoJSON feature via TiTiler /cog/feature.

    TiTiler computes the index `expression` from the analytic COG over the
    feature's bounding box, colorizes it, and sets pixels OUTSIDE the polygon
    transparent — i.e. the EOS-style field-clipped overlay. `width`/`height` force
    a higher output resolution so the polygon edge rasterizes smoothly (instead of
    blocky native COG pixels); `resampling` smooths the index gradient. The analytic
    COG url and storage details stay server-side. Returns (png_bytes, content_type).
    """
    base = (titiler_url or titiler_base_url()).rstrip("/")
    if not base:
        raise raster_backend_unavailable(
            "TiTiler is not configured (TITILER_URL unset) in this environment."
        )
    qs = urllib.parse.urlencode(
        {
            "url": analytic_href,
            "expression": expression,
            "rescale": rescale,
            "colormap_name": colormap_name,
            "width": int(width),
            "height": int(height),
            "resampling": resampling,
        }
    )
    url = f"{base}/cog/feature.png?{qs}"
    body = json.dumps(feature).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "image/png,*/*"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read(), resp.headers.get("Content-Type", "image/png")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return TRANSPARENT_PNG, "image/png"
        raise upstream_error(
            "TiTiler feature-overlay request failed.", code="TITILER_ERROR"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise upstream_error(
            "TiTiler feature-overlay request failed.", code="TITILER_ERROR"
        ) from exc


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
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return TRANSPARENT_PNG, "image/png"
        raise upstream_error("TiTiler tile request failed.", code="TITILER_ERROR") from exc
    except Exception as exc:  # noqa: BLE001
        raise upstream_error("TiTiler tile request failed.", code="TITILER_ERROR") from exc
