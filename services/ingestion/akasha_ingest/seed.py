"""Seed orchestration (Slice 1): idempotent catalog + storage seeding."""
from __future__ import annotations

from . import catalog, storage
from .scene import SAMPLE_SCENE


def seed_stac(method: str = "upsert") -> list[str]:
    out = [catalog.load_collection(method=method), catalog.load_items(method=method)]
    return out


def seed_minio(force: bool = False) -> list[str]:
    out = [storage.ensure_bucket()]
    out.extend(storage.seed_keys(SAMPLE_SCENE, force=force))
    return out


def seed_all(method: str = "upsert", force: bool = False) -> list[str]:
    """Full idempotent seed: pgSTAC migrate -> load collection/item -> MinIO.

    Assumes the app schema (api `python -m app.cli migrate`) has already created
    the PostGIS extension. Safe to run repeatedly.
    """
    out = [catalog.migrate_catalog()]
    out.extend(seed_stac(method=method))
    out.extend(seed_minio(force=force))
    return out
