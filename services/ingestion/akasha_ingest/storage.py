"""MinIO / S3-compatible object-storage operations (Slice 1).

Creates the deterministic COG bucket/key layout. Per the data-ingestion rules,
real rasters are operator-provided and NOT committed; when a local raster is
absent we create an empty placeholder object at the deterministic key so the
layout is established and listable (Slice 2 replaces these with real COGs).

boto3 is imported lazily so this module imports cleanly without it installed.
"""
from __future__ import annotations

from collections.abc import Sequence

from . import config
from .scene import SAMPLE_SCENE, SceneIdentity

PLACEHOLDER_BYTES = b""  # empty placeholder object
PLACEHOLDER_META = {"akasha-placeholder": "true"}


def _client():
    import boto3  # lazy
    from botocore.config import Config as BotoConfig  # lazy

    return boto3.client(
        "s3",
        endpoint_url=config.S3_ENDPOINT_URL,
        aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY,
        region_name=config.S3_REGION,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> str:
    from botocore.exceptions import ClientError  # lazy

    client = _client()
    try:
        client.head_bucket(Bucket=config.BUCKET)
        return f"bucket exists: {config.BUCKET}"
    except ClientError:
        client.create_bucket(Bucket=config.BUCKET)
        return f"bucket created: {config.BUCKET}"


def _object_exists(client, key: str) -> bool:
    from botocore.exceptions import ClientError  # lazy

    try:
        client.head_object(Bucket=config.BUCKET, Key=key)
        return True
    except ClientError:
        return False


def object_status(client, key: str) -> dict:
    """Return {exists, size, placeholder} for one object (head_object)."""
    from botocore.exceptions import ClientError  # lazy

    try:
        head = client.head_object(Bucket=config.BUCKET, Key=key)
    except ClientError:
        return {"key": key, "exists": False, "size": 0, "placeholder": None}
    size = int(head.get("ContentLength", 0))
    meta = head.get("Metadata", {}) or {}
    placeholder = meta.get("akasha-placeholder") == "true" or size == 0
    return {"key": key, "exists": True, "size": size, "placeholder": placeholder}


def _strip_scheme(url: str) -> str:
    return url.split("://", 1)[-1] if "://" in url else url


def _gdal_s3_options() -> dict[str, str]:
    endpoint = _strip_scheme(config.S3_ENDPOINT_URL)
    opts = {
        "AWS_ACCESS_KEY_ID": config.S3_ACCESS_KEY,
        "AWS_SECRET_ACCESS_KEY": config.S3_SECRET_KEY,
        "AWS_REGION": config.S3_REGION,
        "AWS_VIRTUAL_HOSTING": "FALSE",
        "AWS_HTTPS": "NO",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    }
    if endpoint:
        opts["AWS_S3_ENDPOINT"] = endpoint
    return {key: value for key, value in opts.items() if value}


def _verify_cog_metadata(scene: SceneIdentity) -> tuple[bool, str]:
    """Open analytic+SCL via rasterio and verify basic COG/grid contracts."""
    try:
        import rasterio  # lazy

        analytic_path = f"/vsis3/{config.BUCKET}/{scene.analytic_key}"
        scl_path = f"/vsis3/{config.BUCKET}/{scene.scl_key}"
        with rasterio.Env(**_gdal_s3_options()):
            with rasterio.open(analytic_path) as analytic, rasterio.open(scl_path) as scl:
                problems: list[str] = []
                if analytic.count != 9:
                    problems.append(f"analytic band count {analytic.count} != 9")
                if scl.count != 1:
                    problems.append(f"SCL band count {scl.count} != 1")
                if analytic.crs != scl.crs:
                    problems.append(f"CRS mismatch analytic={analytic.crs} scl={scl.crs}")
                if analytic.transform != scl.transform:
                    problems.append("transform mismatch")
                if (analytic.width, analytic.height) != (scl.width, scl.height):
                    problems.append(
                        "shape mismatch "
                        f"analytic={analytic.width}x{analytic.height} "
                        f"scl={scl.width}x{scl.height}"
                    )
                if not analytic.overviews(1):
                    problems.append("analytic COG has no band-1 overviews")
                if not scl.overviews(1):
                    problems.append("SCL COG has no band-1 overviews")
                if problems:
                    return False, "; ".join(problems)
                return (
                    True,
                    "rasterio metadata OK: analytic=9 bands, SCL=1 band, "
                    "aligned grid, overviews present",
                )
    except Exception as exc:  # noqa: BLE001
        return False, f"rasterio COG metadata check failed: {exc}"


def seed_keys(scene: SceneIdentity = SAMPLE_SCENE, force: bool = False) -> list[str]:
    """Upload operator rasters if present, else create empty key placeholders.

    Real COG uploads are tagged with metadata so Phase 2 verification can
    distinguish them from Slice 1 empty placeholders (ContentLength > 0 and no
    `akasha-placeholder` marker).
    """
    client = _client()
    results: list[str] = []
    raster_dir = config.raster_source_dir(scene.acquisition_date)
    for asset, key in (("analytic.tif", scene.analytic_key), ("scl.tif", scene.scl_key)):
        if _object_exists(client, key) and not force:
            results.append(f"skip (exists): {key}")
            continue
        local = raster_dir / asset
        if local.is_file():
            size = local.stat().st_size
            client.upload_file(
                str(local),
                config.BUCKET,
                key,
                ExtraArgs={
                    "Metadata": {
                        "akasha-asset": asset.split(".")[0],
                        "akasha-scene-key": scene.scene_key,
                        "akasha-placeholder": "false",
                    }
                },
            )
            results.append(f"uploaded real COG: {key} <- {local} ({size:,} bytes)")
        else:
            client.put_object(
                Bucket=config.BUCKET,
                Key=key,
                Body=PLACEHOLDER_BYTES,
                Metadata=PLACEHOLDER_META,
            )
            results.append(f"placeholder created (operator COG pending): {key}")
    return results


def verify_real_cogs(scene: SceneIdentity = SAMPLE_SCENE) -> tuple[bool, str]:
    """Phase 2 check: deterministic COG objects exist AND are non-empty real COGs.

    Fails if either object is missing, empty (ContentLength == 0), or still
    marked as a Slice 1 placeholder.
    """
    try:
        client = _client()
        client.head_bucket(Bucket=config.BUCKET)
        problems: list[str] = []
        sizes: list[str] = []
        for key in (scene.analytic_key, scene.scl_key):
            st = object_status(client, key)
            if not st["exists"]:
                problems.append(f"missing: {key}")
            elif st["placeholder"]:
                problems.append(f"placeholder/empty (ContentLength={st['size']}): {key}")
            else:
                sizes.append(f"{key}={st['size']:,}B")
        if problems:
            return False, "real COG check failed -> " + "; ".join(problems)
        meta_ok, meta_detail = _verify_cog_metadata(scene)
        if not meta_ok:
            return False, "real COG metadata check failed -> " + meta_detail
        return True, "real COGs present (non-empty + valid metadata): " + ", ".join(sizes)
    except Exception as exc:  # noqa: BLE001
        return False, f"real COG check error: {exc}"


def bucket_reachable(required_keys: Sequence[str] | None = None) -> tuple[bool, str]:
    """Exit-criterion check: bucket reachable + deterministic keys present.

    Empty placeholder objects are acceptable in Slice 1, but the expected keys
    must exist so Slice 2 can replace them with validated COGs deterministically.
    """
    try:
        client = _client()
        client.head_bucket(Bucket=config.BUCKET)
        resp = client.list_objects_v2(Bucket=config.BUCKET, Prefix=f"{config.COLLECTION_ID}/")
        keys = [obj["Key"] for obj in resp.get("Contents", [])]
        expected = list(required_keys or [SAMPLE_SCENE.analytic_key, SAMPLE_SCENE.scl_key])
        missing = [key for key in expected if key not in keys]
        if missing:
            return (
                False,
                f"bucket '{config.BUCKET}' reachable but missing expected key(s): {missing}",
            )
        return (
            True,
            f"bucket '{config.BUCKET}' reachable; expected keys present; "
            f"{len(keys)} key(s) under {config.COLLECTION_ID}/",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"bucket unreachable: {exc}"
