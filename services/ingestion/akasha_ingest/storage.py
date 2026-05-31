"""MinIO / S3-compatible object-storage operations (Slice 1).

Creates the deterministic COG bucket/key layout. Per the data-ingestion rules,
real rasters are operator-provided and NOT committed; when a local raster is
absent we create an empty placeholder object at the deterministic key so the
layout is established and listable (Slice 2 replaces these with real COGs).

boto3 is imported lazily so this module imports cleanly without it installed.
"""
from __future__ import annotations

from typing import List, Tuple

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


def seed_keys(scene: SceneIdentity = SAMPLE_SCENE, force: bool = False) -> List[str]:
    """Upload operator rasters if present, else create empty key placeholders."""
    client = _client()
    results: List[str] = []
    raster_dir = config.raster_source_dir(scene.acquisition_date)
    for asset, key in (("analytic.tif", scene.analytic_key), ("scl.tif", scene.scl_key)):
        if _object_exists(client, key) and not force:
            results.append(f"skip (exists): {key}")
            continue
        local = raster_dir / asset
        if local.is_file():
            client.upload_file(str(local), config.BUCKET, key)
            results.append(f"uploaded raster: {key} <- {local}")
        else:
            client.put_object(
                Bucket=config.BUCKET,
                Key=key,
                Body=PLACEHOLDER_BYTES,
                Metadata=PLACEHOLDER_META,
            )
            results.append(f"placeholder created (operator COG pending): {key}")
    return results


def bucket_reachable() -> Tuple[bool, str]:
    """Exit-criterion check: bucket reachable + list keys."""
    try:
        client = _client()
        client.head_bucket(Bucket=config.BUCKET)
        resp = client.list_objects_v2(Bucket=config.BUCKET, Prefix=f"{config.COLLECTION_ID}/")
        keys = [obj["Key"] for obj in resp.get("Contents", [])]
        return True, f"bucket '{config.BUCKET}' reachable; {len(keys)} key(s) under {config.COLLECTION_ID}/"
    except Exception as exc:  # noqa: BLE001
        return False, f"bucket unreachable: {exc}"
