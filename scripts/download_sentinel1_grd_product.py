"""Search and optionally download Copernicus Sentinel-1 GRD SAFE products.

This downloader targets the CDSE STAC collection ``sentinel-1-grd``. It is
dry-run-first: by default it writes a coverage manifest and does not request
credentials or download data. Use ``--download`` or ``--download-selected`` with
``--yes`` to opt in to native SAFE ZIP downloads.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STAC_API_URL = "https://stac.dataspace.copernicus.eu/v1"
ODATA_API_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
ODATA_DOWNLOAD_API_URL = "https://download.dataspace.copernicus.eu/odata/v1"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
COLLECTION_ID = "sentinel-1-grd"
REFERENCE_DATETIME = datetime(2026, 4, 27, tzinfo=UTC)
REFERENCE_DATE = REFERENCE_DATETIME.date()

BBOX_PRESETS = {
    "south-india-target": [74.168701, 8.085101, 81.013184, 14.434701],
}
ACCEPTED_PRODUCT_TYPES = (
    "IW_GRDH_1S",
    "IW_GRDH_1A",
)
LARGE_DOWNLOAD_BYTES = 1 * 1024 * 1024 * 1024

STAC_SEARCH_FIELDS = [
    "id",
    "collection",
    "bbox",
    "assets",
    "properties.datetime",
    "properties.platform",
    "properties.product:type",
    "properties.sar:instrument_mode",
    "properties.sar:polarizations",
    "properties.sat:relative_orbit",
    "properties.sat:orbit_state",
    "properties.sat:absolute_orbit",
]


@dataclass(frozen=True)
class CandidateProduct:
    item_id: str
    datetime: str | None
    platform: str | None
    product_type: str | None
    instrument_mode: str | None
    polarizations: tuple[str, ...]
    relative_orbit: int | str | None
    orbit_state: str | None
    absolute_orbit: int | str | None
    bbox: list[float] | None
    overlap_bbox: list[float] | None
    overlap_area: float
    overlap_percent: float
    product_href: str | None
    product_uuid: str | None
    download_url: str | None
    download_url_mode: str | None
    availability_status: str
    availability_reason: str | None
    content_length: int | None
    s3_path: str | None

    @property
    def has_vv(self) -> bool:
        return "VV" in self.polarizations

    @property
    def has_dual_vv_vh(self) -> bool:
        return "VV" in self.polarizations and "VH" in self.polarizations

    @property
    def safe_name(self) -> str:
        return self.item_id if self.item_id.endswith(".SAFE") else f"{self.item_id}.SAFE"

    @property
    def zip_name(self) -> str:
        return f"{self.safe_name}.zip"


def load_root_env() -> None:
    """Load simple KEY=VALUE pairs from the ignored repo-root .env file if present."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def default_datetime_range(
    reference_date: date = REFERENCE_DATE, window_days: int = 7
) -> str:
    """Return an inclusive STAC datetime interval around a Sentinel-1 target date."""
    start_date = reference_date - timedelta(days=window_days)
    end_date = reference_date + timedelta(days=window_days)
    return (
        f"{start_date.isoformat()}T00:00:00Z/"
        f"{end_date.isoformat()}T23:59:59Z"
    )


def bbox_intersection(a: list[float], b: list[float]) -> list[float] | None:
    west = max(a[0], b[0])
    south = max(a[1], b[1])
    east = min(a[2], b[2])
    north = min(a[3], b[3])
    if west >= east or south >= north:
        return None
    return [west, south, east, north]


def bbox_area_degrees(bbox: list[float]) -> float:
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return width * height


def overlap_percent(target_bbox: list[float], item_bbox: list[float] | None) -> float:
    if item_bbox is None:
        return 0.0
    intersection = bbox_intersection(target_bbox, item_bbox)
    if intersection is None:
        return 0.0
    target_area = bbox_area_degrees(target_bbox)
    if target_area <= 0:
        return 0.0
    return bbox_area_degrees(intersection) / target_area * 100.0


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _form_request(url: str, fields: dict[str, str], *, timeout: int = 60) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get_access_token(*, prompt_credentials: bool = False) -> str:
    token = os.environ.get("CDSE_ACCESS_TOKEN")
    if token:
        return token

    username = os.environ.get("CDSE_USERNAME")
    password = os.environ.get("CDSE_PASSWORD")
    if prompt_credentials and not username:
        username = input("Copernicus Data Space username: ").strip()
    if prompt_credentials and not password:
        password = getpass.getpass("Copernicus Data Space password: ")
    if not username or not password:
        raise RuntimeError(
            "download requires credentials. Set CDSE_ACCESS_TOKEN, or set "
            "CDSE_USERNAME/CDSE_PASSWORD, or run with --prompt-credentials."
        )

    data = _form_request(
        TOKEN_URL,
        {
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
    )
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Copernicus token response did not contain access_token")
    return access_token


def parse_bbox(values: list[str] | None, preset: str | None) -> list[float]:
    if values is not None:
        if len(values) != 4:
            raise argparse.ArgumentTypeError(
                "--bbox requires four numbers: min_lon min_lat max_lon max_lat"
            )
        bbox = [float(value) for value in values]
    else:
        bbox = BBOX_PRESETS[preset or "south-india-target"]
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise argparse.ArgumentTypeError(f"invalid bbox: {bbox}")
    return bbox


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.1f} {unit}"


def _asset_href(asset: dict[str, Any] | None) -> str | None:
    if not isinstance(asset, dict):
        return None
    href = asset.get("href")
    return href if isinstance(href, str) else None


def _product_uuid_from_href(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r"Products\(([^)]+)\)", href)
    return match.group(1) if match else None


def _download_odata_url(product_uuid: str, suffix: str = "$value") -> str:
    safe_suffix = suffix if suffix in {"$value", "$zip"} else "$value"
    return f"{ODATA_DOWNLOAD_API_URL}/Products({product_uuid})/{safe_suffix}"


def _is_download_odata_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "download.dataspace.copernicus.eu"
        and parsed.path.startswith("/odata/v1/Products(")
        and parsed.path.endswith(("/$value", "/$zip"))
    )


def _is_safe_zip_href(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.path.lower().endswith(".zip")


def _find_product_asset(assets: dict[str, Any]) -> dict[str, Any] | None:
    product_asset = assets.get("Product")
    if isinstance(product_asset, dict):
        return product_asset
    for name, asset in assets.items():
        if isinstance(name, str) and name.lower() == "product" and isinstance(asset, dict):
            return asset
    return None


def _product_details_content_length(details: dict[str, Any]) -> int | None:
    content_length = details.get("ContentLength")
    return content_length if isinstance(content_length, int) else None


def resolve_download_url(
    product_href: str | None, product_uuid: str | None, details: dict[str, Any]
) -> tuple[str | None, str | None, str, str | None]:
    """Resolve a native SAFE ZIP URL without exposing credentials or tokens."""
    if product_href:
        if _is_download_odata_url(product_href):
            suffix = "$zip" if product_href.endswith("/$zip") else "$value"
            online = details.get("Online")
            status = "online" if online is True else "unverified"
            if online is False:
                return product_href, f"stac_product_asset_odata_{suffix[1:]}", "offline", None
            return product_href, f"stac_product_asset_odata_{suffix[1:]}", status, None
        if _is_safe_zip_href(product_href):
            return product_href, "stac_product_asset_zip", "unverified", None

    uuid = product_uuid or _product_uuid_from_href(product_href)
    if uuid:
        online = details.get("Online")
        if online is False:
            return _download_odata_url(uuid), "cdse_odata_value", "offline", None
        status = "online" if online is True else "unverified"
        return _download_odata_url(uuid), "cdse_odata_value", status, None

    return None, None, "missing_download_url", "no STAC Product asset or OData product UUID"


def _parse_item_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _time_delta_seconds(value: str | None) -> float:
    parsed = _parse_item_datetime(value)
    if parsed is None:
        return float("inf")
    return abs((parsed - REFERENCE_DATETIME).total_seconds())


def _candidate_rank(candidate: CandidateProduct) -> tuple[bool, bool, float, float, str]:
    return (
        candidate.overlap_area <= 0,
        not candidate.has_dual_vv_vh,
        _time_delta_seconds(candidate.datetime),
        -candidate.overlap_percent,
        candidate.item_id,
    )


def search_grd_items(*, bbox: list[float], datetime_range: str, limit: int) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "collections": [COLLECTION_ID],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": min(limit, 100),
        "fields": {"include": STAC_SEARCH_FIELDS},
    }
    items: list[dict[str, Any]] = []
    url = f"{STAC_API_URL}/search"
    method = "POST"
    next_payload: dict[str, Any] | None = payload

    while True:
        page = _json_request(url, method=method, payload=next_payload)
        items.extend(page.get("features", []))
        if len(items) >= limit:
            return items[:limit]
        next_link = next(
            (link for link in page.get("links", []) if link.get("rel") == "next"), None
        )
        if not next_link:
            return items
        url = next_link["href"]
        method = str(next_link.get("method", "GET")).upper()
        next_payload = next_link.get("body") if method == "POST" else None


def get_odata_product_details(product_uuid: str | None) -> dict[str, Any]:
    if not product_uuid:
        return {}
    url = (
        f"{ODATA_API_URL}/Products({product_uuid})?"
        + urllib.parse.urlencode({"$select": "Id,Name,ContentLength,S3Path,Online,ContentDate"})
    )
    try:
        return _json_request(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return {}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).upper() for item in value if isinstance(item, str))


def _is_candidate(properties: dict[str, Any]) -> bool:
    instrument_mode = properties.get("sar:instrument_mode")
    product_type = properties.get("product:type")
    polarizations = _string_tuple(properties.get("sar:polarizations"))
    return (
        instrument_mode == "IW"
        and product_type in ACCEPTED_PRODUCT_TYPES
        and "VV" in polarizations
    )


def collect_candidates(
    *, items: list[dict[str, Any]], target_bbox: list[float]
) -> list[CandidateProduct]:
    candidates: list[CandidateProduct] = []
    target_area = bbox_area_degrees(target_bbox)
    for item in items:
        properties = item.get("properties", {})
        if not isinstance(properties, dict) or not _is_candidate(properties):
            continue

        assets = item.get("assets", {})
        if not isinstance(assets, dict):
            assets = {}
        product_asset = _find_product_asset(assets)
        product_href = _asset_href(product_asset)
        product_uuid = _product_uuid_from_href(product_href)
        details = get_odata_product_details(product_uuid)
        (
            download_url,
            download_mode,
            availability_status,
            availability_reason,
        ) = resolve_download_url(product_href, product_uuid, details)
        content_length = _product_details_content_length(details)
        s3_path = details.get("S3Path")

        item_bbox = item.get("bbox") if isinstance(item.get("bbox"), list) else None
        overlap_bbox = bbox_intersection(target_bbox, item_bbox) if item_bbox else None
        overlap_area = bbox_area_degrees(overlap_bbox) if overlap_bbox else 0.0
        overlap_value = (overlap_area / target_area * 100.0) if target_area > 0 else 0.0

        candidates.append(
            CandidateProduct(
                item_id=str(item.get("id")),
                datetime=properties.get("datetime")
                if isinstance(properties.get("datetime"), str)
                else None,
                platform=properties.get("platform")
                if isinstance(properties.get("platform"), str)
                else None,
                product_type=properties.get("product:type")
                if isinstance(properties.get("product:type"), str)
                else None,
                instrument_mode=properties.get("sar:instrument_mode")
                if isinstance(properties.get("sar:instrument_mode"), str)
                else None,
                polarizations=_string_tuple(properties.get("sar:polarizations")),
                relative_orbit=properties.get("sat:relative_orbit"),
                orbit_state=properties.get("sat:orbit_state")
                if isinstance(properties.get("sat:orbit_state"), str)
                else None,
                absolute_orbit=properties.get("sat:absolute_orbit"),
                bbox=item_bbox,
                overlap_bbox=overlap_bbox,
                overlap_area=overlap_area,
                overlap_percent=overlap_value,
                product_href=product_href,
                product_uuid=product_uuid,
                download_url=download_url,
                download_url_mode=download_mode,
                availability_status=availability_status,
                availability_reason=availability_reason,
                content_length=content_length,
                s3_path=s3_path if isinstance(s3_path, str) else None,
            )
        )
    return sorted(candidates, key=_candidate_rank)


def select_candidate(
    candidates: list[CandidateProduct], candidate_index: int
) -> CandidateProduct | None:
    if not candidates:
        return None
    if candidate_index < 1 or candidate_index > len(candidates):
        raise SystemExit(f"--candidate-index must be between 1 and {len(candidates)}")
    return candidates[candidate_index - 1]


def _manifest_warning_for_candidate(candidate: CandidateProduct | None) -> str | None:
    if candidate is None:
        return "no Sentinel-1 GRD candidate selected"
    if not candidate.download_url:
        return "selected product has no resolved native SAFE ZIP download URL"
    if candidate.availability_status == "offline":
        return "selected product is not online in CDSE OData metadata"
    return None


def write_manifest(
    path: Path,
    *,
    bbox: list[float],
    datetime_range: str,
    selected: CandidateProduct | list[CandidateProduct] | None,
    candidates: list[CandidateProduct],
    download_statuses: dict[str, str] | None = None,
    extra_warnings: list[str] | None = None,
) -> None:
    selected_candidates = (
        selected
        if isinstance(selected, list)
        else ([selected] if selected is not None else [])
    )
    estimated_total_bytes = sum(
        candidate.content_length or 0 for candidate in selected_candidates
    )
    warnings = list(extra_warnings or [])
    if not selected_candidates:
        warnings.append("no Sentinel-1 GRD candidates selected")
    for candidate in selected_candidates:
        warning = _manifest_warning_for_candidate(candidate)
        if warning and warning not in warnings:
            warnings.append(warning)
        if candidate.content_length is None:
            size_warning = "one or more selected products have unknown download size"
            if size_warning not in warnings:
                warnings.append(size_warning)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "collection": COLLECTION_ID,
                "bbox": bbox,
                "datetime": datetime_range,
                "reference_datetime": "2026-04-27T00:00:00Z",
                "accepted_product_types": list(ACCEPTED_PRODUCT_TYPES),
                "selection": {
                    "selected_product_ids": [
                        candidate.item_id for candidate in selected_candidates
                    ],
                    "estimated_total_bytes": estimated_total_bytes,
                    "estimated_total_human": _format_bytes(estimated_total_bytes),
                    "warnings": warnings,
                },
                "selected": (
                    candidate_to_manifest(
                        selected_candidates[0], download_statuses, out_dir=path.parent
                    )
                    if len(selected_candidates) == 1
                    else None
                ),
                "selected_candidates": [
                    candidate_to_manifest(candidate, download_statuses, out_dir=path.parent)
                    for candidate in selected_candidates
                ],
                "candidates": [
                    candidate_to_manifest(candidate, download_statuses, out_dir=path.parent)
                    for candidate in candidates
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def candidate_to_manifest(
    candidate: CandidateProduct | None,
    download_statuses: dict[str, str] | None = None,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any] | None:
    if candidate is None:
        return None
    statuses = download_statuses or {}
    payload = {
        "item_id": candidate.item_id,
        "safe_name": candidate.safe_name,
        "datetime": candidate.datetime,
        "platform": candidate.platform,
        "product_type": candidate.product_type,
        "instrument_mode": candidate.instrument_mode,
        "polarizations": list(candidate.polarizations),
        "relative_orbit": candidate.relative_orbit,
        "orbit_state": candidate.orbit_state,
        "absolute_orbit": candidate.absolute_orbit,
        "bbox": candidate.bbox,
        "overlap_bbox": candidate.overlap_bbox,
        "overlap_area": candidate.overlap_area,
        "overlap_percent": candidate.overlap_percent,
        "product_uuid": candidate.product_uuid,
        "product_href": candidate.product_href,
        "download_url": candidate.download_url,
        "download_url_mode": candidate.download_url_mode,
        "availability_status": candidate.availability_status,
        "availability_reason": candidate.availability_reason,
        "content_length": candidate.content_length,
        "content_length_human": _format_bytes(candidate.content_length),
        "s3_path": candidate.s3_path,
        "download_status": statuses.get(candidate.item_id, "pending"),
    }
    if out_dir is not None:
        payload["source_zip"] = product_output_path(out_dir, candidate).as_posix()
    return payload


def product_output_path(out_dir: Path, candidate: CandidateProduct) -> Path:
    return out_dir / candidate.item_id / candidate.zip_name


def is_complete_existing(candidate: CandidateProduct, output_path: Path) -> bool:
    return (
        output_path.exists()
        and candidate.content_length is not None
        and output_path.stat().st_size == candidate.content_length
    )


def download_product(
    candidate: CandidateProduct, *, token: str, output_path: Path, force: bool
) -> None:
    if not candidate.download_url:
        raise RuntimeError("selected product has no resolved download URL")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not force and is_complete_existing(candidate, output_path):
        print(f"skip existing {output_path} ({_format_bytes(candidate.content_length)})")
        return

    tmp = output_path.with_suffix(output_path.suffix + ".part")
    request = urllib.request.Request(
        candidate.download_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"download {candidate.item_id} -> {output_path}")
    with urllib.request.urlopen(request, timeout=180) as response, tmp.open("wb") as handle:
        copied = 0
        last_report = time.monotonic()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            copied += len(chunk)
            now = time.monotonic()
            if now - last_report >= 5:
                print(f"  {_format_bytes(copied)} / {_format_bytes(candidate.content_length)}")
                last_report = now
    tmp.replace(output_path)


def print_candidates(candidates: list[CandidateProduct]) -> None:
    if not candidates:
        print("no candidate Sentinel-1 GRD products found")
        return
    print("candidate Sentinel-1 GRD products:")
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"  [{index}] {candidate.item_id} "
            f"datetime={candidate.datetime} "
            f"platform={candidate.platform or 'unknown'} "
            f"type={candidate.product_type or 'unknown'} "
            f"pol={','.join(candidate.polarizations) or 'unknown'} "
            f"orbit={candidate.relative_orbit or 'unknown'} "
            f"state={candidate.orbit_state or 'unknown'} "
            f"overlap={candidate.overlap_percent:.2f}% "
            f"size={_format_bytes(candidate.content_length)} "
            f"availability={candidate.availability_status} "
            f"download_mode={candidate.download_url_mode or 'none'}"
        )


def _download_refusal_message(candidate: CandidateProduct) -> str | None:
    if not candidate.download_url:
        return "selected product has no resolved native SAFE ZIP download URL"
    if candidate.availability_status == "offline":
        return "selected product is not online in CDSE OData metadata"
    if (
        candidate.content_length is None or candidate.content_length >= LARGE_DOWNLOAD_BYTES
    ):
        return (
            f"refusing {_format_bytes(candidate.content_length)} download without --yes. "
            "Use --max-items/--item-id first to inspect candidates."
        )
    return None


def _resolve_out_dir(raw_out_dir: str) -> Path:
    out_dir = Path(raw_out_dir)
    return (REPO_ROOT / out_dir).resolve() if not out_dir.is_absolute() else out_dir


def main(argv: list[str] | None = None) -> int:
    load_root_env()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--bbox-preset", choices=sorted(BBOX_PRESETS), default="south-india-target")
    parser.add_argument("--datetime", default=None, help="STAC datetime interval")
    parser.add_argument("--max-items", type=int, default=50, help="maximum STAC items to inspect")
    parser.add_argument("--item-id", help="specific STAC item id to use")
    parser.add_argument(
        "--candidate-index", type=int, default=1, help="1-based ranked candidate index to use"
    )
    parser.add_argument(
        "--out-dir",
        default="data/raw/sentinel-1-grd",
        help="download root for complete native SAFE ZIP products",
    )
    parser.add_argument("--download", action="store_true", help="download the selected product ZIP")
    parser.add_argument(
        "--download-selected",
        action="store_true",
        help="download the dry-run selected product ZIP",
    )
    parser.add_argument("--yes", action="store_true", help="confirm large or unknown downloads")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="prompt in the terminal for CDSE username/password if env vars are absent",
    )
    args = parser.parse_args(argv)
    if args.download and args.download_selected:
        raise SystemExit("use only one of --download or --download-selected")

    bbox = parse_bbox(args.bbox, args.bbox_preset)
    datetime_range = args.datetime or default_datetime_range()
    out_dir = _resolve_out_dir(args.out_dir)
    coverage_manifest_path = out_dir / "coverage_manifest.json"

    items = search_grd_items(bbox=bbox, datetime_range=datetime_range, limit=args.max_items)
    candidates = collect_candidates(items=items, target_bbox=bbox)
    if args.item_id:
        candidates = [candidate for candidate in candidates if candidate.item_id == args.item_id]

    selected = select_candidate(candidates, args.candidate_index)
    selected_list = [selected] if selected is not None else []

    print(f"collection: {COLLECTION_ID}")
    print(f"bbox: {bbox}")
    print(f"datetime: {datetime_range}")
    print(f"accepted product types: {', '.join(ACCEPTED_PRODUCT_TYPES)}")
    print(f"items inspected: {len(items)}")
    print_candidates(candidates)

    if selected is None:
        write_manifest(
            coverage_manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=[],
            candidates=[],
        )
        print(f"manifest: {coverage_manifest_path}")
        return 2

    write_manifest(
        coverage_manifest_path,
        bbox=bbox,
        datetime_range=datetime_range,
        selected=selected_list,
        candidates=candidates,
    )
    print(f"selected: {selected.item_id}")

    if not args.download and not args.download_selected:
        print(f"manifest: {coverage_manifest_path}")
        print("dry run only. Add --download-selected --yes to download the selected SAFE ZIP.")
        return 0

    refusal = _download_refusal_message(selected)
    if refusal and not (
        args.yes
        and selected.download_url
        and selected.availability_status != "offline"
        and "without --yes" in refusal
    ):
        write_manifest(
            coverage_manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=selected_list,
            candidates=candidates,
            extra_warnings=[refusal],
        )
        print(f"manifest: {coverage_manifest_path}")
        print(refusal)
        return 2

    output_path = product_output_path(out_dir, selected)
    manifest_path = output_path.parent / "download_manifest.json"
    download_statuses: dict[str, str] = {}
    try:
        if not args.force and is_complete_existing(selected, output_path):
            print(f"skip existing {output_path} ({_format_bytes(selected.content_length)})")
            download_statuses[selected.item_id] = "skipped_existing"
        else:
            token = get_access_token(prompt_credentials=args.prompt_credentials)
            download_product(selected, token=token, output_path=output_path, force=args.force)
            download_statuses[selected.item_id] = "downloaded"
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        download_statuses[selected.item_id] = "failed"
        write_manifest(
            manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=selected_list,
            candidates=candidates,
            download_statuses=download_statuses,
            extra_warnings=["download failed; see sanitized console status"],
        )
        raise RuntimeError(f"failed downloading {selected.item_id}: {exc}") from exc

    write_manifest(
        manifest_path,
        bbox=bbox,
        datetime_range=datetime_range,
        selected=selected_list,
        candidates=candidates,
        download_statuses=download_statuses,
    )
    write_manifest(
        coverage_manifest_path,
        bbox=bbox,
        datetime_range=datetime_range,
        selected=selected_list,
        candidates=candidates,
        download_statuses=download_statuses,
    )
    print(f"manifest: {coverage_manifest_path}")
    print("download complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
