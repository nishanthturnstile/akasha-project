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
COLLECTION_ID = SENTINEL_2_SOURCE_ID
SOURCE_LABEL = "Sentinel-2 L2A"
SOURCE_PROVIDER = "Copernicus"

_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    SENTINEL_2_SOURCE_ID: {
        "id": SENTINEL_2_SOURCE_ID,
        "label": "Sentinel-2 L2A",
        "provider": "Copernicus",
        "kind": "optical",
        "collectionId": SENTINEL_2_SOURCE_ID,
        "expectedAssets": ["analytic", "scl"],
        "supportedIndices": SUPPORTED_INDICES,
        "displayModes": ["RGB"],
        "defaultDisplayMode": "RGB",
        "description": "Optical Sentinel-2 L2A surface reflectance with cloud/SCL masking.",
        "attribution": "Copernicus Sentinel-2",
        "dateMetricsKind": "optical",
        "defaultRescale": "0,3000",
        "tileRouteMode": "rgb",
    },
    SENTINEL_1_SOURCE_ID: {
        "id": SENTINEL_1_SOURCE_ID,
        "label": "Sentinel-1 GRD",
        "provider": "Copernicus",
        "kind": "sar",
        "collectionId": SENTINEL_1_SOURCE_ID,
        "expectedAssets": ["backscatter"],
        "supportedIndices": [],
        "displayModes": ["VV_GRAYSCALE"],
        "defaultDisplayMode": "VV_GRAYSCALE",
        "description": "Radar layer · cloud-penetrating · not true colour.",
        "attribution": "Copernicus Sentinel-1",
        "dateMetricsKind": "radar",
        "defaultRescale": "-25,5",
        "tileRouteMode": "display-mode",
    },
}


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


def _collection_from_registry(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    return {
        "id": source["collectionId"],
        "title": source["label"],
        "description": source["description"],
        "providers": [{"name": source["provider"]}],
        "akasha:kind": source["kind"],
        "akasha:supported_indices": list(source["supportedIndices"]),
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
        "displayModes": list(source["displayModes"]),
        "defaultDisplayMode": source["defaultDisplayMode"],
        "description": source["description"],
        "attribution": source["attribution"],
        "dateMetricsKind": source["dateMetricsKind"],
        "defaultRescale": source["defaultRescale"],
        "tileRouteMode": source["tileRouteMode"],
    }


def list_sources() -> list[dict[str, Any]]:
    return [source_payload(source_id) for source_id in registered_source_ids()]


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


def _has_tile_assets(item: dict[str, Any], source_id: str) -> bool:
    assets = item.get("assets", {})
    source = get_source(source_id)
    if source["kind"] == "sar":
        backscatter = assets.get("backscatter") or {}
        return bool(backscatter.get("href"))
    analytic = assets.get("analytic") or {}
    scl = assets.get("scl") or {}
    return bool(analytic.get("href") and scl.get("href"))


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
        raise not_found(
            f"No catalog items for source '{source_id}'.", code="NO_ITEMS", sourceId=source_id
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    explicit_latest = any(
        "akasha:is_latest_usable" in item.get("properties", {}) for item in items
    )
    for item in items:
        acquisition_date = _acquisition_date(item)
        if not acquisition_date:
            continue
        grouped.setdefault(acquisition_date, []).append(item)

    dates: list[dict[str, Any]] = []
    for acquisition_date, date_items in grouped.items():
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
                                item.get("properties", {}).get(
                                    "akasha:metrics_provisional", False
                                )
                            )
                            for item in date_items
                        )
                    ),
                    "tileAvailable": scene_count == 1
                    and all(_has_tile_assets(item, source_id) for item in date_items),
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
        dates.append(
            {
                "acquisitionDate": acquisition_date,
                "datetime": max(datetimes) if datetimes else None,
                "sceneCount": scene_count,
                "bounds": merged_bbox(date_items),
                "usablePixelPercent": _average_available(
                    date_items, "akasha:usable_pixel_percent"
                ),
                "cloudMaskedPercent": _average_available(
                    date_items, "akasha:cloud_masked_percent"
                ),
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
                "tileAvailable": all(_has_tile_assets(item, source_id) for item in date_items),
            }
        )
    dates.sort(key=lambda d: d.get("acquisitionDate") or "", reverse=True)
    if source["dateMetricsKind"] == "radar" and dates and not any(
        bool(date["isLatestUsable"]) for date in dates
    ):
        latest_selectable = next(
            (date for date in dates if bool(date.get("tileAvailable"))),
            dates[0],
        )
        latest_selectable["isLatestUsable"] = True
    return dates


def items_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]:
    items = [item for item in list_items(source_id) if _acquisition_date(item) == acquisition_date]
    if items:
        return items
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
    chosen = next((d for d in dates if d["isLatestUsable"]), dates[0])
    return items_for_date(source_id, chosen["acquisitionDate"])


def latest_item(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    return latest_items(source_id)[0]


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
            band_names = [str(pol) for pol in polarizations if str(pol).upper() == "VV"] or ["VV"]
        return {
            "itemId": item.get("id"),
            "backscatterHref": backscatter.get("href"),
            "bandNames": band_names,
            "nodata": first.get("nodata", -9999.0),
            "epsg": backscatter.get("proj:epsg") or item.get("properties", {}).get("proj:epsg"),
            "bbox": item.get("bbox"),
        }

    analytic = assets.get("analytic")
    scl = assets.get("scl")
    if not analytic or not scl:
        raise upstream_error(
            "STAC item is missing analytic/scl assets.",
            code="INCOMPLETE_ITEM",
            itemId=item.get("id"),
            sourceId=source_id,
        )
    band_names = [b.get("name") for b in analytic.get("eo:bands", [])]
    raster_bands = analytic.get("raster:bands", [])
    first = raster_bands[0] if raster_bands else {}
    return {
        "itemId": item.get("id"),
        "analyticHref": analytic.get("href"),
        "sclHref": scl.get("href"),
        "bandNames": band_names,
        "scale": float(first.get("scale", 0.0001)),
        "offset": float(first.get("offset", -0.1)),
        "nodata": first.get("nodata", 0),
        "epsg": analytic.get("proj:epsg") or item.get("properties", {}).get("proj:epsg"),
        "bbox": item.get("bbox"),
    }


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
