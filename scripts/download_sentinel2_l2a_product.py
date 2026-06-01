"""Search and download complete Copernicus Sentinel-2 L2A SAFE products.

This downloader targets the CDSE STAC collection ``sentinel-2-l2a`` and uses the
OData ``Product`` asset to download the complete native L2A product as a ZIP.

Why this route:
- It avoids the Sentinel-2 Global Mosaics collection, which only exposes a small
  visual/NIR subset.
- It avoids requiring separate CDSE S3 keys for the first Slice 2 data pull.
- The downloaded SAFE product contains the JP2 inputs needed to build Akasha's
  analytic COG and SCL COG.

Credentials are intentionally read only from environment variables or an optional
terminal prompt. Do not put Copernicus credentials in source files or chat logs.

Examples:

    # Dry-run: find candidate L2A products over the Bengaluru install footprint.
    uv run python scripts/download_sentinel2_l2a_product.py \
        --bbox-preset bengaluru-install

    # Download the best candidate after prompting for CDSE credentials.
    uv run python scripts/download_sentinel2_l2a_product.py \
        --bbox-preset bengaluru-install \
        --download --yes --prompt-credentials

    # Use environment variables instead of prompts.
    # PowerShell:
    #   $env:CDSE_USERNAME="you@example.com"
    #   $env:CDSE_PASSWORD="..."
    uv run python scripts/download_sentinel2_l2a_product.py \
        --bbox-preset bengaluru-install \
        --download --yes
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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STAC_API_URL = "https://stac.dataspace.copernicus.eu/v1"
ODATA_API_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
COLLECTION_ID = "sentinel-2-l2a"

# Akasha Slice 2 source inputs. The final analytic COG order is:
# [B04, B08, B05, B06, B07, B11, B12, B03, B02].
REQUIRED_SOURCE_ASSETS = (
    "B04_10m",
    "B08_10m",
    "B05_20m",
    "B06_20m",
    "B07_20m",
    "B11_20m",
    "B12_20m",
    "B03_10m",
    "B02_10m",
    "SCL_20m",
)
RECOMMENDED_METADATA_ASSETS = (
    "Product",
    "product_metadata",
    "granule_metadata",
    "safe_manifest",
)
LARGE_DOWNLOAD_BYTES = 1 * 1024 * 1024 * 1024
BBOX_PRESETS = {
    "south-india": [74.0, 8.0, 85.0, 16.0],
    "bengaluru-install": [76.8, 12.5, 77.9, 13.6],
    "south-india-target": [74.168701, 8.085101, 81.013184, 14.434701],
}


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


@dataclass(frozen=True)
class CandidateProduct:
    item_id: str
    datetime: str | None
    cloud_cover: float | None
    bbox: list[float] | None
    mgrs_tile: str | None
    grid_code: str | None
    overlap_bbox: list[float] | None
    overlap_area: float
    overlap_percent: float
    product_href: str
    product_uuid: str | None
    content_length: int | None
    s3_path: str | None
    available_assets: tuple[str, ...]
    missing_required_assets: tuple[str, ...]

    @property
    def safe_name(self) -> str:
        return self.item_id if self.item_id.endswith(".SAFE") else f"{self.item_id}.SAFE"

    @property
    def zip_name(self) -> str:
        return f"{self.safe_name}.zip"


def default_datetime_range(now: datetime | None = None) -> str:
    """Return a 90-day STAC datetime interval constrained to calendar year 2026."""
    current = now or datetime.now(UTC)
    current_date = current.date()
    year_start = datetime(2026, 1, 1, tzinfo=UTC).date()
    year_end = datetime(2026, 12, 31, tzinfo=UTC).date()

    if current_date < year_start:
        start_date = year_start
        end_date = datetime(2026, 3, 31, tzinfo=UTC).date()
    else:
        end_date = min(current_date, year_end)
        start_date = max(year_start, end_date - timedelta(days=89))

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
        bbox = BBOX_PRESETS[preset or "bengaluru-install"]
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


def _product_uuid_from_href(href: str) -> str | None:
    match = re.search(r"Products\(([^)]+)\)", href)
    return match.group(1) if match else None


def _asset_href(asset: dict[str, Any]) -> str | None:
    href = asset.get("href")
    return href if isinstance(href, str) else None


def _datetime_sort_value(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _candidate_rank(candidate: CandidateProduct) -> tuple[bool, bool, float, float, float]:
    return (
        candidate.missing_required_assets != (),
        candidate.overlap_area <= 0,
        -candidate.overlap_percent,
        candidate.cloud_cover if candidate.cloud_cover is not None else 9999.0,
        -_datetime_sort_value(candidate.datetime),
    )


def search_l2a_items(*, bbox: list[float], datetime_range: str, limit: int) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "collections": [COLLECTION_ID],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": min(limit, 100),
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        "fields": {
            "include": [
                "id",
                "collection",
                "bbox",
                "assets",
                "properties.datetime",
                "properties.eo:cloud_cover",
                "properties.grid:code",
                "properties.s2:mgrs_tile",
            ]
        },
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


def collect_candidates(
    *, items: list[dict[str, Any]], target_bbox: list[float], max_cloud_cover: float | None
) -> list[CandidateProduct]:
    candidates: list[CandidateProduct] = []
    target_area = bbox_area_degrees(target_bbox)
    for item in items:
        properties = item.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        cloud_cover = properties.get("eo:cloud_cover")
        if isinstance(cloud_cover, int | float):
            cloud_cover_value = float(cloud_cover)
        else:
            cloud_cover_value = None
        if (
            max_cloud_cover is not None
            and cloud_cover_value is not None
            and cloud_cover_value > max_cloud_cover
        ):
            continue

        assets = item.get("assets", {})
        if not isinstance(assets, dict):
            continue
        product_asset = assets.get("Product")
        if not isinstance(product_asset, dict):
            continue
        product_href = _asset_href(product_asset)
        if not product_href or not product_href.startswith("https://"):
            continue

        available_assets = tuple(sorted(assets))
        missing = tuple(asset for asset in REQUIRED_SOURCE_ASSETS if asset not in assets)
        product_uuid = _product_uuid_from_href(product_href)
        details = get_odata_product_details(product_uuid)
        content_length = details.get("ContentLength")
        s3_path = details.get("S3Path")
        item_bbox = item.get("bbox") if isinstance(item.get("bbox"), list) else None
        overlap_bbox = bbox_intersection(target_bbox, item_bbox) if item_bbox else None
        overlap_area = bbox_area_degrees(overlap_bbox) if overlap_bbox else 0.0
        overlap_percent = (overlap_area / target_area * 100.0) if target_area > 0 else 0.0
        mgrs_tile = properties.get("s2:mgrs_tile")
        grid_code = properties.get("grid:code")
        candidates.append(
            CandidateProduct(
                item_id=str(item.get("id")),
                datetime=properties.get("datetime"),
                cloud_cover=cloud_cover_value,
                bbox=item_bbox,
                mgrs_tile=mgrs_tile if isinstance(mgrs_tile, str) else None,
                grid_code=grid_code if isinstance(grid_code, str) else None,
                overlap_bbox=overlap_bbox,
                overlap_area=overlap_area,
                overlap_percent=overlap_percent,
                product_href=product_href,
                product_uuid=product_uuid,
                content_length=content_length if isinstance(content_length, int) else None,
                s3_path=s3_path if isinstance(s3_path, str) else None,
                available_assets=available_assets,
                missing_required_assets=missing,
            )
        )
    return sorted(candidates, key=_candidate_rank)


def select_coverage_candidates(candidates: list[CandidateProduct]) -> list[CandidateProduct]:
    grouped: dict[str, list[CandidateProduct]] = {}
    for candidate in candidates:
        if candidate.overlap_area <= 0:
            continue
        group_key = candidate.mgrs_tile or f"item:{candidate.item_id}"
        grouped.setdefault(group_key, []).append(candidate)
    selected = [sorted(group, key=_candidate_rank)[0] for group in grouped.values()]
    return sorted(selected, key=_candidate_rank)


def write_manifest(
    path: Path,
    *,
    bbox: list[float],
    datetime_range: str,
    selected: CandidateProduct | list[CandidateProduct] | None,
    candidates: list[CandidateProduct],
    download_statuses: dict[str, str] | None = None,
) -> None:
    selected_candidates = (
        selected
        if isinstance(selected, list)
        else ([selected] if selected is not None else [])
    )
    statuses = download_statuses or {}
    estimated_total_bytes = sum(
        candidate.content_length or 0 for candidate in selected_candidates
    )
    warnings: list[str] = []
    if any(candidate.missing_required_assets for candidate in selected_candidates):
        warnings.append("one or more selected products are missing required source assets")
    if any(candidate.content_length is None for candidate in selected_candidates):
        warnings.append("one or more selected products have unknown download size")
    if not selected_candidates:
        warnings.append("no coverage candidates selected")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "collection": COLLECTION_ID,
                "bbox": bbox,
                "datetime": datetime_range,
                "required_source_assets": list(REQUIRED_SOURCE_ASSETS),
                "recommended_metadata_assets": list(RECOMMENDED_METADATA_ASSETS),
                "selection": {
                    "selected_product_ids": [
                        candidate.item_id for candidate in selected_candidates
                    ],
                    "selected_mgrs_tiles": [
                        candidate.mgrs_tile
                        for candidate in selected_candidates
                        if candidate.mgrs_tile
                    ],
                    "estimated_total_bytes": estimated_total_bytes,
                    "estimated_total_human": _format_bytes(estimated_total_bytes),
                    "warnings": warnings,
                },
                "selected": (
                    candidate_to_manifest(selected_candidates[0], statuses)
                    if len(selected_candidates) == 1
                    else None
                ),
                "selected_candidates": [
                    candidate_to_manifest(candidate, statuses)
                    for candidate in selected_candidates
                ],
                "candidates": [
                    candidate_to_manifest(candidate, statuses) for candidate in candidates
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )



def candidate_to_manifest(
    candidate: CandidateProduct | None, download_statuses: dict[str, str] | None = None
) -> dict[str, Any] | None:
    if candidate is None:
        return None
    statuses = download_statuses or {}
    return {
        "item_id": candidate.item_id,
        "safe_name": candidate.safe_name,
        "datetime": candidate.datetime,
        "cloud_cover": candidate.cloud_cover,
        "bbox": candidate.bbox,
        "mgrs_tile": candidate.mgrs_tile,
        "grid_code": candidate.grid_code,
        "overlap_bbox": candidate.overlap_bbox,
        "overlap_area": candidate.overlap_area,
        "overlap_percent": candidate.overlap_percent,
        "product_uuid": candidate.product_uuid,
        "product_href": candidate.product_href,
        "content_length": candidate.content_length,
        "content_length_human": _format_bytes(candidate.content_length),
        "s3_path": candidate.s3_path,
        "missing_required_assets": list(candidate.missing_required_assets),
        "download_status": statuses.get(candidate.item_id, "pending"),
    }


def download_product(
    candidate: CandidateProduct, *, token: str, output_path: Path, force: bool
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        not force
        and output_path.exists()
        and candidate.content_length is not None
        and output_path.stat().st_size == candidate.content_length
    ):
        print(f"skip existing {output_path} ({_format_bytes(candidate.content_length)})")
        return

    tmp = output_path.with_suffix(output_path.suffix + ".part")
    request = urllib.request.Request(
        candidate.product_href,
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


def product_output_path(out_dir: Path, candidate: CandidateProduct) -> Path:
    return out_dir / candidate.item_id / candidate.zip_name


def is_complete_existing(candidate: CandidateProduct, output_path: Path) -> bool:
    return (
        output_path.exists()
        and candidate.content_length is not None
        and output_path.stat().st_size == candidate.content_length
    )


def print_candidates(candidates: list[CandidateProduct]) -> None:
    if not candidates:
        print("no candidate L2A products found")
        return
    print("candidate L2A products:")
    for index, candidate in enumerate(candidates, start=1):
        missing = ",".join(candidate.missing_required_assets) or "none"
        print(
            f"  [{index}] {candidate.item_id} "
            f"datetime={candidate.datetime} "
            f"cloud={candidate.cloud_cover} "
            f"mgrs={candidate.mgrs_tile or 'unknown'} "
            f"overlap={candidate.overlap_percent:.2f}% "
            f"size={_format_bytes(candidate.content_length)} "
            f"missing={missing}"
        )
        if candidate.s3_path:
            print(f"      s3={candidate.s3_path}")


def main(argv: list[str] | None = None) -> int:
    load_root_env()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--bbox-preset", choices=sorted(BBOX_PRESETS), default="bengaluru-install")
    parser.add_argument("--datetime", default=None, help="STAC datetime interval")
    parser.add_argument("--max-items", type=int, default=50, help="maximum STAC items to inspect")
    parser.add_argument("--max-cloud-cover", type=float, default=30.0)
    parser.add_argument("--item-id", help="specific STAC item id to download")
    parser.add_argument(
        "--candidate-index", type=int, default=1, help="1-based candidate index to use"
    )
    parser.add_argument(
        "--out-dir",
        default="data/raw/sentinel-2-l2a",
        help="download root for complete native SAFE ZIP products",
    )
    parser.add_argument("--download", action="store_true", help="download the selected product ZIP")
    parser.add_argument(
        "--download-selected",
        action="store_true",
        help="download all coverage-selected product ZIPs serially",
    )
    parser.add_argument("--yes", action="store_true", help="confirm large downloads")
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
    out_dir = (
        (REPO_ROOT / args.out_dir).resolve()
        if not Path(args.out_dir).is_absolute()
        else Path(args.out_dir)
    )
    coverage_manifest_path = out_dir / "coverage_manifest.json"

    items = search_l2a_items(bbox=bbox, datetime_range=datetime_range, limit=args.max_items)
    candidates = collect_candidates(
        items=items, target_bbox=bbox, max_cloud_cover=args.max_cloud_cover
    )
    if args.item_id:
        candidates = [candidate for candidate in candidates if candidate.item_id == args.item_id]
    coverage_selected = select_coverage_candidates(candidates)

    print(f"collection: {COLLECTION_ID}")
    print(f"bbox: {bbox}")
    print(f"datetime: {datetime_range}")
    print(f"required assets: {', '.join(REQUIRED_SOURCE_ASSETS)}")
    print(f"items inspected: {len(items)}")
    print_candidates(candidates)

    if not candidates:
        write_manifest(
            coverage_manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=[],
            candidates=[],
        )
        return 2
    if args.candidate_index < 1 or args.candidate_index > len(candidates):
        raise SystemExit(f"--candidate-index must be between 1 and {len(candidates)}")

    selected = candidates[args.candidate_index - 1]
    output_path = product_output_path(out_dir, selected)
    manifest_path = output_path.parent / "download_manifest.json"
    manifest_selected: CandidateProduct | list[CandidateProduct]
    manifest_selected = selected if args.download else coverage_selected
    write_manifest(
        manifest_path if args.download else coverage_manifest_path,
        bbox=bbox,
        datetime_range=datetime_range,
        selected=manifest_selected,
        candidates=candidates,
    )
    print(
        "coverage selected: "
        + (", ".join(candidate.item_id for candidate in coverage_selected) or "none")
    )

    if not args.download and not args.download_selected:
        print(f"manifest: {coverage_manifest_path}")
        print("dry run only. Add --download-selected --yes for coverage batch downloads.")
        print("Use --download --yes with --candidate-index for the legacy single-product path.")
        return 0

    download_statuses: dict[str, str] = {}
    token: str | None = None

    if args.download:
        print(f"selected: {selected.item_id}")
        print(f"output: {output_path}")
        print(f"manifest: {manifest_path}")
        if selected.missing_required_assets:
            raise SystemExit(
                "selected product is missing required assets: "
                + ", ".join(selected.missing_required_assets)
            )
        if (
            selected.content_length is None or selected.content_length >= LARGE_DOWNLOAD_BYTES
        ) and not args.yes:
            raise SystemExit(
                f"refusing {_format_bytes(selected.content_length)} download without --yes. "
                "Use --max-items/--max-cloud-cover/--item-id first to inspect candidates."
            )
        if not args.force and is_complete_existing(selected, output_path):
            print(f"skip existing {output_path} ({_format_bytes(selected.content_length)})")
            download_statuses[selected.item_id] = "skipped_existing"
        else:
            try:
                token = token or get_access_token(prompt_credentials=args.prompt_credentials)
                download_product(selected, token=token, output_path=output_path, force=args.force)
                download_statuses[selected.item_id] = "downloaded"
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                download_statuses[selected.item_id] = "failed"
                write_manifest(
                    manifest_path,
                    bbox=bbox,
                    datetime_range=datetime_range,
                    selected=selected,
                    candidates=candidates,
                    download_statuses=download_statuses,
                )
                raise RuntimeError(f"failed downloading {selected.item_id}: {exc}") from exc
        write_manifest(
            manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=selected,
            candidates=candidates,
            download_statuses=download_statuses,
        )
        print("download complete")
        return 0

    if not coverage_selected:
        write_manifest(
            coverage_manifest_path,
            bbox=bbox,
            datetime_range=datetime_range,
            selected=[],
            candidates=candidates,
        )
        print(f"manifest: {coverage_manifest_path}")
        print("no positive-overlap coverage candidates selected")
        return 2

    failures: list[str] = []
    for candidate in coverage_selected:
        output_path = product_output_path(out_dir, candidate)
        if candidate.missing_required_assets:
            print(
                f"skip {candidate.item_id}: missing required assets "
                + ", ".join(candidate.missing_required_assets)
            )
            download_statuses[candidate.item_id] = "failed"
            failures.append(candidate.item_id)
            continue
        if (
            candidate.content_length is None or candidate.content_length >= LARGE_DOWNLOAD_BYTES
        ) and not args.yes:
            raise SystemExit(
                f"refusing {_format_bytes(candidate.content_length)} download without --yes. "
                "Use --max-items/--max-cloud-cover/--item-id first to inspect candidates."
            )
        if not args.force and is_complete_existing(candidate, output_path):
            print(f"skip existing {output_path} ({_format_bytes(candidate.content_length)})")
            download_statuses[candidate.item_id] = "skipped_existing"
            continue
        try:
            token = token or get_access_token(prompt_credentials=args.prompt_credentials)
            download_product(candidate, token=token, output_path=output_path, force=args.force)
            download_statuses[candidate.item_id] = "downloaded"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f"failed downloading {candidate.item_id}: {exc}")
            download_statuses[candidate.item_id] = "failed"
            failures.append(candidate.item_id)
    write_manifest(
        coverage_manifest_path,
        bbox=bbox,
        datetime_range=datetime_range,
        selected=coverage_selected,
        candidates=candidates,
        download_statuses=download_statuses,
    )
    print(f"manifest: {coverage_manifest_path}")
    if failures:
        print(f"download completed with failures: {', '.join(failures)}")
        return 1
    print("download complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
