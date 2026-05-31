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


def list_dates(source_id: str = COLLECTION_ID) -> list[dict[str, Any]]:
    """Return per-date metadata (newest first) for a source."""
    items = list_items(source_id)
    if not items:
        raise not_found(
            f"No catalog items for source '{source_id}'.", code="NO_ITEMS", sourceId=source_id
        )
    dates: list[dict[str, Any]] = []
    for item in items:
        props = item.get("properties", {})
        dates.append(
            {
                "acquisitionDate": _acquisition_date(item),
                "datetime": props.get("datetime"),
                "usablePixelPercent": props.get("akasha:usable_pixel_percent"),
                "cloudMaskedPercent": props.get("akasha:cloud_masked_percent"),
                "coveragePercent": props.get("akasha:coverage_percent"),
                "isLatestUsable": bool(props.get("akasha:is_latest_usable", False)),
                "metricsProvisional": bool(props.get("akasha:metrics_provisional", False)),
                "tileAvailable": True,
            }
        )
    dates.sort(key=lambda d: d.get("acquisitionDate") or "", reverse=True)
    return dates


def get_item_for_date(source_id: str, acquisition_date: str) -> dict[str, Any]:
    for item in list_items(source_id):
        if _acquisition_date(item) == acquisition_date:
            return item
    raise not_found(
        f"No scene for source '{source_id}' on '{acquisition_date}'.",
        code="UNKNOWN_DATE",
        sourceId=source_id,
        acquisitionDate=acquisition_date,
    )


def latest_item(source_id: str = COLLECTION_ID) -> dict[str, Any]:
    dates = list_dates(source_id)
    chosen = next((d for d in dates if d["isLatestUsable"]), dates[0])
    return get_item_for_date(source_id, chosen["acquisitionDate"])


def resolve_assets(source_id: str, acquisition_date: str) -> dict[str, Any]:
    """Resolve analytic/SCL asset hrefs + band metadata for stats/tiles.

    Returns a dict with: analyticHref, sclHref, bandNames (ordered),
    scale, offset, nodata.
    """
    item = get_item_for_date(source_id, acquisition_date)
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
