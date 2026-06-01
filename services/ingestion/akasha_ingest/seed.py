"""Seed orchestration (Slice 1): idempotent catalog + storage seeding."""
from __future__ import annotations

from . import catalog, config, storage
from .scene import SAMPLE_SCENE


def seed_stac(method: str = "upsert", collection_id: str | None = None) -> list[str]:
    out = [
        catalog.load_collection(method=method, collection_id=collection_id),
        catalog.load_items(method=method, collection_id=collection_id),
    ]
    return out


def seed_minio(force: bool = False) -> list[str]:
    out = [storage.ensure_bucket()]
    out.extend(storage.seed_keys(SAMPLE_SCENE, force=force))
    return out


def seed_all(
    method: str = "upsert",
    force: bool = False,
    collection_id: str | None = None,
) -> list[str]:
    """Full idempotent seed: pgSTAC migrate -> load collection/item -> MinIO.

    Assumes the app schema (api `python -m app.cli migrate`) has already created
    the PostGIS extension. Safe to run repeatedly.
    """
    out = [catalog.migrate_catalog()]
    out.extend(seed_stac(method=method, collection_id=collection_id))
    if (collection_id or config.COLLECTION_ID) == config.SENTINEL2_COLLECTION_ID:
        out.extend(seed_minio(force=force))
    return out
