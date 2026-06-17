"""Catalog resolver: source/date/asset metadata for the BFF (Slice 2).

Resolution order:
  1. STAC API (``STAC_API_URL``) when configured.
  2. Local seed STAC JSON under ``data/seed/stac/`` for offline validation.

No heavy deps: uses stdlib ``urllib``/``json`` only.
"""

from __future__ import annotations

import json
import os
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import not_found, upstream_error
from .indices import DEFAULT_INDEX, SUPPORTED_INDICES

SENTINEL_2_SOURCE_ID = "sentinel-2-l2a"
SENTINEL_1_SOURCE_ID = "sentinel-1-grd"
RESOURCESAT_LISS3_SOURCE_ID = "resourcesat-2a-liss3-boa"
RESOURCESAT_AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
RESOURCESAT_BOA_SOURCE_IDS = {RESOURCESAT_LISS3_SOURCE_ID, RESOURCESAT_AWIFS_SOURCE_ID}
COLLECTION_ID = RESOURCESAT_LISS3_SOURCE_ID
SOURCE_LABEL = "ResourceSat-2A LISS-3 BOA"
SOURCE_PROVIDER = "ISRO/NRSC Bhoonidhi"
_LEGACY_SENTINEL_SOURCE_IDS = {SENTINEL_2_SOURCE_ID, SENTINEL_1_SOURCE_ID}

_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    SENTINEL_2_SOURCE_ID: {
        "id": SENTINEL_2_SOURCE_ID,
        "label": "Sentinel-2 L2A",
        "provider": "Copernicus",
        "kind": "optical",
        "collectionId": SENTINEL_2_SOURCE_ID,
        "expectedAssets": ["analytic", "scl"],
        "supportedIndices": SUPPORTED_INDICES,
        "bandRoleMapping": {
            "BLUE": "B02",
            "GREEN": "B03",
            "RED": "B04",
            "NIR": "B08",
            "RED_EDGE": "B05",
            "SWIR1": "B11",
            "SWIR2": "B12",
        },
        "maskAsset": "scl",
        "maskMethod": "Sentinel-2 Scene Classification Layer (SCL).",
        "excludedMaskClasses": [0, 1, 2, 3, 7, 8, 9, 10, 11],
        "nodataPolicy": "selected_band_or_mask",
        "displayModes": ["RGB", "NDVI", "NDRE", "MSAVI", "NDMI"],
        "defaultDisplayMode": "RGB",
        # EOS-style grouped LAYER picker. Each mode is a valid display mode above.
        "layerGroups": [
            {"label": "Natural Color", "modes": ["RGB"]},
            {"label": "Vegetation Indices", "modes": ["NDVI", "NDRE", "MSAVI"]},
            {"label": "Moisture Indices", "modes": ["NDMI"]},
        ],
        "description": "Optical Sentinel-2 L2A surface reflectance with cloud/SCL masking.",
        "attribution": "Copernicus Sentinel-2",
        "dateMetricsKind": "optical",
        "defaultRescale": "0,3000",
        "tileRouteMode": "rgb",
    },
    RESOURCESAT_LISS3_SOURCE_ID: {
        "id": RESOURCESAT_LISS3_SOURCE_ID,
        "label": "ResourceSat-2A LISS-3 BOA",
        "provider": "ISRO/NRSC Bhoonidhi",
        "kind": "optical",
        "collectionId": RESOURCESAT_LISS3_SOURCE_ID,
        "expectedAssets": ["analytic", "mask"],
        "supportedIndices": ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
        "bandRoleMapping": {
            "GREEN": "BAND2",
            "RED": "BAND3",
            "NIR": "BAND4",
            "SWIR1": "BAND5",
        },
        "maskAsset": "mask",
        "excludedMaskClasses": [0, 2, 3],
        "nodataPolicy": "mask_only",
        # FCC base imagery + optical indices. LISS-3 has no red-edge band, so NDRE
        # is intentionally absent (only NDVI/MSAVI vegetation + NDMI moisture).
        "displayModes": ["FCC", "NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
        "defaultDisplayMode": "FCC",
        "mapDisplayModes": ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
        "defaultMapDisplayMode": "NDVI",
        "layerGroups": [
            {"label": "Imagery", "modes": ["FCC"]},
            {"label": "Vegetation Indices", "modes": ["NDVI", "MSAVI"]},
            {"label": "Moisture Indices", "modes": ["NDMI"]},
            {"label": "Water Index", "modes": ["NDWI_GREEN_NIR"]},
        ],
        "description": (
            "ResourceSat-2A LISS-3 BOA crop analytics source with Akasha-generated "
            "provisional cloud/validity mask."
        ),
        "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
        "dateMetricsKind": "optical",
        "defaultRescale": "0,3000",
        "tileRouteMode": "fcc",
        "resolutionMeters": 24,
        "analysisLevel": "field",
        "refreshPolicy": "Daily Bhoonidhi search; BOA products lag acquisition by about 5 days.",
        "limitations": [
            "False-colour composite only; LISS-3 has no blue band.",
            "NDRE/RECI unsupported because LISS-3 has no true red-edge band.",
            "Mask is Akasha threshold-derived and provisional until a native quality layer exists.",
        ],
        "maskMethod": (
            "Akasha threshold mask v1 (no native quality layer found in validated "
            "LISS-3 BOA sample; provisional)."
        ),
        "availableMaskOptions": ["clouds", "cloudShadows"],
        "metricsProvisional": True,
    },
    SENTINEL_1_SOURCE_ID: {
        "id": SENTINEL_1_SOURCE_ID,
        "label": "Sentinel-1 GRD",
        "provider": "Copernicus",
        "kind": "sar",
        "collectionId": SENTINEL_1_SOURCE_ID,
        "expectedAssets": ["backscatter"],
        "supportedIndices": [],
        "bandRoleMapping": {},
        "displayModes": ["VV_GRAYSCALE"],
        "defaultDisplayMode": "VV_GRAYSCALE",
        "description": "Radar layer · cloud-penetrating · not true colour.",
        "attribution": "Copernicus Sentinel-1",
        "dateMetricsKind": "radar",
        "defaultRescale": "-25,5",
        "tileRouteMode": "display-mode",
    },
}

_SOURCE_REGISTRY.update(
    {
        "resourcesat-2a-awifs-boa": {
            "id": "resourcesat-2a-awifs-boa",
            "label": "ResourceSat-2A AWiFS BOA",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "optical",
            "collectionId": "ResourceSat-2A_AWIFS_BOA",
            "expectedAssets": ["analytic", "mask"],
            "supportedIndices": ["NDVI", "MSAVI", "NDMI", "NDWI_GREEN_NIR"],
            "bandRoleMapping": {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4", "SWIR1": "BAND5"},
            "maskAsset": "mask",
            "nodataPolicy": "mask_only",
            "displayModes": ["FCC"],
            "defaultDisplayMode": "FCC",
            "description": "Gated regional ResourceSat-2A AWiFS BOA context source.",
            "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "fcc",
            "resolutionMeters": 56,
            "analysisLevel": "regional",
            "refreshPolicy": "Gated until AWiFS BOA download and COG prep are validated.",
            "limitations": ["Registered for roadmap visibility; no composites are loaded yet."],
            "maskMethod": (
                "Akasha threshold mask v1 for ResourceSat-2A AWiFS BOA "
                "(pending AWiFS-specific native quality-layer validation; provisional)."
            ),
            "excludedMaskClasses": [0, 2, 3],
            "availableMaskOptions": ["clouds", "cloudShadows"],
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated AWiFS BOA composite has been ingested.",
        },
        "resourcesat-2a-liss4-mx70-l2": {
            "id": "resourcesat-2a-liss4-mx70-l2",
            "label": "ResourceSat-2A LISS-4 MX70 L2",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "optical",
            "collectionId": "ResourceSat-2A_LISS4-MX70_L2",
            "expectedAssets": ["analytic", "mask"],
            "supportedIndices": [],
            "bandRoleMapping": {"RED": "BAND3", "NIR": "BAND4"},
            "maskAsset": "mask",
            "displayModes": ["FCC"],
            "defaultDisplayMode": "FCC",
            "description": "Gated higher-resolution ResourceSat-2A LISS-4 context source.",
            "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "fcc",
            "resolutionMeters": 5.8,
            "analysisLevel": "context",
            "refreshPolicy": "Gated until access, calibration, and band metadata are validated.",
            "limitations": [
                "Context-only until downloaded LISS-4 product metadata confirms calibrated "
                "red/NIR bands and mask behavior.",
                "Potential NDVI/MSAVI support remains gated and is not enabled for field "
                "analytics.",
            ],
            "maskMethod": "Pending Akasha mask validation.",
            "excludedMaskClasses": [0, 2, 3],
            "availableMaskOptions": ["clouds", "cloudShadows"],
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated LISS-4 MX70 product has been ingested.",
        },
        "eos-06-ocm-lac-ndvi-8day-360m": {
            "id": "eos-06-ocm-lac-ndvi-8day-360m",
            "label": "EOS-06 OCM-LAC NDVI 8-day 360m",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "context",
            "collectionId": "EOS-06_OCM-LAC_NDVI_8day_360m",
            "expectedAssets": ["ndvi"],
            "supportedIndices": [],
            "bandRoleMapping": {},
            "maskAsset": None,
            "displayModes": ["NDVI_CONTEXT"],
            "defaultDisplayMode": "NDVI_CONTEXT",
            "description": "Gated coarse regional precomputed NDVI context source.",
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,1",
            "tileRouteMode": "context",
            "resolutionMeters": 360,
            "analysisLevel": "regional",
            "refreshPolicy": "Gated; context only, not field-level analytics.",
            "limitations": ["Precomputed NDVI only; not raw reflectance for plot statistics."],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated EOS-06 NDVI context COG has been ingested.",
        },
        "eos-04-sar-mrs-l2b": {
            "id": "eos-04-sar-mrs-l2b",
            "label": "EOS-04 SAR MRS L2B",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "sar",
            "collectionId": "EOS-04_SAR-MRS_L2B",
            "expectedAssets": ["backscatter"],
            "supportedIndices": [],
            "bandRoleMapping": {},
            "maskAsset": None,
            "displayModes": ["VV_GRAYSCALE"],
            "defaultDisplayMode": "VV_GRAYSCALE",
            "description": "Gated ISRO SAR context source.",
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "radar",
            "defaultRescale": "-25,5",
            "tileRouteMode": "vv_grayscale",
            "resolutionMeters": None,
            "analysisLevel": "context",
            "refreshPolicy": "Gated until SAR product structure is validated.",
            "limitations": ["Not an optical vegetation-index source."],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated EOS-04 SAR COG has been ingested.",
        },
        "nisar-ssar-beta-gcov": {
            "id": "nisar-ssar-beta-gcov",
            "label": "NISAR SSAR Beta GCOV",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "sar",
            "collectionId": "NISAR_SSAR-Beta_GCOV",
            "expectedAssets": ["backscatter"],
            "supportedIndices": [],
            "bandRoleMapping": {},
            "maskAsset": None,
            "displayModes": ["VV_GRAYSCALE"],
            "defaultDisplayMode": "VV_GRAYSCALE",
            "description": "Gated NISAR SAR context source.",
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "radar",
            "defaultRescale": "-25,5",
            "tileRouteMode": "vv_grayscale",
            "resolutionMeters": None,
            "analysisLevel": "context",
            "refreshPolicy": "Gated until NISAR product support is validated.",
            "limitations": ["Not an optical vegetation-index source."],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated NISAR COG has been ingested.",
        },
        "cartosat-3-gated": {
            "id": "cartosat-3-gated",
            "label": "Cartosat-3 (gated)",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "context",
            "collectionId": "cartosat-3-gated",
            "expectedAssets": ["visual"],
            "supportedIndices": [],
            "bandRoleMapping": {},
            "maskAsset": None,
            "displayModes": ["CONTEXT"],
            "defaultDisplayMode": "CONTEXT",
            "description": "Gated high-resolution visual/context source for manual imports.",
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "context",
            "resolutionMeters": None,
            "analysisLevel": "context",
            "refreshPolicy": (
                "Manual/order workflow only until direct API availability is confirmed."
            ),
            "limitations": [
                "Cartosat-3 is not present in the validated Bhoonidhi API catalog.",
                (
                    "No crop indices are enabled until calibrated band metadata and use rights "
                    "are confirmed."
                ),
            ],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No Bhoonidhi API collection was found for Cartosat-3.",
        },
        "irs-1c-liss3-archive": {
            "id": "irs-1c-liss3-archive",
            "label": "IRS-1C LISS-3 archive",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "archive",
            "collectionId": "irs-1c-liss3-archive",
            "expectedAssets": ["analytic", "mask"],
            "supportedIndices": [],
            "bandRoleMapping": {},
            "maskAsset": "mask",
            "displayModes": ["FCC"],
            "defaultDisplayMode": "FCC",
            "description": "Gated historical archive source.",
            "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "fcc",
            "resolutionMeters": 23.5,
            "analysisLevel": "archive",
            "refreshPolicy": "Archive only; no scheduled current-monitoring refresh.",
            "limitations": ["Calibration and metadata must be validated before analytics."],
            "maskMethod": "Pending archive mask validation.",
            "availableMaskOptions": ["clouds", "cloudShadows"],
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated IRS-1C archive product has been ingested.",
        },
    }
)


def _stac_api_url() -> str:
    return os.environ.get("STAC_API_URL", "").strip().rstrip("/")


def _seed_dir() -> Path:
    """Locate the repo data/seed directory (preview: /app/data/seed)."""
    env = os.environ.get("SEED_DATA_DIR")
    if env:
        return Path(env)
    repo_root = os.environ.get("REPO_ROOT")
    candidates: list[Path] = []
    if repo_root:
        candidates.append(Path(repo_root) / "data" / "seed")
    here = Path(__file__).resolve()
    candidates.extend(base / "data" / "seed" for base in [Path("/app"), *here.parents])
    for cand in candidates:
        if cand.is_dir():
            return cand
    return Path("/app/data/seed")


def _http_get_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read())


def get_source(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    try:
        return dict(_SOURCE_REGISTRY[source_id])
    except KeyError as exc:
        raise not_found(
            f"Unknown source '{source_id}'.", code="UNKNOWN_SOURCE", sourceId=source_id
        ) from exc


def registered_source_ids() -> list[str]:
    return list(_SOURCE_REGISTRY)


def _include_legacy_sentinel_sources() -> bool:
    return os.environ.get("AKASHA_INCLUDE_LEGACY_SENTINEL_SOURCES", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def selectable_source_ids() -> list[str]:
    """Return browser-selectable production sources.

    Phase 8a moves Sentinel out of the production selector after the ResourceSat
    composite smoke test. Direct resolver access remains for legacy tests and
    operator migration checks.
    """
    if _include_legacy_sentinel_sources():
        return registered_source_ids()
    return [
        source_id
        for source_id in registered_source_ids()
        if source_id not in _LEGACY_SENTINEL_SOURCE_IDS
    ]


def _collection_from_registry(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    return {
        "id": source["collectionId"],
        "title": source["label"],
        "description": source["description"],
        "providers": [{"name": source["provider"]}],
        "akasha:kind": source["kind"],
        "akasha:source_kind": source["kind"],
        "akasha:supported_indices": list(source["supportedIndices"]),
        "akasha:band_role_mapping": dict(source.get("bandRoleMapping", {})),
        "akasha:mask_asset": source.get("maskAsset"),
        "akasha:display_modes": list(source["displayModes"]),
        "akasha:default_display_mode": source["defaultDisplayMode"],
        "akasha:date_metrics_kind": source["dateMetricsKind"],
    }


def source_payload(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    return {
        "id": source["id"],
        "label": source["label"],
        "provider": source["provider"],
        "kind": source["kind"],
        "collectionId": source["collectionId"],
        "expectedAssets": list(source["expectedAssets"]),
        "supportedIndices": supported_indices(source_id),
        "bandRoleMapping": dict(source.get("bandRoleMapping", {})),
        "maskAsset": source.get("maskAsset"),
        "displayModes": list(source["displayModes"]),
        "defaultDisplayMode": source["defaultDisplayMode"],
        "mapDisplayModes": list(source.get("mapDisplayModes", source["displayModes"])),
        "defaultMapDisplayMode": source.get("defaultMapDisplayMode", source["defaultDisplayMode"]),
        # EOS-style grouped LAYER picker; None for sources without categories
        # (frontend then falls back to a flat displayModes list).
        "layerGroups": source.get("layerGroups"),
        "description": source["description"],
        "attribution": source["attribution"],
        "dateMetricsKind": source["dateMetricsKind"],
        "defaultRescale": source["defaultRescale"],
        "tileRouteMode": source["tileRouteMode"],
        "resolutionMeters": source.get("resolutionMeters"),
        "analysisLevel": source.get("analysisLevel"),
        "refreshPolicy": source.get("refreshPolicy"),
        "limitations": list(source.get("limitations", [])),
        "maskMethod": source.get("maskMethod"),
        "availableMaskOptions": list(
            source.get("availableMaskOptions", ["clouds", "cloudShadows", "cirrus"])
            if source.get("kind") == "optical" and source.get("maskAsset")
            else []
        ),
        "displayRescale": source.get("defaultRescale"),
        "availabilityStatus": source.get("availabilityStatus", "active"),
        "gatedReason": source.get("gatedReason"),
        "metricsProvisional": bool(source.get("metricsProvisional", False)),
    }


def list_sources() -> list[dict[str, Any]]:
    return [source_payload(source_id) for source_id in selectable_source_ids()]


def default_display_mode(source_id: str = COLLECTION_ID) -> str:
    return str(get_source(source_id)["defaultDisplayMode"])


def display_modes(source_id: str = COLLECTION_ID) -> list[str]:
    return list(get_source(source_id)["displayModes"])


def attribution(source_id: str = COLLECTION_ID) -> str:
    return str(get_source(source_id)["attribution"])


def tile_url_template(source_id: str, acquisition_date: str) -> str:
    source = get_source(source_id)
    display_mode = source["defaultDisplayMode"]
    if source["tileRouteMode"] == "rgb":
        return f"/api/tiles/{source_id}/{acquisition_date}/rgb/{{z}}/{{x}}/{{y}}.png"
    return f"/api/tiles/{source_id}/{acquisition_date}/{display_mode}/{{z}}/{{x}}/{{y}}.png"


@lru_cache(maxsize=8)
def _seed_collection(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    path = _seed_dir() / "stac" / f"{source_id}-collection.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=8)
def _seed_items(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    stac_dir = _seed_dir() / "stac"
    items: list[dict[str, Any]] = []
    sample_path = stac_dir / f"{source_id}-sample-item.json"
    if sample_path.is_file():
        items.append(json.loads(sample_path.read_text()))
    for item_dir in (stac_dir / "items" / source_id, stac_dir / source_id / "items"):
        if not item_dir.is_dir():
            continue
        for path in sorted(item_dir.glob("*.json")):
            items.append(json.loads(path.read_text()))
    return [item for item in items if item.get("collection") == source_id]


def get_collection(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    """Return the STAC collection document (STAC API first, then seed/registry)."""
    get_source(source_id)
    base = _stac_api_url()
    if base:
        try:
            return _http_get_json(f"{base}/collections/{source_id}")
        except Exception:  # noqa: BLE001 - fall back to seed/registry metadata
            pass
    coll = _seed_collection(source_id)
    if coll and coll.get("id") == source_id:
        return coll
    return _collection_from_registry(source_id)


def list_items(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    """Return STAC items for the collection (STAC API first, then seed JSON)."""
    get_source(source_id)
    base = _stac_api_url()
    if base:
        try:
            data = _http_get_json(f"{base}/collections/{source_id}/items?limit=100")
            feats = data.get("features") if isinstance(data, dict) else None
            if feats:
                return feats
        except Exception:  # noqa: BLE001 - fall back to seed JSON
            pass
    return _seed_items(source_id)


def _acquisition_date(item: dict[str, Any]) -> str:
    props = item.get("properties", {})
    return props.get("akasha:acquisition_date") or (props.get("datetime", "") or "")[:10]


def _average_available(items: list[dict[str, Any]], property_name: str) -> float | None:
    values: list[float] = []
    for item in items:
        value = item.get("properties", {}).get(property_name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _usable_pixel_threshold_percent() -> float:
    try:
        return float(os.environ.get("USABLE_PIXEL_THRESHOLD_PERCENT", "70"))
    except ValueError:
        return 70.0


def _has_tile_assets(item: dict[str, Any], source_id: str) -> bool:
    return not _missing_tile_asset_keys(item, source_id)


def _missing_tile_asset_keys(item: dict[str, Any], source_id: str) -> list[str]:
    assets = item.get("assets", {})
    if not isinstance(assets, dict):
        assets = {}
    source = get_source(source_id)
    if source["kind"] == "sar":
        return [] if (assets.get("backscatter") or {}).get("href") else ["backscatter"]
    if source.get("tileRouteMode") == "context":
        context_asset = str((source.get("expectedAssets") or [""])[0])
        if context_asset and (assets.get(context_asset) or {}).get("href"):
            return []
        return [context_asset or "context"]
    analytic = assets.get("analytic") or {}
    mask_asset = str(source.get("maskAsset") or "scl")
    mask = assets.get(mask_asset) or {}
    missing: list[str] = []
    if not analytic.get("href"):
        missing.append("analytic")
    if not mask.get("href"):
        missing.append(mask_asset)
    return missing


def _tiles_available_for_date(source_id: str, date_items: list[dict[str, Any]]) -> bool:
    source = get_source(source_id)
    if source["kind"] == "sar" or source.get("tileRouteMode") == "context":
        return len(date_items) == 1 and all(
            _has_tile_assets(item, source_id) for item in date_items
        )
    return bool(date_items) and all(_has_tile_assets(item, source_id) for item in date_items)


def _tile_unavailable_reason(source_id: str, date_items: list[dict[str, Any]]) -> str | None:
    if _tiles_available_for_date(source_id, date_items):
        return None
    if not date_items:
        return "No servable catalog item is available for this date."

    source = get_source(source_id)
    if len(date_items) > 1 and source["kind"] == "sar":
        return (
            "Multiple same-date radar scenes require a mosaic backend before tiles are available."
        )
    if len(date_items) > 1 and source.get("tileRouteMode") == "context":
        return (
            "Multiple same-date context scenes require a mosaic backend before tiles are available."
        )

    missing = sorted(
        {
            key
            for item in date_items
            for key in _missing_tile_asset_keys(item, source_id)
        }
    )
    if missing:
        return f"Required raster assets are missing for this date: {', '.join(missing)}."
    return "Tiles are unavailable for this date."


def merged_bbox(items: list[dict[str, Any]]) -> list[float] | None:
    """Return the union of item bboxes in lon/lat order, if any are present."""
    bboxes: list[list[float]] = []
    for item in items:
        bbox = item.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            bboxes.append([float(v) for v in bbox])
        except (TypeError, ValueError):
            continue
    if not bboxes:
        return None
    return [
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    ]


def list_dates(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    """Return deduplicated per-date metadata (newest first) for a source."""
    source = get_source(source_id)
    items = list_items(source_id)
    if not items:
        return []

    grouped: dict[str, list[dict[str, Any]]] = {}
    explicit_latest = any("akasha:is_latest_usable" in item.get("properties", {}) for item in items)
    for item in items:
        acquisition_date = _acquisition_date(item)
        if not acquisition_date:
            continue
        grouped.setdefault(acquisition_date, []).append(item)

    dates: list[dict[str, Any]] = []
    for acquisition_date, grouped_items in grouped.items():
        date_items = _servable_items_for_date(source_id, grouped_items)
        datetimes = [
            item.get("properties", {}).get("datetime")
            for item in date_items
            if item.get("properties", {}).get("datetime")
        ]
        scene_count = len(date_items)
        coverage_percent = _average_available(date_items, "akasha:coverage_percent")
        is_explicit_latest = any(
            bool(item.get("properties", {}).get("akasha:is_latest_usable", False))
            for item in date_items
        )

        if source["dateMetricsKind"] == "radar":
            metrics_missing = coverage_percent is None
            tile_available = _tiles_available_for_date(source_id, date_items)
            dates.append(
                {
                    "acquisitionDate": acquisition_date,
                    "datetime": max(datetimes) if datetimes else None,
                    "sceneCount": scene_count,
                    "bounds": merged_bbox(date_items),
                    "usablePixelPercent": None,
                    "cloudMaskedPercent": None,
                    "coveragePercent": coverage_percent,
                    "isLatestUsable": is_explicit_latest if explicit_latest else False,
                    "metricsProvisional": (
                        scene_count > 1
                        or metrics_missing
                        or any(
                            bool(
                                item.get("properties", {}).get("akasha:metrics_provisional", False)
                            )
                            for item in date_items
                        )
                    ),
                    "tileAvailable": tile_available,
                    "unavailableReason": (
                        None
                        if tile_available
                        else _tile_unavailable_reason(source_id, date_items)
                    ),
                }
            )
            continue

        metrics_missing = any(
            item.get("properties", {}).get(name) is None
            for item in date_items
            for name in (
                "akasha:usable_pixel_percent",
                "akasha:cloud_masked_percent",
                "akasha:coverage_percent",
            )
        )
        tile_available = _tiles_available_for_date(source_id, date_items)
        dates.append(
            {
                "acquisitionDate": acquisition_date,
                "datetime": max(datetimes) if datetimes else None,
                "sceneCount": scene_count,
                "bounds": merged_bbox(date_items),
                "usablePixelPercent": _average_available(date_items, "akasha:usable_pixel_percent"),
                "cloudMaskedPercent": _average_available(date_items, "akasha:cloud_masked_percent"),
                "coveragePercent": coverage_percent,
                "isLatestUsable": is_explicit_latest,
                "metricsProvisional": (
                    scene_count > 1
                    or metrics_missing
                    or any(
                        bool(item.get("properties", {}).get("akasha:metrics_provisional", False))
                        for item in date_items
                    )
                ),
                "tileAvailable": tile_available,
                "unavailableReason": (
                    None if tile_available else _tile_unavailable_reason(source_id, date_items)
                ),
            }
        )
    dates.sort(key=lambda d: d.get("acquisitionDate") or "", reverse=True)
    if (
        source["dateMetricsKind"] == "radar"
        and dates
        and not any(bool(date["isLatestUsable"]) for date in dates)
    ):
        latest_selectable = next(
            (date for date in dates if bool(date.get("tileAvailable"))),
            dates[0],
        )
        latest_selectable["isLatestUsable"] = True
    if (
        source["dateMetricsKind"] == "optical"
        and dates
        and not explicit_latest
        and not any(bool(date["isLatestUsable"]) for date in dates)
    ):
        threshold = _usable_pixel_threshold_percent()
        latest_usable = next(
            (
                date
                for date in dates
                if bool(date.get("tileAvailable"))
                and isinstance(date.get("usablePixelPercent"), (int, float))
                and float(date["usablePixelPercent"]) >= threshold
            ),
            None,
        )
        if latest_usable is not None:
            latest_usable["isLatestUsable"] = True
    return dates


def items_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]:
    items = [item for item in list_items(source_id) if _acquisition_date(item) == acquisition_date]
    if items:
        return _servable_items_for_date(source_id, items)
    raise not_found(
        f"No scenes for source '{source_id}' on '{acquisition_date}'.",
        code="UNKNOWN_DATE",
        sourceId=source_id,
        acquisitionDate=acquisition_date,
    )


def get_item_for_date(source_id: str, acquisition_date: str) -> dict[str, Any]:
    return items_for_date(source_id, acquisition_date)[0]


def latest_items(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    dates = list_dates(source_id)
    if not dates:
        raise not_found(
            f"No acquisition dates are available for source '{source_id}'.",
            code="SOURCE_HAS_NO_DATES",
            sourceId=source_id,
        )
    chosen = next((d for d in dates if d["isLatestUsable"]), dates[0])
    return items_for_date(source_id, chosen["acquisitionDate"])


def latest_item(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    return latest_items(source_id)[0]


def _is_composite_item(item: dict[str, Any]) -> bool:
    props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
    return bool(item.get("akasha:composite") or props.get("akasha:composite"))


def _servable_items_for_date(source_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return public/served items for a date.

    ResourceSat keeps per-scene items for provenance, but once a dated
    composite exists it is the single served analytic+mask pair for tiles and
    statistics. Sentinel and SAR sources retain their same-date scene behavior.
    """
    if source_id not in RESOURCESAT_BOA_SOURCE_IDS:
        return items
    composites = [item for item in items if _is_composite_item(item)]
    return composites or items


def _band_names_from_raster_bands(asset: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for idx, band in enumerate(asset.get("raster:bands", []), start=1):
        name = band.get("name") or band.get("common_name") or band.get("description")
        names.append(str(name) if name else f"B{idx}")
    return names


def _resolve_item_assets(item: dict[str, Any], source_id: str | None = None) -> dict[str, Any]:
    """Resolve source-specific asset hrefs and minimal raster metadata for one item."""
    source_id = source_id or item.get("collection") or COLLECTION_ID
    source = get_source(source_id)
    assets = item.get("assets", {})

    if source["kind"] == "sar":
        backscatter = assets.get("backscatter")
        if not backscatter or not backscatter.get("href"):
            raise upstream_error(
                "STAC item is missing backscatter asset.",
                code="INCOMPLETE_ITEM",
                itemId=item.get("id"),
                sourceId=source_id,
            )
        raster_bands = backscatter.get("raster:bands", [])
        first = raster_bands[0] if raster_bands else {}
        band_names = _band_names_from_raster_bands(backscatter)
        if not band_names:
            polarizations = item.get("properties", {}).get("sar:polarizations") or []
            band_names = [str(pol).upper() for pol in polarizations] or ["VV"]
        return {
            "itemId": item.get("id"),
            "backscatterHref": backscatter.get("href"),
            "bandNames": band_names,
            "nodata": first.get("nodata", -9999.0),
            "epsg": backscatter.get("proj:epsg") or item.get("properties", {}).get("proj:epsg"),
            "bbox": item.get("bbox"),
        }

    if source.get("tileRouteMode") == "context":
        context_asset_key = str((source.get("expectedAssets") or [""])[0])
        context_asset = assets.get(context_asset_key)
        if not context_asset or not context_asset.get("href"):
            raise upstream_error(
                "STAC item is missing context display asset.",
                code="INCOMPLETE_ITEM",
                itemId=item.get("id"),
                sourceId=source_id,
                contextAsset=context_asset_key,
            )
        raster_bands = context_asset.get("raster:bands", [])
        first = raster_bands[0] if raster_bands else {}
        return {
            "itemId": item.get("id"),
            "contextHref": context_asset.get("href"),
            "contextAsset": context_asset_key,
            "bandNames": _band_names_from_raster_bands(context_asset),
            "rasterBandCount": len(raster_bands),
            "scale": float(first.get("scale", 1.0)),
            "offset": float(first.get("offset", 0.0)),
            "nodata": first.get("nodata"),
            "epsg": context_asset.get("proj:epsg")
            or item.get("properties", {}).get("proj:epsg"),
            "bbox": item.get("bbox"),
        }

    analytic = assets.get("analytic")
    mask_asset = str(source.get("maskAsset") or "scl")
    mask = assets.get(mask_asset)
    if not analytic or not mask:
        raise upstream_error(
            "STAC item is missing analytic/mask assets.",
            code="INCOMPLETE_ITEM",
            itemId=item.get("id"),
            sourceId=source_id,
            maskAsset=mask_asset,
        )
    band_names = [str(b.get("name")) for b in analytic.get("eo:bands", []) if b.get("name")]
    raster_bands = analytic.get("raster:bands", [])
    first = raster_bands[0] if raster_bands else {}
    band_role_mapping = _band_role_mapping_for_item(source_id, item)
    props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
    return {
        "itemId": item.get("id"),
        "analyticHref": analytic.get("href"),
        "sclHref": mask.get("href"),
        "maskHref": mask.get("href"),
        "maskAsset": mask_asset,
        "bandNames": band_names,
        "bandRoleMapping": band_role_mapping,
        "maskMethod": source.get("maskMethod"),
        "excludedMaskClasses": source.get("excludedMaskClasses"),
        "nodataPolicy": source.get("nodataPolicy", "selected_band_or_mask"),
        "metricsProvisional": bool(
            props.get("akasha:metrics_provisional", source.get("metricsProvisional", False))
        ),
        "scale": float(first.get("scale", 0.0001)),
        "offset": float(first.get("offset", source.get("reflectanceOffset", 0.0))),
        "nodata": first.get("nodata", 0),
        "epsg": analytic.get("proj:epsg") or item.get("properties", {}).get("proj:epsg"),
        "bbox": item.get("bbox"),
    }


def _band_role_mapping_for_item(source_id: str, item: dict[str, Any]) -> dict[str, str]:
    source = get_source(source_id)
    mapping: Any = source.get("bandRoleMapping", {})
    try:
        collection_mapping = get_collection(source_id).get("akasha:band_role_mapping")
        if isinstance(collection_mapping, dict) and collection_mapping:
            mapping = collection_mapping
    except Exception:  # noqa: BLE001
        pass
    item_mapping = item.get("properties", {}).get("akasha:band_role_mapping")
    if isinstance(item_mapping, dict) and item_mapping:
        mapping = item_mapping
    return {str(role): str(name) for role, name in dict(mapping).items()}


def resolve_assets(source_id: str, acquisition_date: str) -> dict[str, Any]:
    """Resolve source-specific asset hrefs + metadata for one date item."""
    return _resolve_item_assets(get_item_for_date(source_id, acquisition_date), source_id)


def resolve_assets_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]:
    """Resolve source-specific asset hrefs + metadata for all items on a date."""
    return [
        _resolve_item_assets(item, source_id)
        for item in items_for_date(source_id, acquisition_date)
    ]


def supported_indices(source_id: str = COLLECTION_ID) -> list[str]:
    source = get_source(source_id)
    advertised: Any = source.get("supportedIndices", [])
    try:
        coll = get_collection(source_id)
        if "akasha:supported_indices" in coll:
            advertised = coll.get("akasha:supported_indices")
    except Exception:  # noqa: BLE001
        advertised = source.get("supportedIndices", [])

    if advertised is None:
        advertised = []
    if not isinstance(advertised, list):
        advertised = source.get("supportedIndices", [])
    return [idx for idx in advertised if idx in SUPPORTED_INDICES]


def default_index(source_id: str = COLLECTION_ID) -> str:
    supported = supported_indices(source_id)
    if not supported:
        return ""
    try:
        configured = get_collection(source_id).get("akasha:default_index")
        if configured in supported:
            return configured
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_INDEX if DEFAULT_INDEX in supported else supported[0]
