from __future__ import annotations

import importlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

downloader = importlib.import_module("scripts.download_sentinel1_grd_product")


def stac_item(
    item_id: str,
    *,
    acquired: str = "2026-04-27T00:00:00Z",
    bbox: list[float] | None = None,
    polarizations: list[str] | None = None,
    product_type: str = "IW_GRDH_1S",
    instrument_mode: str = "IW",
    href: str = (
        "https://catalogue.dataspace.copernicus.eu/odata/v1/"
        "Products(00000000-0000-0000-0000-000000000001)/$value"
    ),
) -> dict[str, Any]:
    return {
        "id": item_id,
        "bbox": bbox or [74.0, 8.0, 80.0, 14.0],
        "properties": {
            "datetime": acquired,
            "platform": "sentinel-1a",
            "product:type": product_type,
            "sar:instrument_mode": instrument_mode,
            "sar:polarizations": polarizations or ["VV", "VH"],
            "sat:relative_orbit": 42,
            "sat:orbit_state": "ascending",
            "sat:absolute_orbit": 123456,
        },
        "assets": {"Product": {"href": href}},
    }


def test_constants_and_default_datetime_range() -> None:
    assert downloader.COLLECTION_ID == "sentinel-1-grd"
    assert downloader.BBOX_PRESETS["south-india-target"] == [
        74.168701,
        8.085101,
        81.013184,
        14.434701,
    ]
    assert (
        downloader.default_datetime_range(date(2026, 4, 27), 7)
        == "2026-04-20T00:00:00Z/2026-05-04T23:59:59Z"
    )


def test_bbox_helpers() -> None:
    assert downloader.bbox_intersection([0, 0, 2, 2], [1, 1, 3, 3]) == [1, 1, 2, 2]
    assert downloader.bbox_intersection([0, 0, 1, 1], [1, 0, 2, 1]) is None
    assert downloader.bbox_area_degrees([0, 0, 2, 3]) == pytest.approx(6.0)
    assert downloader.bbox_area_degrees([2, 3, 0, 0]) == pytest.approx(0.0)
    assert downloader.overlap_percent([0, 0, 2, 2], [1, 1, 3, 3]) == pytest.approx(25.0)


def test_search_uses_sentinel1_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload: dict[str, Any] = {}

    def fake_json_request(
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        captured_payload.update(payload or {})
        return {"features": [], "links": []}

    monkeypatch.setattr(downloader, "_json_request", fake_json_request)

    result = downloader.search_grd_items(
        bbox=downloader.BBOX_PRESETS["south-india-target"],
        datetime_range="2026-04-20T00:00:00Z/2026-05-04T23:59:59Z",
        limit=10,
    )

    assert result == []
    assert captured_payload["collections"] == ["sentinel-1-grd"]
    assert captured_payload["fields"]["include"] == downloader.STAC_SEARCH_FIELDS
    assert "properties.product:type" in captured_payload["fields"]["include"]
    assert "properties.sat:absolute_orbit" in captured_payload["fields"]["include"]


def test_collect_candidates_filters_and_ranks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        downloader,
        "get_odata_product_details",
        lambda product_uuid: {
            "ContentLength": 2048,
            "S3Path": "s3://example/product",
            "Online": True,
        },
    )

    candidates = downloader.collect_candidates(
        target_bbox=[0.0, 0.0, 10.0, 10.0],
        items=[
            stac_item(
                "single-pol-closer",
                acquired="2026-04-27T00:00:00Z",
                bbox=[0.0, 0.0, 10.0, 10.0],
                polarizations=["VV"],
            ),
            stac_item(
                "dual-pol-farther",
                acquired="2026-04-20T00:00:00Z",
                bbox=[0.0, 0.0, 1.0, 1.0],
                polarizations=["VV", "VH"],
            ),
            stac_item(
                "zero-overlap",
                acquired="2026-04-27T00:00:00Z",
                bbox=[20.0, 20.0, 21.0, 21.0],
                polarizations=["VV", "VH"],
            ),
            stac_item("bad-mode", instrument_mode="EW"),
            stac_item("bad-type", product_type="IW_GRDM_1S"),
            stac_item("bad-pol", polarizations=["VH"]),
        ],
    )

    assert [candidate.item_id for candidate in candidates] == [
        "dual-pol-farther",
        "single-pol-closer",
        "zero-overlap",
    ]
    assert candidates[0].download_url == (
        "https://download.dataspace.copernicus.eu/odata/v1/"
        "Products(00000000-0000-0000-0000-000000000001)/$value"
    )
    assert candidates[0].download_url_mode == "cdse_odata_value"
    assert candidates[0].availability_status == "online"


def test_default_main_writes_manifest_without_credentials_or_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_called = False
    download_called = False

    def fail_token(*args: object, **kwargs: object) -> str:
        nonlocal token_called
        token_called = True
        raise AssertionError("credentials must not be requested during dry-run")

    def fail_download(*args: object, **kwargs: object) -> None:
        nonlocal download_called
        download_called = True
        raise AssertionError("download_product must not be called during dry-run")

    monkeypatch.setattr(
        downloader, "search_grd_items", lambda **kwargs: [stac_item("s1-best.SAFE")]
    )
    monkeypatch.setattr(
        downloader,
        "get_odata_product_details",
        lambda product_uuid: {"ContentLength": 4096, "Online": True},
    )
    monkeypatch.setattr(downloader, "get_access_token", fail_token)
    monkeypatch.setattr(downloader, "download_product", fail_download)

    result = downloader.main(["--out-dir", str(tmp_path), "--max-items", "1"])

    manifest = json.loads((tmp_path / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert result == 0
    assert token_called is False
    assert download_called is False
    assert manifest["collection"] == "sentinel-1-grd"
    assert manifest["selection"]["selected_product_ids"] == ["s1-best.SAFE"]
    assert manifest["selected"]["source_zip"] == (
        tmp_path / "s1-best.SAFE" / "s1-best.SAFE.zip"
    ).as_posix()
    assert manifest["selected"]["download_status"] == "pending"
    assert manifest["selected"]["availability_status"] == "online"


def test_download_selected_exits_safely_without_download_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_url_item = stac_item("s1-no-url")
    no_url_item["assets"] = {}
    token_called = False

    def fail_token(*args: object, **kwargs: object) -> str:
        nonlocal token_called
        token_called = True
        raise AssertionError("credentials must not be requested without a download URL")

    monkeypatch.setattr(downloader, "search_grd_items", lambda **kwargs: [no_url_item])
    monkeypatch.setattr(downloader, "get_odata_product_details", lambda product_uuid: {})
    monkeypatch.setattr(downloader, "get_access_token", fail_token)

    result = downloader.main(["--out-dir", str(tmp_path), "--download-selected", "--yes"])

    manifest = json.loads((tmp_path / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert result == 2
    assert token_called is False
    assert manifest["selected"]["availability_status"] == "missing_download_url"
    assert "selected product has no resolved native SAFE ZIP download URL" in (
        manifest["selection"]["warnings"]
    )
