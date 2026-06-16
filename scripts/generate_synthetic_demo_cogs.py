#!/usr/bin/env python3
"""Generate + upload SYNTHETIC demo COGs so the index/overlay pipeline renders.

This is a DEV/DEMO utility, not part of the real ingestion pipeline. Real COGs are
operator-provided (see docs/sentinel-2-l2a-cog-prep-runbook.md). It exists only so
the EOS-style colorized index overlay can be exercised end-to-end without a real
Bhoonidhi/CDSE download in a dev environment.

It writes a 4-band ResourceSat-2A LISS-3 analytic COG (BAND2/3/4/5 = green/red/
nir/swir, uint16, scale 0.0001) with a smooth, realistic NDVI gradient, plus a
1-band "all valid" mask COG, and uploads both to MinIO at the deterministic keys
declared by the seed STAC item.

Run inside the ingestion image (has rasterio + boto3 + numpy):
    docker compose -f infra/docker/docker-compose.yml run --rm \
        ingestion-worker python /app/scripts/generate_synthetic_demo_cogs.py
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds

# --- Target scene (matches data/seed/stac/resourcesat-2a-liss3-boa-sample-item.json)
BUCKET = os.environ.get("AKASHA_COG_BUCKET", "akasha-cogs")
KEY_PREFIX = "resourcesat-2a-liss3-boa/composite/bangalore-60km/2026-03-19"
ANALYTIC_KEY = f"{KEY_PREFIX}/analytic.tif"
MASK_KEY = f"{KEY_PREFIX}/mask.tif"

# Full AOI footprint bbox (lon/lat) from the seed item, and its declared CRS.
LONLAT_BBOX = (77.023647, 12.537266, 78.131561, 13.61645)
DST_EPSG = 32643  # UTM 43N
MAX_DIM = 3000  # cap the longest raster side; ~40 m/px over the 120 km AOI

SCALE = 0.0001  # DN -> reflectance


def _s3_client():
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _grid() -> tuple[int, int, rasterio.Affine, rasterio.crs.CRS]:
    from rasterio.crs import CRS

    left, bottom, right, top = transform_bounds("EPSG:4326", f"EPSG:{DST_EPSG}", *LONLAT_BBOX)
    span_x, span_y = right - left, top - bottom
    res = max(span_x, span_y) / MAX_DIM
    width = max(1, int(round(span_x / res)))
    height = max(1, int(round(span_y / res)))
    transform = from_bounds(left, bottom, right, top, width, height)
    return width, height, transform, CRS.from_epsg(DST_EPSG)


def _ndvi_field(height: int, width: int) -> np.ndarray:
    """Smooth NDVI surface in [~0.05, ~0.85] with a diagonal trend + low-freq texture."""
    yy, xx = np.mgrid[0:height, 0:width].astype("float64")
    gx, gy = xx / max(1, width - 1), yy / max(1, height - 1)
    # High NDVI toward the lower-left (green), low toward the upper-right (red).
    diagonal = 1.0 - 0.5 * (gx + (1.0 - gy))
    texture = (
        0.08 * np.sin(2 * np.pi * (1.5 * gx + 0.7))
        + 0.06 * np.cos(2 * np.pi * (1.9 * gy + 0.3))
    )
    rng = np.random.default_rng(20260319)
    noise = rng.normal(0.0, 0.015, size=(height, width))
    return np.clip(0.45 + 0.42 * (diagonal - 0.5) * 2 + texture + noise, 0.03, 0.88)


def _analytic_bands(ndvi: np.ndarray) -> np.ndarray:
    """Derive plausible green/red/nir/swir reflectance DN from a target NDVI field."""
    red = 0.02 + 0.18 * (1.0 - ndvi)  # bare/built ~0.2 -> dense veg ~0.02
    nir = np.clip(red * (1.0 + ndvi) / np.clip(1.0 - ndvi, 1e-3, None), 0.01, 0.55)
    green = red * 0.9 + 0.03
    swir = 0.12 + 0.18 * (1.0 - ndvi)  # drier/brighter SWIR where less vegetation
    bands = np.stack([green, red, nir, swir])  # order MUST match eo:bands BAND2/3/4/5
    dn = np.clip(np.round(bands / SCALE), 1, 10000).astype("uint16")
    return dn


def _write_cog(path: str, data: np.ndarray, transform, crs, *, dtype: str, nodata=None) -> None:
    count = data.shape[0] if data.ndim == 3 else 1
    height, width = data.shape[-2:]
    profile = {
        "driver": "COG",
        "dtype": dtype,
        "count": count,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "blocksize": 256,
        "overview_resampling": "nearest",
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        if data.ndim == 3:
            dst.write(data)
        else:
            dst.write(data, 1)


def main() -> None:
    width, height, transform, crs = _grid()
    print(f"grid: {width}x{height} @ EPSG:{DST_EPSG}")

    ndvi = _ndvi_field(height, width)
    analytic = _analytic_bands(ndvi)
    mask = np.ones((height, width), dtype="uint8")  # 1 = valid everywhere

    client = _s3_client()
    try:
        client.head_bucket(Bucket=BUCKET)
    except Exception:  # noqa: BLE001
        client.create_bucket(Bucket=BUCKET)

    with tempfile.TemporaryDirectory() as tmp:
        apath, mpath = f"{tmp}/analytic.tif", f"{tmp}/mask.tif"
        _write_cog(apath, analytic, transform, crs, dtype="uint16")
        _write_cog(mpath, mask, transform, crs, dtype="uint8", nodata=0)
        for path, key in ((apath, ANALYTIC_KEY), (mpath, MASK_KEY)):
            size = os.path.getsize(path)
            client.upload_file(
                path, BUCKET, key,
                ExtraArgs={"Metadata": {"akasha-asset": "synthetic-demo"}},
            )
            print(f"uploaded {key} ({size:,} bytes)")

    print(f"NDVI demo range: {ndvi.min():.3f}..{ndvi.max():.3f} (mean {ndvi.mean():.3f})")
    print("done.")


if __name__ == "__main__":
    main()
