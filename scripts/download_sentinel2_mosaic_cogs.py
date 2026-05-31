"""Search and download Copernicus Sentinel-2 Global Mosaic COG band assets.

This helper targets the Copernicus Data Space STAC collection
``sentinel-2-global-mosaics``. It is intended for large-area visual basemap source
imagery, not for per-scene raw Sentinel-2 product downloads.

Default mode is a dry run: it searches the STAC API, prints matching mosaic tiles,
and writes a manifest. Add ``--download`` to fetch the HTTPS COG assets.

Credentials are intentionally read only from environment variables or an optional
terminal prompt. Do not put Copernicus credentials in source files or chat logs.

Examples:

    # Inventory South India Q3 2025 mosaic tiles and estimated download size.
    uv run python scripts/download_sentinel2_mosaic_cogs.py --bbox-preset south-india

    # Download only the Bengaluru install footprint after setting env vars.
    # PowerShell:
    #   $env:CDSE_USERNAME="you@example.com"
    #   $env:CDSE_PASSWORD="..."
    uv run python scripts/download_sentinel2_mosaic_cogs.py \
        --bbox-preset bengaluru-install \
        --download --yes

    # Or use an already-created OAuth access token.
    # PowerShell:
    #   $env:CDSE_ACCESS_TOKEN="eyJ..."
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
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
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
COLLECTION_ID = "sentinel-2-global-mosaics"
REQUIRED_BANDS = ("B02", "B03", "B04", "B08")
DEFAULT_DATETIME = "2025-07-01T00:00:00Z/2025-09-30T23:59:59Z"
LARGE_DOWNLOAD_BYTES = 5 * 1024 * 1024 * 1024
BBOX_PRESETS = {
    # User-requested rough South India bbox: Tamil Nadu, Kerala, Karnataka,
    # Andhra Pradesh, Telangana, and Bengaluru.
    "south-india": [74.0, 8.0, 85.0, 16.0],
    # Akasha Wave 1 is one ~60 km install around Bengaluru; use this when the
    # goal is the actual field-detail demo instead of a regional basemap corpus.
    "bengaluru-install": [76.8, 12.5, 77.9, 13.6],
}


@dataclass(frozen=True)
class AssetDownload:
    item_id: str
    band: str
    href: str
    size: int | None
    output_path: Path


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


def search_items(*, bbox: list[float], datetime_range: str, limit: int) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "collections": [COLLECTION_ID],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": min(limit, 100),
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


def asset_https_href(asset: dict[str, Any]) -> str | None:
    alternate = asset.get("alternate")
    if isinstance(alternate, dict):
        https = alternate.get("https")
        if isinstance(https, dict) and isinstance(https.get("href"), str):
            return https["href"]
    href = asset.get("href")
    if isinstance(href, str) and href.startswith("https://"):
        return href
    return None


def collect_downloads(
    *, items: list[dict[str, Any]], bands: tuple[str, ...], out_dir: Path
) -> list[AssetDownload]:
    downloads: list[AssetDownload] = []
    for item in items:
        item_id = item["id"]
        assets = item.get("assets", {})
        for band in bands:
            asset = assets.get(band)
            if not isinstance(asset, dict):
                raise RuntimeError(f"{item_id} is missing required asset {band}")
            href = asset_https_href(asset)
            if href is None:
                raise RuntimeError(f"{item_id} asset {band} has no HTTPS download URL")
            size = asset.get("file:size") if isinstance(asset.get("file:size"), int) else None
            downloads.append(
                AssetDownload(
                    item_id=item_id,
                    band=band,
                    href=href,
                    size=size,
                    output_path=out_dir / item_id / f"{band}.tif",
                )
            )
    return downloads


def write_manifest(
    path: Path, *, bbox: list[float], datetime_range: str, items: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    compact_items = []
    for item in items:
        compact_items.append(
            {
                "id": item.get("id"),
                "collection": item.get("collection"),
                "bbox": item.get("bbox"),
                "datetime": item.get("properties", {}).get("datetime"),
                "assets": {
                    band: {
                        "href": asset_https_href(item.get("assets", {}).get(band, {})),
                        "size": item.get("assets", {}).get(band, {}).get("file:size"),
                    }
                    for band in REQUIRED_BANDS
                },
            }
        )
    path.write_text(
        json.dumps(
            {
                "collection": COLLECTION_ID,
                "bbox": bbox,
                "datetime": datetime_range,
                "items": compact_items,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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


def download_file(download: AssetDownload, *, token: str, force: bool = False) -> None:
    download.output_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        not force
        and download.output_path.exists()
        and download.size is not None
        and download.output_path.stat().st_size == download.size
    ):
        print(f"skip existing {download.output_path} ({_format_bytes(download.size)})")
        return

    tmp = download.output_path.with_suffix(download.output_path.suffix + ".part")
    request = urllib.request.Request(download.href, headers={"Authorization": f"Bearer {token}"})
    print(f"download {download.item_id} {download.band} -> {download.output_path}")
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
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
                print(f"  {_format_bytes(copied)} / {_format_bytes(download.size)}")
                last_report = now
    tmp.replace(download.output_path)


def parse_bbox(values: list[str] | None, preset: str | None) -> list[float]:
    if values is not None:
        if len(values) != 4:
            raise argparse.ArgumentTypeError(
                "--bbox requires four numbers: min_lon min_lat max_lon max_lat"
            )
        bbox = [float(value) for value in values]
    else:
        bbox = BBOX_PRESETS[preset or "south-india"]
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise argparse.ArgumentTypeError(f"invalid bbox: {bbox}")
    return bbox


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--bbox-preset", choices=sorted(BBOX_PRESETS), default="south-india")
    parser.add_argument("--datetime", default=DEFAULT_DATETIME, help="STAC datetime interval")
    parser.add_argument("--max-items", type=int, default=500, help="maximum STAC items to inspect")
    parser.add_argument(
        "--out-dir",
        default="data/cog/sentinel-2-global-mosaics",
        help="download root for per-item B02/B03/B04/B08 COGs",
    )
    parser.add_argument("--download", action="store_true", help="download the COG files")
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
    items = search_items(bbox=bbox, datetime_range=args.datetime, limit=args.max_items)
    downloads = collect_downloads(items=items, bands=REQUIRED_BANDS, out_dir=out_dir)
    total_size = sum(download.size or 0 for download in downloads)
    manifest = out_dir / "manifest.json"
    write_manifest(manifest, bbox=bbox, datetime_range=args.datetime, items=items)

    print(f"collection: {COLLECTION_ID}")
    print(f"bbox: {bbox}")
    print(f"datetime: {args.datetime}")
    print(f"items: {len(items)}")
    print(f"assets: {len(downloads)} ({', '.join(REQUIRED_BANDS)})")
    print(f"estimated size: {_format_bytes(total_size)}")
    print(f"manifest: {manifest}")
    for item in items[:20]:
        print(f"  {item['id']} bbox={item.get('bbox')}")
    if len(items) > 20:
        print(f"  ... {len(items) - 20} more items")

    if not args.download:
        print("dry run only. Add --download --yes to fetch files.")
        return 0
    if total_size >= LARGE_DOWNLOAD_BYTES and not args.yes:
        raise SystemExit(
            f"refusing {_format_bytes(total_size)} download without --yes. "
            "Use --bbox-preset bengaluru-install or --max-items first "
            "if you only need the demo area."
        )

    token = get_access_token(prompt_credentials=args.prompt_credentials)
    for download in downloads:
        try:
            download_file(download, token=token, force=args.force)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"failed downloading {download.item_id} {download.band}: "
                f"HTTP {exc.code} {exc.reason}"
            ) from exc
    print("download complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
