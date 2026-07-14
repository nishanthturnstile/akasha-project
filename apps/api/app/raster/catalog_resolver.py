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
from dataclasses import dataclass
from datetime import date as _date
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import not_found, upstream_error
from .indices import DEFAULT_INDEX, SUPPORTED_INDICES

SENTINEL_2_SOURCE_ID = "sentinel-2-l2a"
SENTINEL_1_SOURCE_ID = "sentinel-1-grd"
RESOURCESAT_LISS3_SOURCE_ID = "resourcesat-2a-liss3-boa"
RESOURCESAT_AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
RESOURCESAT_LISS4_SOURCE_ID = "resourcesat-2a-liss4-mx70-l2"
EOS04_SAR_SOURCE_ID = "eos-04-sar-mrs-l2b"
RESOURCESAT_BOA_SOURCE_IDS = {
    RESOURCESAT_LISS3_SOURCE_ID,
    RESOURCESAT_AWIFS_SOURCE_ID,
    RESOURCESAT_LISS4_SOURCE_ID,
}
COLLECTION_ID = RESOURCESAT_LISS3_SOURCE_ID
SOURCE_LABEL = "ResourceSat-2A LISS-3 BOA"
SOURCE_PROVIDER = "ISRO/NRSC Bhoonidhi"
_LEGACY_SENTINEL_SOURCE_IDS = {SENTINEL_2_SOURCE_ID, SENTINEL_1_SOURCE_ID}
_EOS04_KNOWN_POLARIZATIONS = {"HH", "HV", "VH", "VV", "RH", "RV"}

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
        "revisitDays": 5,
        "refreshPolicy": (
            "Daily standalone-ingestion discovery over the latest seven complete provider days; "
            "only scenes with known cloud at or below 20% enter processing."
        ),
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
        "revisitDays": 24,
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
            "description": "Active regional ResourceSat-2A AWiFS BOA context source.",
            "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "fcc",
            "resolutionMeters": 56,
            "analysisLevel": "regional",
            "revisitDays": 5,
            "refreshPolicy": (
                "Scheduler-active Bhoonidhi ingestion; regional composites use a 60% "
                "minimum usable-coverage threshold."
            ),
            "limitations": [
                "Coarse 56 m pixels; use for regional context and large-field analytics.",
                (
                    "Mask is Akasha threshold-derived and provisional until a native "
                    "quality layer exists."
                ),
                (
                    "AWiFS-specific EO wavelengths are pending NRSC validation; STAC "
                    "currently uses the shared ResourceSat broad-band metadata aliases."
                ),
                "Not a replacement for LISS-3/LISS-4 field-level monitoring.",
            ],
            "maskMethod": (
                "Akasha threshold mask v1 for ResourceSat-2A AWiFS BOA "
                "(pending AWiFS-specific native quality-layer validation; provisional)."
            ),
            "excludedMaskClasses": [0, 2, 3],
            "availableMaskOptions": ["clouds", "cloudShadows"],
            "metricsProvisional": True,
            "availabilityStatus": "active",
            "gatedReason": None,
        },
        "resourcesat-2a-liss4-mx70-l2": {
            "id": "resourcesat-2a-liss4-mx70-l2",
            "label": "ResourceSat-2A LISS-4 MX70 L2",
            "provider": "ISRO/NRSC Bhoonidhi",
            "kind": "optical",
            "collectionId": "ResourceSat-2A_LISS4-MX70_L2",
            "expectedAssets": ["analytic", "mask"],
            "supportedIndices": ["NDVI", "MSAVI", "NDWI_GREEN_NIR"],
            "bandRoleMapping": {"GREEN": "BAND2", "RED": "BAND3", "NIR": "BAND4"},
            "maskAsset": "mask",
            "excludedMaskClasses": [0, 2, 3],
            "nodataPolicy": "mask_only",
            "displayModes": ["FCC", "NDVI", "MSAVI", "NDWI_GREEN_NIR"],
            "defaultDisplayMode": "FCC",
            "mapDisplayModes": ["NDVI", "MSAVI", "NDWI_GREEN_NIR"],
            "defaultMapDisplayMode": "NDVI",
            "layerGroups": [
                {"label": "Imagery", "modes": ["FCC"]},
                {"label": "Vegetation Indices", "modes": ["NDVI", "MSAVI"]},
                {"label": "Water Index", "modes": ["NDWI_GREEN_NIR"]},
            ],
            "description": (
                "ResourceSat-2A LISS-4 MX70 L2 high-resolution field analytics source "
                "with Akasha-generated provisional cloud/validity mask."
            ),
            "attribution": "ISRO-IRS, ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "optical",
            "defaultRescale": "0,3000",
            "tileRouteMode": "fcc",
            "resolutionMeters": 5.8,
            "analysisLevel": "field",
            "revisitDays": 5,
            "refreshPolicy": (
                "Bhoonidhi search on the ~5-day LISS-4 MX revisit cadence; L2 products may "
                "lag acquisition."
            ),
            "limitations": [
                "False-colour composite only; LISS-4 MX70 has no blue band.",
                "NDMI/NDRE/RECI unsupported because LISS-4 MX70 has no SWIR or red-edge band.",
                (
                    "Mask is Akasha threshold-derived and provisional until a native "
                    "quality layer exists."
                ),
            ],
            "maskMethod": "Akasha threshold mask v1 (LISS-4, no SWIR; provisional)",
            "availableMaskOptions": ["clouds", "cloudShadows"],
            "metricsProvisional": True,
            "availabilityStatus": "active",
            "gatedReason": None,
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
            "revisitDays": 8,
            "refreshPolicy": "Gated; context only, not field-level analytics.",
            "limitations": ["Precomputed NDVI only; not raw reflectance for plot statistics."],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": "No validated EOS-06 NDVI context COG has been ingested.",
        },
        EOS04_SAR_SOURCE_ID: {
            "id": EOS04_SAR_SOURCE_ID,
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
            "description": (
                "ISRO EOS-04 C-band SAR backscatter (display-only; "
                "cloud-penetrating, no optical indices)."
            ),
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "radar",
            "defaultRescale": "-25,5",
            "tileRouteMode": "vv_grayscale",
            "resolutionMeters": None,
            "analysisLevel": "context",
            "refreshPolicy": (
                "Validated single-scene backscatter display only; no optical indices or cloud mask."
            ),
            "limitations": [
                "Display-only SAR backscatter; no NDVI/MSAVI/NDMI/NDWI/NDRE/RECI.",
                "No cloud/SCL/ResourceSat threshold mask controls.",
                "Date-level mosaics are unavailable until a SAR mosaic backend exists.",
                "Catalog items must declare explicit SAR polarizations before tiles render.",
            ],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": (
                "EOS-04 is validated for backend SAR-assisted cloudy optical analytics; "
                "it is not a directly selectable optical index layer."
            ),
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
            "description": "NISAR S-band GCOV radar backscatter (display-only; cloud-penetrating).",
            "attribution": "ISRO/NRSC, Bhoonidhi",
            "dateMetricsKind": "radar",
            "defaultRescale": "-25,5",
            "tileRouteMode": "vv_grayscale",
            "resolutionMeters": None,
            "analysisLevel": "context",
            "refreshPolicy": "Backscatter display only; no optical indices or cloud mask.",
            "limitations": ["Not an optical vegetation-index source."],
            "maskMethod": None,
            "metricsProvisional": True,
            "availabilityStatus": "gated",
            "gatedReason": (
                "NISAR GCOV remains data-gated until calibrated ARD products are validated."
            ),
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
        "revisitDays": source.get("revisitDays"),
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
        {key for item in date_items for key in _missing_tile_asset_keys(item, source_id)}
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
                        None if tile_available else _tile_unavailable_reason(source_id, date_items)
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


def _sar_polarizations(item: dict[str, Any], asset: dict[str, Any]) -> list[str]:
    props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
    value = asset.get("sar:polarizations") or props.get("sar:polarizations") or []
    if isinstance(value, str):
        raw = [part for part in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    return [str(pol).strip().upper() for pol in raw if str(pol).strip()]


def _explicit_sar_band_names(asset: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for band in asset.get("raster:bands", []):
        name = band.get("name") or band.get("common_name") or band.get("description")
        if name:
            names.append(str(name))
    return names


def _sar_band_name_polarizations(band_names: list[str]) -> list[str]:
    polarizations: list[str] = []
    for name in band_names:
        tokens = [token for token in str(name).upper().replace("-", "_").split("_") if token]
        matched = next((token for token in tokens if token in _EOS04_KNOWN_POLARIZATIONS), None)
        if matched and matched not in polarizations:
            polarizations.append(matched)
    return polarizations


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
        polarizations = _sar_polarizations(item, backscatter)
        band_names = _explicit_sar_band_names(backscatter)
        if source_id == EOS04_SAR_SOURCE_ID:
            invalid_polarizations = [
                pol for pol in polarizations if pol not in _EOS04_KNOWN_POLARIZATIONS
            ]
            band_name_polarizations = _sar_band_name_polarizations(band_names)
            if invalid_polarizations or (not polarizations and not band_name_polarizations):
                raise upstream_error(
                    "EOS-04 SAR item must declare explicit valid SAR polarizations.",
                    code="MISSING_SAR_POLARIZATIONS",
                    itemId=item.get("id"),
                    sourceId=source_id,
                    availablePolarizations=polarizations,
                    availableBands=band_names,
                    allowedPolarizations=sorted(_EOS04_KNOWN_POLARIZATIONS),
                )
            if not polarizations:
                polarizations = band_name_polarizations
        if polarizations and (
            not band_names or all(name.upper().startswith("B") for name in band_names)
        ):
            band_names = polarizations
        if not band_names:
            band_names = ["VV"]
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
            "epsg": context_asset.get("proj:epsg") or item.get("properties", {}).get("proj:epsg"),
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


# ---------------------------------------------------------------------------
# Best-resolution resolver (Phase D)
# ---------------------------------------------------------------------------

_NDMI_PROVENANCE_NOTE = "Moisture served from LISS-3 (24 m) -- LISS-4 has no SWIR band."

# Indices not supported by LISS-4 (no SWIR / no red-edge).
_LISS4_UNSUPPORTED_INDICES: frozenset[str] = frozenset({"NDMI", "NDRE", "RECI"})


@dataclass
class ResolutionResult:
    """Result of the best-resolution source selection for a field + index + date."""

    source_id: str
    resolution_meters: float | None
    enhanced: bool
    basis_date: str | None
    provenance_note: str | None


def _bbox_from_geometry(geometry: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Return (minx, miny, maxx, maxy) for a GeoJSON Polygon or MultiPolygon, or None on error."""
    coords = geometry.get("coordinates")
    geom_type = geometry.get("type", "")
    if not isinstance(coords, list) or not coords:
        return None
    try:
        xs: list[float] = []
        ys: list[float] = []
        if geom_type == "MultiPolygon":
            for polygon in coords:
                for ring in polygon:
                    for pt in ring:
                        xs.append(float(pt[0]))
                        ys.append(float(pt[1]))
        else:
            for ring in coords:
                for pt in ring:
                    xs.append(float(pt[0]))
                    ys.append(float(pt[1]))
        if not xs or not ys:
            return None
        return (min(xs), min(ys), max(xs), max(ys))
    except (TypeError, ValueError, IndexError):
        return None


def _bbox_intersects(
    bbox: Any,
    geometry_bounds: tuple[float, float, float, float],
) -> bool:
    """Return True if ``bbox`` (list/tuple of 4 floats) intersects ``geometry_bounds``."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    try:
        minx, miny, maxx, maxy = (float(v) for v in bbox)
        gminx, gminy, gmaxx, gmaxy = geometry_bounds
    except (TypeError, ValueError):
        return False
    if minx > maxx or miny > maxy:
        return False
    return not (maxx < gminx or gmaxx < minx or maxy < gminy or gmaxy < miny)


def resolve_best_resolution_source(
    *,
    primary_source_id: str,
    index_type: str,
    field_geometry: dict[str, Any],
    acquisition_date: str,
    prefer_high_res: bool = True,
    window_days: int | None = None,
) -> ResolutionResult:
    """Select the best-resolution source for a field + index + date.

    Returns LISS-4 (5.8 m composite grid) when all of the following hold:
    - ``prefer_high_res`` is True
    - ``index_type`` is in the LISS-4 supported-indices set (NDVI/MSAVI/NDWI_GREEN_NIR)
    - a LISS-4 composite item exists whose date is within ``window_days`` of
      ``acquisition_date``
    - the composite item's bbox intersects ``field_geometry`` (used as a cheap
      coverage proxy; no raster reads are performed here)

    Otherwise returns the primary source (LISS-3).  NDMI/NDRE always return the
    primary source with a provenance note.  Any catalog error causes a silent
    fallback to the primary source so single-date analytics remain available.

    Coverage check: asset bbox intersection is used as a proxy for composite
    coverage; this may include fields near the composite edge that have partial
    no-data.  Full per-pixel coverage validation requires opening the COG and is
    intentionally deferred to the statistics/overlay computation step.
    """
    if window_days is None:
        # Imported lazily to avoid a top-level circular dependency.
        from ..config import settings as _settings

        window_days = _settings.best_resolution_window_days

    primary_source = get_source(primary_source_id)
    primary_resolution: float | None = primary_source.get("resolutionMeters")

    def _primary(note: str | None = None) -> ResolutionResult:
        return ResolutionResult(
            source_id=primary_source_id,
            resolution_meters=primary_resolution,
            enhanced=False,
            basis_date=None,
            provenance_note=note,
        )

    # LISS-4 enhancement only applies when the primary source is LISS-3.
    # For Sentinel, AWiFS, and other sources, return the primary unchanged.
    if primary_source_id != RESOURCESAT_LISS3_SOURCE_ID:
        return _primary()

    # NDMI/NDRE must always use LISS-3 (LISS-4 has no SWIR/red-edge).
    if index_type in _LISS4_UNSUPPORTED_INDICES:
        note = _NDMI_PROVENANCE_NOTE if index_type == "NDMI" else None
        return _primary(note)

    if not prefer_high_res:
        return _primary()

    if not acquisition_date:
        return _primary()

    try:
        liss4_source = get_source(RESOURCESAT_LISS4_SOURCE_ID)
    except Exception:  # noqa: BLE001
        return _primary()

    liss4_indices: set[str] = set(liss4_source.get("supportedIndices", []))
    if index_type not in liss4_indices:
        return _primary()

    try:
        target = _date.fromisoformat(acquisition_date)
        window_start = target - timedelta(days=window_days)
        window_end = target + timedelta(days=window_days)

        liss4_dates = list_dates(RESOURCESAT_LISS4_SOURCE_ID)
        candidates = [
            d
            for d in liss4_dates
            if window_start <= _date.fromisoformat(d["acquisitionDate"]) <= window_end
        ]
        if not candidates:
            return _primary()

        # Pick the composite whose date is closest to the requested date.
        candidates.sort(
            key=lambda d: abs((_date.fromisoformat(d["acquisitionDate"]) - target).days)
        )
        best = candidates[0]

        # Coverage check: bbox intersection as proxy (no raster reads).
        field_bbox = _bbox_from_geometry(field_geometry)
        composite_bbox = best.get("bounds")
        if field_bbox is not None and composite_bbox is not None:
            if not _bbox_intersects(composite_bbox, field_bbox):
                return _primary()

        liss4_resolution: float = float(liss4_source.get("resolutionMeters") or 5.8)
        return ResolutionResult(
            source_id=RESOURCESAT_LISS4_SOURCE_ID,
            resolution_meters=liss4_resolution,
            enhanced=True,
            basis_date=best["acquisitionDate"],
            provenance_note=None,
        )
    except Exception:  # noqa: BLE001 - any catalog error → silent fallback
        return _primary()


# ---------------------------------------------------------------------------
# Best-observation resolver (Phase 11 / TASK-066–069)
# ---------------------------------------------------------------------------

# Priority for cross-source ranking (higher = preferred).
# Sources absent from this map get _DEFAULT_SOURCE_PRIORITY.
_SOURCE_PRIORITY_MAP: dict[str, int] = {
    RESOURCESAT_LISS4_SOURCE_ID: 100,  # 5.8 m high-res field enhancement
    RESOURCESAT_LISS3_SOURCE_ID: 80,  # 24 m field-level production baseline
    RESOURCESAT_AWIFS_SOURCE_ID: 20,  # 56 m regional (coarse)
}
_DEFAULT_SOURCE_PRIORITY: int = 10

# Analysis levels considered coarse for field-level use cases.
_COARSE_ANALYSIS_LEVELS: frozenset[str] = frozenset({"regional", "context", "archive"})

# Sources considered coarse regardless of analysis_level metadata.
_COARSE_SOURCES: frozenset[str] = frozenset({RESOURCESAT_AWIFS_SOURCE_ID})


@dataclass
class ObservationCandidate:
    """A ranked candidate observation from the best-observation resolver.

    Attributes
    ----------
    score
        Weighted [0, 100] ranking score (higher is better).  Derived from
        source priority, date proximity, usable-pixel percent, and coverage.
    is_coarse
        True when the source is regional/coarse (e.g. AWiFS 56 m).  Coarse
        candidates are excluded from field-level queries unless ``allow_coarse``
        is True.
    """

    source_id: str
    acquisition_date: str
    resolution_meters: float | None
    analysis_level: str | None
    usable_pixel_percent: float | None
    coverage_percent: float | None
    cloud_masked_percent: float | None
    tile_available: bool
    is_latest_usable: bool
    score: float
    source_priority: int
    provenance_note: str | None
    is_coarse: bool
    supported_indices: list[str]
    label: str


def _observation_score(
    *,
    source_priority: int,
    days_diff: int,
    usable_pixel_percent: float | None,
    coverage_percent: float | None,
    window_days: int,
) -> float:
    """Return a weighted [0, 100] score for a candidate observation.

    Weights: source_priority=40%, date_proximity=35%, usable_pixels=15%, coverage=10%.
    Unknown quality metrics default to 50 (neutral/unknown).
    """
    priority_score = float(min(100, max(0, source_priority)))
    proximity = max(0.0, 100.0 - abs(days_diff) * (100.0 / max(1, window_days)))
    usable = float(usable_pixel_percent) if usable_pixel_percent is not None else 50.0
    coverage = float(coverage_percent) if coverage_percent is not None else 50.0
    return 0.40 * priority_score + 0.35 * proximity + 0.15 * usable + 0.10 * coverage


def resolve_best_observation(
    *,
    target_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_days: int | None = None,
    index_type: str | None = None,
    use_case: str = "field",
    allow_coarse: bool = False,
    field_geometry: dict[str, Any] | None = None,
    max_candidates: int = 10,
    window_days: int = 30,
) -> list[ObservationCandidate]:
    """Rank validated active observations across sources for best-observation selection.

    Ranking considers: source state (active/gated), index support, date proximity,
    coverage, usable-pixel percent, field intersection (bbox proxy), analysis level,
    resolution, and source priority.

    Parameters
    ----------
    target_date:
        YYYY-MM-DD centre date for proximity scoring.  Falls back to ``end_date``
        when not provided; no proximity weighting when neither is given.
    start_date / end_date / lookback_days:
        Date window for candidate filtering.  ``lookback_days`` is applied backward
        from ``target_date`` (or ``end_date``) when ``start_date`` is omitted.
        When no window parameters are given, ``window_days`` is applied
        symmetrically around ``target_date``.
    index_type:
        If set, only sources that support this index are considered (e.g. "NDVI").
        Non-optical sources are also excluded when an index is requested.
    use_case:
        ``"field"`` (default) excludes coarse/regional sources unless
        ``allow_coarse=True``; ``"regional"`` allows them unconditionally.
    allow_coarse:
        When True, coarse/regional sources (e.g. AWiFS 56 m) are eligible even
        for field queries.  AWiFS still requires ``availabilityStatus == "active"``.
    field_geometry:
        Optional GeoJSON Polygon/MultiPolygon.  When supplied, candidates whose
        date-level bounds bbox does not intersect are filtered out.  This is a
        cheap metadata-only proxy; no raster reads are performed.
    max_candidates:
        Upper bound on returned candidates (capped to 50).
    window_days:
        Symmetric window (days) around ``target_date`` when no explicit start/end
        dates are given.

    Returns
    -------
    list[ObservationCandidate]
        Up to ``max_candidates`` candidates ordered by descending score (best first).
        Only sources with ``availabilityStatus == "active"`` are included.
        AWiFS and other coarse sources are excluded from field-level decisions
        unless ``allow_coarse`` is True or ``use_case == "regional"``.
    """
    # Resolve target date for proximity scoring and lookback anchoring.
    target: _date | None = None
    today = _date.today()
    try:
        if target_date:
            target = _date.fromisoformat(target_date)
        elif end_date:
            target = _date.fromisoformat(end_date)
    except ValueError:
        target = None

    # Resolve search window.
    w_start: _date | None = None
    w_end: _date | None = None
    try:
        if start_date:
            w_start = _date.fromisoformat(start_date)
        if end_date:
            w_end = _date.fromisoformat(end_date)
    except ValueError:
        pass

    lookback_anchor = target or today
    if w_start is None and lookback_days is not None:
        w_start = lookback_anchor - timedelta(days=lookback_days - 1)
        if w_end is None:
            w_end = lookback_anchor
    if w_start is None and target is not None:
        w_start = target - timedelta(days=window_days)
    if w_end is None and target is not None:
        w_end = target + timedelta(days=window_days)
    if w_start is not None and w_end is None:
        w_end = today

    # Precompute field bbox for intersection checks (metadata-only; no raster reads).
    field_bbox: tuple[float, float, float, float] | None = None
    if field_geometry:
        field_bbox = _bbox_from_geometry(field_geometry)
        if field_bbox is None:
            return []

    candidates: list[ObservationCandidate] = []

    for source_id in selectable_source_ids():
        try:
            source = get_source(source_id)
        except Exception:  # noqa: BLE001
            continue

        # Only include sources with active availability.
        if source.get("availabilityStatus", "active") != "active":
            continue

        source_kind = source.get("kind", "optical")

        # Best-observation resolution ranks optical field analytics only.
        if source_kind != "optical":
            continue

        # Check index support.
        if index_type and index_type not in source.get("supportedIndices", []):
            continue

        # Coarse-source exclusion for field-level queries.
        is_coarse = (
            source_id in _COARSE_SOURCES
            or source.get("analysisLevel", "field") in _COARSE_ANALYSIS_LEVELS
        )
        if is_coarse and use_case == "field" and not allow_coarse:
            continue

        source_priority = _SOURCE_PRIORITY_MAP.get(source_id, _DEFAULT_SOURCE_PRIORITY)
        resolution = source.get("resolutionMeters")
        analysis_level = source.get("analysisLevel")
        label = str(source.get("label", source_id))
        src_indices_list: list[str] = list(source.get("supportedIndices", []))

        try:
            dates = list_dates(source_id)
        except Exception:  # noqa: BLE001
            continue

        for date_entry in dates:
            acq_raw = date_entry.get("acquisitionDate")
            if not acq_raw or not isinstance(acq_raw, str):
                continue
            try:
                acq = _date.fromisoformat(acq_raw)
            except ValueError:
                continue

            # Apply date window filter.
            if w_start and acq < w_start:
                continue
            if w_end and acq > w_end:
                continue

            tile_available = bool(date_entry.get("tileAvailable", False))
            if not tile_available:
                continue

            # Field intersection check (bbox proxy; no raster reads).
            bounds = date_entry.get("bounds")
            if field_bbox is not None and not _bbox_intersects(bounds, field_bbox):
                continue

            days_diff = abs((acq - target).days) if target is not None else 0
            usable = date_entry.get("usablePixelPercent")
            coverage = date_entry.get("coveragePercent")
            cloud = date_entry.get("cloudMaskedPercent")

            score = _observation_score(
                source_priority=source_priority,
                days_diff=days_diff,
                usable_pixel_percent=usable,
                coverage_percent=coverage,
                window_days=window_days,
            )

            candidates.append(
                ObservationCandidate(
                    source_id=source_id,
                    acquisition_date=acq_raw,
                    resolution_meters=resolution,
                    analysis_level=analysis_level,
                    usable_pixel_percent=usable,
                    coverage_percent=coverage,
                    cloud_masked_percent=cloud,
                    tile_available=tile_available,
                    is_latest_usable=bool(date_entry.get("isLatestUsable", False)),
                    score=round(score, 4),
                    source_priority=source_priority,
                    provenance_note=None,
                    is_coarse=is_coarse,
                    supported_indices=src_indices_list,
                    label=label,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: max(1, min(max_candidates, 50))]
