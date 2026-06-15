"""Deterministic Sentinel-2 scene identity + idempotency key (Slice 1).

Pure stdlib; no third-party deps so it can be imported by validators and the
lightweight `worker.py info/scene-key` commands.

Idempotency key (data-ingestion-and-satellite-rules.md):
    {satellite}:{product_level}:{mgrs_tile}:{acquisition_datetime}:{processing_baseline}
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

_PRODUCT_RE = re.compile(
    r"(?P<platform>S2[A-B])_MSI(?P<level>L\d[A-Z])_(?P<dt>\d{8}T\d{6})_"
    r"N(?P<baseline>\d{4})_R\d{3}_T(?P<tile>[0-9A-Z]{5})_",
    re.IGNORECASE,
)
_S1_PRODUCT_RE = re.compile(
    r"(?P<platform>S1[A-C])_(?P<mode>[A-Z0-9]+)_(?P<family>GRD[HFM])_"
    r"(?P<class>\d[A-Z]{2,3})_(?P<dt>\d{8}T\d{6})_",
    re.IGNORECASE,
)
_UNSAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z]+")
_RESOURCESAT_LISS3_SOURCE_ID = "resourcesat-2a-liss3-boa"
_RESOURCESAT_LISS3_BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS3_BOA"
_RESOURCESAT_AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
_RESOURCESAT_AWIFS_BHOONIDHI_COLLECTION = "ResourceSat-2A_AWIFS_BOA"
_RESOURCESAT_BOA_COLLECTION_ALIASES = {
    _RESOURCESAT_LISS3_SOURCE_ID: _RESOURCESAT_LISS3_SOURCE_ID,
    _RESOURCESAT_LISS3_BHOONIDHI_COLLECTION: _RESOURCESAT_LISS3_SOURCE_ID,
    _RESOURCESAT_AWIFS_SOURCE_ID: _RESOURCESAT_AWIFS_SOURCE_ID,
    _RESOURCESAT_AWIFS_BHOONIDHI_COLLECTION: _RESOURCESAT_AWIFS_SOURCE_ID,
}
_RESOURCESAT_BOA_SOURCE_IDS = set(_RESOURCESAT_BOA_COLLECTION_ALIASES.values())


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


def _s1_product_match(manifest: dict[str, Any]) -> re.Match[str] | None:
    for value in _manifest_text_sources(manifest):
        match = _S1_PRODUCT_RE.search(value)
        if match:
            return match
    return None


def _source_id_from_manifest(manifest: dict[str, Any]) -> str:
    source_id = _first_value(manifest, "source_id", "sourceId", "collection_id", "collection")
    if source_id:
        source_text = str(source_id)
        if source_text in _RESOURCESAT_BOA_COLLECTION_ALIASES:
            return _RESOURCESAT_BOA_COLLECTION_ALIASES[source_text]
        return source_text
    if _s1_product_match(manifest):
        return "sentinel-1-grd"
    return "sentinel-2-l2a"


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


def _safe_path_component(value: str, default: str = "unknown") -> str:
    cleaned = _UNSAFE_COMPONENT_RE.sub("-", str(value).strip()).strip("-")
    return cleaned or default


def _platform_name(value: str | None) -> str | None:
    if not value:
        return None
    code = value.lower()
    if code in {"s1a", "sentinel-1a"}:
        return "sentinel-1a"
    if code in {"s1b", "sentinel-1b"}:
        return "sentinel-1b"
    if code in {"s1c", "sentinel-1c"}:
        return "sentinel-1c"
    if code in {"s2a", "sentinel-2a"}:
        return "sentinel-2a"
    if code in {"s2b", "sentinel-2b"}:
        return "sentinel-2b"
    return value


@dataclass(frozen=True)
class SceneIdentity:
    satellite: str
    product_level: str
    mgrs_tile: str
    acquisition_datetime: str  # ISO 8601 UTC, e.g. "2026-01-15T05:20:00Z"
    processing_baseline: str  # e.g. "05.00"
    legacy_object_layout: bool = False
    platform: str | None = None
    instrument_mode: str | None = None
    product_type: str | None = None
    relative_orbit: str | int | None = None
    orbit_state: str | None = None
    product_id: str | None = None
    path: str | int | None = None
    row: str | int | None = None
    composite: bool = False
    aoi_id: str | None = None

    @classmethod
    def from_prepare_manifest(cls, manifest: dict[str, Any]) -> SceneIdentity:
        """Build a dynamic scene identity from a COG prepare manifest."""
        source_id = _source_id_from_manifest(manifest)
        if source_id == "sentinel-1-grd":
            return cls._sentinel1_from_prepare_manifest(manifest)
        if source_id in _RESOURCESAT_BOA_SOURCE_IDS:
            return cls._resourcesat_boa_from_prepare_manifest(manifest, source_id=source_id)
        return cls._sentinel2_from_prepare_manifest(manifest)

    @classmethod
    def _sentinel2_from_prepare_manifest(cls, manifest: dict[str, Any]) -> SceneIdentity:
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

        platform = _platform_name(match.group("platform")) if match else None

        return cls(
            satellite="sentinel-2-l2a",
            product_level=product_level,
            mgrs_tile=mgrs_tile,
            acquisition_datetime=_normalise_datetime(str(acquisition_datetime)),
            processing_baseline=_format_baseline(str(baseline)),
            platform=platform or _platform_name(_first_value(manifest, "platform")),
        )

    @classmethod
    def _sentinel1_from_prepare_manifest(cls, manifest: dict[str, Any]) -> SceneIdentity:
        match = _s1_product_match(manifest)
        product_id = _first_value(manifest, "product_id", "productId", "source_product_id", "id")
        if not product_id and match:
            product_id = match.group(0).rstrip("_")
        product_id = str(product_id or "sentinel-1-grd")

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
            raise ValueError("Sentinel-1 prepare manifest is missing acquisition datetime")

        platform = _platform_name(_first_value(manifest, "platform"))
        if not platform and match:
            platform = _platform_name(match.group("platform"))

        instrument_mode = _first_value(
            manifest,
            "sar:instrument_mode",
            "instrument_mode",
            "instrumentMode",
        )
        if not instrument_mode and match:
            instrument_mode = match.group("mode").upper()

        product_type = _first_value(
            manifest,
            "product:type",
            "product_type",
            "productType",
            "sar:product_type",
        )
        if not product_type and match:
            product_class = match.group("class").upper()
            product_type = (
                f"{match.group('mode').upper()}_"
                f"{match.group('family').upper()}_{product_class[:2]}"
            )

        return cls(
            satellite="sentinel-1-grd",
            product_level="GRD",
            mgrs_tile="",
            acquisition_datetime=_normalise_datetime(str(acquisition_datetime)),
            processing_baseline="",
            platform=platform,
            instrument_mode=str(instrument_mode or "unknown").upper(),
            product_type=str(product_type or "unknown"),
            relative_orbit=_first_value(
                manifest,
                "sat:relative_orbit",
                "relative_orbit",
                "relativeOrbit",
            ),
            orbit_state=_first_value(
                manifest,
                "sat:orbit_state",
                "orbit_state",
                "orbitState",
                "orbit_direction",
                "orbitDirection",
            ),
            product_id=product_id,
        )

    @classmethod
    def _resourcesat_boa_from_prepare_manifest(
        cls, manifest: dict[str, Any], *, source_id: str
    ) -> SceneIdentity:
        props = manifest.get("properties") if isinstance(manifest.get("properties"), dict) else {}
        is_composite = bool(
            manifest.get("composite")
            or manifest.get("akasha:composite")
            or props.get("akasha:composite")
        )
        product_id = _first_value(manifest, "product_id", "productId", "source_product_id", "id")
        product_id = str(product_id or source_id)

        acquisition_datetime = _first_value(
            manifest,
            "acquisition_datetime",
            "acquisitionDateTime",
            "datetime",
            "sensing_time",
            "composite_date",
            "compositeDate",
            "anchor_date",
            "anchorDate",
        )
        if not acquisition_datetime:
            acquisition_date = _first_value(manifest, "acquisition_date", "acquisitionDate")
            if acquisition_date:
                acquisition_datetime = f"{acquisition_date}T00:00:00Z"
        if not acquisition_datetime:
            raise ValueError("ResourceSat BOA prepare manifest is missing acquisition datetime")

        if is_composite:
            aoi_id = _first_value(manifest, "aoi_id", "aoiId", "akasha:aoi_id") or props.get(
                "akasha:aoi_id"
            )
            if not aoi_id:
                raise ValueError("ResourceSat BOA composite manifest is missing AOI id")
            acquisition_datetime = _normalise_datetime(str(acquisition_datetime))
            return cls(
                satellite=source_id,
                product_level=str(
                    _first_value(manifest, "product_level", "productLevel") or "BOA-COMPOSITE"
                ),
                mgrs_tile="",
                acquisition_datetime=acquisition_datetime,
                processing_baseline="",
                platform=str(_first_value(manifest, "platform") or "resourcesat-2a"),
                product_type=str(_first_value(manifest, "product:type", "product_type") or "BOA"),
                product_id=product_id,
                composite=True,
                aoi_id=_safe_path_component(str(aoi_id)),
            )

        path = _first_value(manifest, "path", "path_id", "pathId")
        if path in (None, ""):
            path = _nested(manifest, "pathRow", "path") or _nested(manifest, "path_row", "path")
        row = _first_value(manifest, "row", "row_id", "rowId")
        if row in (None, ""):
            row = _nested(manifest, "pathRow", "row") or _nested(manifest, "path_row", "row")
        if path in (None, ""):
            raise ValueError("ResourceSat BOA prepare manifest is missing path")
        if row in (None, ""):
            raise ValueError("ResourceSat BOA prepare manifest is missing row")

        return cls(
            satellite=source_id,
            product_level=str(_first_value(manifest, "product_level", "productLevel") or "BOA"),
            mgrs_tile="",
            acquisition_datetime=_normalise_datetime(str(acquisition_datetime)),
            processing_baseline="",
            platform=str(_first_value(manifest, "platform") or "resourcesat-2a"),
            product_type=str(_first_value(manifest, "product:type", "product_type") or "BOA"),
            product_id=product_id,
            path=path,
            row=row,
        )

    @property
    def acquisition_date(self) -> str:
        return self.acquisition_datetime[:10]

    @property
    def source_id(self) -> str:
        return self.satellite

    @property
    def relative_orbit_or_unknown(self) -> str:
        if self.relative_orbit in (None, ""):
            return "unknown"
        return _safe_path_component(str(self.relative_orbit), "unknown")

    @property
    def orbit_state_or_unknown(self) -> str:
        if self.orbit_state in (None, ""):
            return "unknown"
        return _safe_path_component(str(self.orbit_state).lower(), "unknown")

    @property
    def path_or_unknown(self) -> str:
        if self.path in (None, ""):
            return "unknown"
        return _safe_path_component(str(self.path), "unknown")

    @property
    def row_or_unknown(self) -> str:
        if self.row in (None, ""):
            return "unknown"
        return _safe_path_component(str(self.row), "unknown")

    @property
    def product_id_hash(self) -> str:
        value = self.product_id or (
            f"{self.source_id}:{self.acquisition_datetime}:"
            f"{self.product_level}:{self.mgrs_tile}:{self.processing_baseline}"
        )
        return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]

    @property
    def scene_key(self) -> str:
        """Deterministic idempotency key. Re-ingesting the same scene must not
        create duplicate STAC items or overwrite validated assets."""
        if self.source_id == "sentinel-1-grd":
            platform = self.platform or "unknown"
            instrument_mode = self.instrument_mode or "unknown"
            return (
                f"{self.source_id}:{platform}:{instrument_mode}:"
                f"{self.product_type or 'unknown'}:{self.relative_orbit_or_unknown}:"
                f"{self.orbit_state_or_unknown}:{self.acquisition_datetime}:{self.product_id_hash}"
            )
        if self.source_id in _RESOURCESAT_BOA_SOURCE_IDS:
            if self.composite:
                return (
                    f"{self.source_id}:composite:{self.aoi_id or 'unknown'}:"
                    f"{self.acquisition_datetime}"
                )
            return (
                f"{self.source_id}:{self.product_level}:{self.path_or_unknown}:"
                f"{self.row_or_unknown}:{self.acquisition_datetime}"
            )
        return (
            f"{self.satellite}:{self.product_level}:{self.mgrs_tile}:"
            f"{self.acquisition_datetime}:{self.processing_baseline}"
        )

    @property
    def item_id(self) -> str:
        if self.source_id == "sentinel-1-grd":
            return f"{self.source_id}_{self.relative_orbit_or_unknown}_{self.scene_component}"
        if self.source_id in _RESOURCESAT_BOA_SOURCE_IDS:
            if self.composite:
                return (
                    f"{self.source_id}_composite_"
                    f"{self.aoi_id or 'unknown'}_{self.acquisition_date}"
                )
            return f"{self.source_id}_{self.scene_component}"
        if self.legacy_object_layout:
            date_compact = self.acquisition_date.replace("-", "")
            baseline_compact = _safe_component(self.processing_baseline)
            return f"{self.satellite}_{self.mgrs_tile}_{date_compact}_{baseline_compact}"
        return f"{self.satellite}_{self.mgrs_tile}_{self.scene_component}"

    @property
    def scene_component(self) -> str:
        """Filesystem/S3-safe component that distinguishes scenes for one date/tile."""
        if self.source_id == "sentinel-1-grd":
            datetime_compact = _safe_component(self.acquisition_datetime)
            platform = _safe_path_component(self.platform or "unknown")
            instrument = _safe_path_component(self.instrument_mode or "unknown")
            product = _safe_path_component(self.product_type or "unknown")
            return f"{datetime_compact}_{platform}_{instrument}_{product}_{self.product_id_hash}"
        if self.source_id in _RESOURCESAT_BOA_SOURCE_IDS:
            if self.composite:
                date_compact = _safe_component(self.acquisition_datetime)
                return f"composite_{self.aoi_id or 'unknown'}_{date_compact}"
            datetime_compact = _safe_component(self.acquisition_datetime)
            return (
                f"{datetime_compact}_path-{self.path_or_unknown}_"
                f"row-{self.row_or_unknown}_{self.product_id_hash}"
            )
        datetime_compact = _safe_component(self.acquisition_datetime)
        baseline_compact = _safe_component(self.processing_baseline)
        return f"{datetime_compact}_{baseline_compact}"

    @property
    def _dynamic_key_prefix(self) -> str:
        if self.source_id == "sentinel-1-grd":
            return (
                f"{self.source_id}/{self.acquisition_date}/"
                f"{self.relative_orbit_or_unknown}/{self.scene_component}"
            )
        if self.source_id in _RESOURCESAT_BOA_SOURCE_IDS:
            if self.composite:
                return (
                    f"{self.source_id}/composite/"
                    f"{self.aoi_id or 'unknown'}/{self.acquisition_date}"
                )
            return f"{self.source_id}/scene/{self.acquisition_date}/{self.scene_component}"
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

    @property
    def mask_key(self) -> str:
        return f"{self._key_prefix}/mask.tif"

    @property
    def backscatter_key(self) -> str:
        return f"{self._key_prefix}/backscatter.tif"


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
