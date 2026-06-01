"""Deterministic Sentinel-2 scene identity + idempotency key (Slice 1).

Pure stdlib; no third-party deps so it can be imported by validators and the
lightweight `worker.py info/scene-key` commands.

Idempotency key (data-ingestion-and-satellite-rules.md):
    {satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_PRODUCT_RE = re.compile(
    r"(?P<platform>S2[A-B])_MSI(?P<level>L\d[A-Z])_(?P<dt>\d{8}T\d{6})_"
    r"N(?P<baseline>\d{4})_R\d{3}_T(?P<tile>[0-9A-Z]{5})_",
    re.IGNORECASE,
)
_UNSAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z]+")


def _nested(manifest: dict[str, Any], *keys: str) -> Any:
    cur: Any = manifest
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _first_value(manifest: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in manifest and manifest[key] not in (None, ""):
            return manifest[key]
    props = manifest.get("properties") if isinstance(manifest.get("properties"), dict) else {}
    for key in keys:
        if key in props and props[key] not in (None, ""):
            return props[key]
    product = manifest.get("product") if isinstance(manifest.get("product"), dict) else {}
    for key in keys:
        if key in product and product[key] not in (None, ""):
            return product[key]
    return None


def _manifest_text_sources(manifest: dict[str, Any]) -> list[str]:
    values = [
        _first_value(manifest, "product_id", "productId", "source_product_id", "id"),
        manifest.get("source_zip"),
        manifest.get("safe_dir"),
        _nested(manifest, "paths", "source_zip"),
        _nested(manifest, "paths", "safe_dir"),
    ]
    return [str(value) for value in values if value]


def _product_match(manifest: dict[str, Any]) -> re.Match[str] | None:
    for value in _manifest_text_sources(manifest):
        match = _PRODUCT_RE.search(value)
        if match:
            return match
    return None


def _normalise_datetime(value: str) -> str:
    if value.endswith("Z"):
        return value
    if value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value + "Z" if "T" in value else f"{value}T00:00:00Z"


def _datetime_from_product(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}T{value[9:11]}:{value[11:13]}:{value[13:15]}Z"


def _format_baseline(value: str) -> str:
    value = value.strip()
    if value.startswith("N"):
        value = value[1:]
    if "." in value:
        return value
    if len(value) == 4 and value.isdigit():
        return f"{value[:2]}.{value[2:]}"
    return value


def _safe_component(value: str) -> str:
    return _UNSAFE_COMPONENT_RE.sub("", value)


@dataclass(frozen=True)
class SceneIdentity:
    satellite: str
    product_level: str
    mgrs_tile: str
    acquisition_datetime: str  # ISO 8601 UTC, e.g. "2026-01-15T05:20:00Z"
    processing_baseline: str  # e.g. "05.00"
    legacy_object_layout: bool = False

    @classmethod
    def from_prepare_manifest(cls, manifest: dict[str, Any]) -> SceneIdentity:
        """Build a dynamic scene identity from a COG prepare manifest."""
        match = _product_match(manifest)
        mgrs_tile = _first_value(manifest, "mgrs_tile", "mgrsTile", "s2:mgrs_tile")
        if not mgrs_tile and match:
            mgrs_tile = match.group("tile")
        if not mgrs_tile:
            raise ValueError("prepare manifest is missing MGRS tile")
        mgrs_tile = str(mgrs_tile).removeprefix("T")

        acquisition_datetime = _first_value(
            manifest,
            "acquisition_datetime",
            "acquisitionDateTime",
            "datetime",
            "sensing_time",
        )
        if not acquisition_datetime and match:
            acquisition_datetime = _datetime_from_product(match.group("dt"))
        if not acquisition_datetime:
            acquisition_date = _first_value(manifest, "acquisition_date", "acquisitionDate")
            if acquisition_date:
                acquisition_datetime = f"{acquisition_date}T00:00:00Z"
        if not acquisition_datetime:
            raise ValueError("prepare manifest is missing acquisition datetime")

        baseline = _first_value(
            manifest,
            "processing_baseline",
            "processingBaseline",
            "s2:processing_baseline",
        )
        if not baseline and match:
            baseline = match.group("baseline")
        if not baseline:
            raise ValueError("prepare manifest is missing processing baseline")

        level = _first_value(manifest, "product_level", "productLevel", "s2:product_level")
        if not level and match:
            level = match.group("level")
        product_level = str(level or "L2A").replace("MSI", "")

        return cls(
            satellite="sentinel-2-l2a",
            product_level=product_level,
            mgrs_tile=mgrs_tile,
            acquisition_datetime=_normalise_datetime(str(acquisition_datetime)),
            processing_baseline=_format_baseline(str(baseline)),
        )

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
        if self.legacy_object_layout:
            date_compact = self.acquisition_date.replace("-", "")
            baseline_compact = _safe_component(self.processing_baseline)
            return f"{self.satellite}_{self.mgrs_tile}_{date_compact}_{baseline_compact}"
        return f"{self.satellite}_{self.mgrs_tile}_{self.scene_component}"

    @property
    def scene_component(self) -> str:
        """Filesystem/S3-safe component that distinguishes scenes for one date/tile."""
        datetime_compact = _safe_component(self.acquisition_datetime)
        baseline_compact = _safe_component(self.processing_baseline)
        return f"{datetime_compact}_{baseline_compact}"

    @property
    def _dynamic_key_prefix(self) -> str:
        return f"{self.satellite}/{self.acquisition_date}/{self.mgrs_tile}/{self.scene_component}"

    @property
    def _legacy_key_prefix(self) -> str:
        return f"{self.satellite}/{self.acquisition_date}"

    @property
    def _key_prefix(self) -> str:
        if self.legacy_object_layout:
            return self._legacy_key_prefix
        return self._dynamic_key_prefix

    @property
    def legacy_item_id(self) -> str:
        date_compact = self.acquisition_date.replace("-", "")
        baseline_compact = _safe_component(self.processing_baseline)
        return f"{self.satellite}_{self.mgrs_tile}_{date_compact}_{baseline_compact}"

    @property
    def analytic_key(self) -> str:
        return f"{self._key_prefix}/analytic.tif"

    @property
    def scl_key(self) -> str:
        return f"{self._key_prefix}/scl.tif"


def scene_from_prepare_manifest(manifest: dict[str, Any]) -> SceneIdentity:
    return SceneIdentity.from_prepare_manifest(manifest)


# The Wave 1 sample scene used by the seed.
#
# Slice 2 (Phase 2 raster de-risk): this now points at the REAL prepared
# Sentinel-2 L2A scene whose analytic + SCL COGs were generated by
# scripts/prepare_sentinel2_l2a_cogs.py (see
# docs/sentinel-2-l2a-cog-prep-runbook.md). Source product:
#   S2B_MSIL2A_20250914T050649_N0511_R019_T43PHP_20250914T074457.SAFE
# The large COGs themselves are operator-provided and intentionally git-ignored.
SAMPLE_SCENE = SceneIdentity(
    satellite="sentinel-2-l2a",
    product_level="L2A",
    mgrs_tile="43PHP",
    acquisition_datetime="2025-09-14T05:06:49.024000Z",
    processing_baseline="05.11",
    legacy_object_layout=True,
)
