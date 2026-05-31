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
DEFAULT_DATETIME = "2025-07-01T00:00:00Z/2025-09-30T23:59:59Z"
LARGE_DOWNLOAD_BYTES = 1 * 1024 * 1024 * 1024
BBOX_PRESETS = {
    "south-india": [74.0, 8.0, 85.0, 16.0],
    "bengaluru-install": [76.8, 12.5, 77.9, 13.6],
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
    *, items: list[dict[str, Any]], max_cloud_cover: float | None
) -> list[CandidateProduct]:
    candidates: list[CandidateProduct] = []
    for item in items:
        properties = item.get("properties", {})
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
        candidates.append(
            CandidateProduct(
                item_id=str(item.get("id")),
                datetime=properties.get("datetime") if isinstance(properties, dict) else None,
                cloud_cover=cloud_cover_value,
                bbox=item.get("bbox") if isinstance(item.get("bbox"), list) else None,
                product_href=product_href,
                product_uuid=product_uuid,
                content_length=content_length if isinstance(content_length, int) else None,
                s3_path=s3_path if isinstance(s3_path, str) else None,
                available_assets=available_assets,
                missing_required_assets=missing,
            )
        )
    return sorted(candidates, key=lambda c: (c.missing_required_assets != (), c.cloud_cover or 9999))


def write_manifest(
    path: Path,
    *,
    bbox: list[float],
    datetime_range: str,
    selected: CandidateProduct | None,
    candidates: list[CandidateProduct],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "collection": COLLECTION_ID,
                "bbox": bbox,
                "datetime": datetime_range,
                "required_source_assets": list(REQUIRED_SOURCE_ASSETS),
                "recommended_metadata_assets": list(RECOMMENDED_METADATA_ASSETS),
                "selected": candidate_to_manifest(selected) if selected else None,
                "candidates": [candidate_to_manifest(candidate) for candidate in candidates],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def candidate_to_manifest(candidate: CandidateProduct | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "item_id": candidate.item_id,
        "safe_name": candidate.safe_name,
        "datetime": candidate.datetime,
        "cloud_cover": candidate.cloud_cover,
        "bbox": candidate.bbox,
        "product_uuid": candidate.product_uuid,
        "product_href": candidate.product_href,
        "content_length": candidate.content_length,
        "content_length_human": _format_bytes(candidate.content_length),
        "s3_path": candidate.s3_path,
        "missing_required_assets": list(candidate.missing_required_assets),
    }


def download_product(candidate: CandidateProduct, *, token: str, output_path: Path, force: bool) -> None:
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
    parser.add_argument("--datetime", default=DEFAULT_DATETIME, help="STAC datetime interval")
    parser.add_argument("--max-items", type=int, default=50, help="maximum STAC items to inspect")
    parser.add_argument("--max-cloud-cover", type=float, default=30.0)
    parser.add_argument("--item-id", help="specific STAC item id to download")
    parser.add_argument("--candidate-index", type=int, default=1, help="1-based candidate index to use")
    parser.add_argument(
        "--out-dir",
        default="data/raw/sentinel-2-l2a",
        help="download root for complete native SAFE ZIP products",
    )
    parser.add_argument("--download", action="store_true", help="download the selected product ZIP")
    parser.add_argument("--yes", action="store_true", help="confirm large downloads")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="prompt in the terminal for CDSE username/password if env vars are absent",
    )
    args = parser.parse_args(argv)

    bbox = parse_bbox(args.bbox, args.bbox_preset)
    out_dir = (
        (REPO_ROOT / args.out_dir).resolve()
        if not Path(args.out_dir).is_absolute()
        else Path(args.out_dir)
    )

    items = search_l2a_items(bbox=bbox, datetime_range=args.datetime, limit=args.max_items)
    candidates = collect_candidates(items=items, max_cloud_cover=args.max_cloud_cover)
    if args.item_id:
        candidates = [candidate for candidate in candidates if candidate.item_id == args.item_id]

    print(f"collection: {COLLECTION_ID}")
    print(f"bbox: {bbox}")
    print(f"datetime: {args.datetime}")
    print(f"required assets: {', '.join(REQUIRED_SOURCE_ASSETS)}")
    print(f"items inspected: {len(items)}")
    print_candidates(candidates)

    if not candidates:
        write_manifest(
            out_dir / "manifest.json",
            bbox=bbox,
            datetime_range=args.datetime,
            selected=None,
            candidates=[],
        )
        return 2
    if args.candidate_index < 1 or args.candidate_index > len(candidates):
        raise SystemExit(f"--candidate-index must be between 1 and {len(candidates)}")

    selected = candidates[args.candidate_index - 1]
    selected_dir = out_dir / selected.item_id
    output_path = selected_dir / selected.zip_name
    manifest_path = selected_dir / "download_manifest.json"
    write_manifest(
        manifest_path,
        bbox=bbox,
        datetime_range=args.datetime,
        selected=selected,
        candidates=candidates,
    )
    print(f"selected: {selected.item_id}")
    print(f"output: {output_path}")
    print(f"manifest: {manifest_path}")

    if selected.missing_required_assets:
        raise SystemExit(
            "selected product is missing required assets: "
            + ", ".join(selected.missing_required_assets)
        )

    if not args.download:
        print("dry run only. Add --download --yes to fetch the complete SAFE ZIP.")
        return 0

    if (selected.content_length is None or selected.content_length >= LARGE_DOWNLOAD_BYTES) and not args.yes:
        raise SystemExit(
            f"refusing {_format_bytes(selected.content_length)} download without --yes. "
            "Use --max-items/--max-cloud-cover/--item-id first to inspect candidates."
        )

    token = get_access_token(prompt_credentials=args.prompt_credentials)
    try:
        download_product(selected, token=token, output_path=output_path, force=args.force)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"failed downloading {selected.item_id}: HTTP {exc.code} {exc.reason}"
        ) from exc
    print("download complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
