"""Catalog resolver: source/date/asset metadata for the BFF (Slice 2).

Resolution order:
  1. STAC API (`STAC_API_URL`) when configured — the runtime source of truth
     on Railway / local Docker.
  2. Local seed STAC JSON under `data/seed/stac/` — used for offline/static
     validation and the Emergent live preview (where STAC API is not running).

No heavy deps: uses stdlib `urllib`/`json` only.
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

COLLECTION_ID = "sentinel-2-l2a"
SOURCE_LABEL = "Sentinel-2 L2A"
SOURCE_PROVIDER = "Copernicus"


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


# --- collection ------------------------------------------------------------
@lru_cache(maxsize=4)
def _seed_collection() -> dict[str, Any]:
    path = _seed_dir() / "stac" / f"{COLLECTION_ID}-collection.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=4)
def _seed_items() -> list[dict[str, Any]]:
    path = _seed_dir() / "stac" / f"{COLLECTION_ID}-sample-item.json"
    if not path.is_file():
        return []
    return [json.loads(path.read_text())]


def get_collection(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    """Return the STAC collection document (STAC API first, then seed JSON)."""
    base = _stac_api_url()
    if base:
        try:
            return _http_get_json(f"{base}/collections/{source_id}")
        except Exception:  # noqa: BLE001 - fall back to seed JSON
            pass
    coll = _seed_collection()
    if coll and coll.get("id") == source_id:
        return coll
    raise not_found(f"Unknown source '{source_id}'.", code="UNKNOWN_SOURCE", sourceId=source_id)


def list_items(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    """Return STAC items for the collection (STAC API first, then seed JSON)."""
    base = _stac_api_url()
    if base:
        try:
            data = _http_get_json(f"{base}/collections/{source_id}/items?limit=100")
            feats = data.get("features") if isinstance(data, dict) else None
            if feats:
                return feats
        except Exception:  # noqa: BLE001 - fall back to seed JSON
            pass
    return [it for it in _seed_items() if it.get("collection") == source_id]


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


def _has_tile_assets(item: dict[str, Any]) -> bool:
    assets = item.get("assets", {})
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
    items = list_items(source_id)
    if not items:
        raise not_found(
            f"No catalog items for source '{source_id}'.", code="NO_ITEMS", sourceId=source_id
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
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
                "coveragePercent": _average_available(date_items, "akasha:coverage_percent"),
                "isLatestUsable": any(
                    bool(item.get("properties", {}).get("akasha:is_latest_usable", False))
                    for item in date_items
                ),
                "metricsProvisional": (
                    scene_count > 1
                    or metrics_missing
                    or any(
                        bool(item.get("properties", {}).get("akasha:metrics_provisional", False))
                        for item in date_items
                    )
                ),
                "tileAvailable": all(_has_tile_assets(item) for item in date_items),
            }
        )
    dates.sort(key=lambda d: d.get("acquisitionDate") or "", reverse=True)
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


def _resolve_item_assets(item: dict[str, Any]) -> dict[str, Any]:
    """Resolve analytic/SCL asset hrefs + band metadata for one STAC item.

    Returns a dict with: analyticHref, sclHref, bandNames (ordered),
    scale, offset, nodata.
    """
    assets = item.get("assets", {})
    analytic = assets.get("analytic")
    scl = assets.get("scl")
    if not analytic or not scl:
        raise upstream_error(
            "STAC item is missing analytic/scl assets.",
            code="INCOMPLETE_ITEM",
            itemId=item.get("id"),
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
    """Resolve analytic/SCL asset hrefs + band metadata for one date item."""
    return _resolve_item_assets(get_item_for_date(source_id, acquisition_date))


def resolve_assets_for_date(source_id: str, acquisition_date: str) -> list[dict[str, Any]]:
    """Resolve analytic/SCL asset hrefs + band metadata for all items on a date."""
    return [_resolve_item_assets(item) for item in items_for_date(source_id, acquisition_date)]


def supported_indices(source_id: str = COLLECTION_ID) -> list[str]:
    coll = {}
    try:
        coll = get_collection(source_id)
    except Exception:  # noqa: BLE001
        coll = {}
    advertised = coll.get("akasha:supported_indices") or SUPPORTED_INDICES
    supported = [idx for idx in advertised if idx in SUPPORTED_INDICES]
    return supported or SUPPORTED_INDICES


def default_index(source_id: str = COLLECTION_ID) -> str:
    try:
        return get_collection(source_id).get("akasha:default_index") or DEFAULT_INDEX
    except Exception:  # noqa: BLE001
        return DEFAULT_INDEX
