"""Deterministic Sentinel-2 scene identity + idempotency key (Slice 1).

Pure stdlib; no third-party deps so it can be imported by validators and the
lightweight `worker.py info/scene-key` commands.

Idempotency key (data-ingestion-and-satellite-rules.md):
    {satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SceneIdentity:
    satellite: str
    product_level: str
    mgrs_tile: str
    acquisition_datetime: str  # ISO 8601 UTC, e.g. "2026-01-15T05:20:00Z"
    processing_baseline: str  # e.g. "05.00"

    @property
    def acquisition_date(self) -> str:
        return self.acquisition_datetime[:10]

    @property
    def scene_key(self) -> str:
        """Deterministic idempotency key. Re-ingesting the same scene must not
        create duplicate STAC items or overwrite validated assets."""
        return (
            f"{self.satellite}:{self.product_level}:{self.mgrs_tile}:"
            f"{self.acquisition_datetime}:{self.processing_baseline}"
        )

    @property
    def item_id(self) -> str:
        date_compact = self.acquisition_date.replace("-", "")
        baseline_compact = self.processing_baseline.replace(".", "")
        return f"{self.satellite}_{self.mgrs_tile}_{date_compact}_{baseline_compact}"

    @property
    def analytic_key(self) -> str:
        return f"{self.satellite}/{self.acquisition_date}/analytic.tif"

    @property
    def scl_key(self) -> str:
        return f"{self.satellite}/{self.acquisition_date}/scl.tif"


# The Wave 1 Bangalore sample scene used by the seed.
SAMPLE_SCENE = SceneIdentity(
    satellite="sentinel-2-l2a",
    product_level="L2A",
    mgrs_tile="43PGQ",
    acquisition_datetime="2026-01-15T05:20:00Z",
    processing_baseline="05.00",
)
