from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

downloader = importlib.import_module("scripts.download_sentinel2_l2a_product")


def make_candidate(
    item_id: str,
    *,
    mgrs_tile: str | None = "43PGP",
    overlap_area: float = 1.0,
    overlap_percent: float = 10.0,
    cloud_cover: float | None = 10.0,
    acquired: str | None = "2026-05-01T00:00:00Z",
    missing_required_assets: tuple[str, ...] = (),
) -> downloader.CandidateProduct:
    return downloader.CandidateProduct(
        item_id=item_id,
        datetime=acquired,
        cloud_cover=cloud_cover,
        bbox=[0.0, 0.0, 1.0, 1.0],
        mgrs_tile=mgrs_tile,
        grid_code=f"MGRS-{mgrs_tile}" if mgrs_tile else None,
        overlap_bbox=[0.0, 0.0, 1.0, 1.0] if overlap_area > 0 else None,
        overlap_area=overlap_area,
        overlap_percent=overlap_percent,
        product_href=f"https://example.invalid/Products({item_id})/$value",
        product_uuid=item_id,
        content_length=1024,
        s3_path=None,
        available_assets=downloader.REQUIRED_SOURCE_ASSETS,
        missing_required_assets=missing_required_assets,
    )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2025, 12, 15, tzinfo=UTC),
            "2026-01-01T00:00:00Z/2026-03-31T23:59:59Z",
        ),
        (
            datetime(2026, 1, 15, tzinfo=UTC),
            "2026-01-01T00:00:00Z/2026-01-15T23:59:59Z",
        ),
        (
            datetime(2026, 5, 31, 12, 30, tzinfo=UTC),
            "2026-03-03T00:00:00Z/2026-05-31T23:59:59Z",
        ),
        (
            datetime(2027, 1, 10, tzinfo=UTC),
            "2026-10-03T00:00:00Z/2026-12-31T23:59:59Z",
        ),
    ],
)
def test_default_datetime_range_is_constrained_to_2026(now: datetime, expected: str) -> None:
    assert downloader.default_datetime_range(now) == expected


def test_bbox_intersection_requires_positive_area() -> None:
    assert downloader.bbox_intersection([0, 0, 2, 2], [1, 1, 3, 3]) == [1, 1, 2, 2]
    assert downloader.bbox_intersection([0, 0, 1, 1], [1, 0, 2, 1]) is None
    assert downloader.bbox_intersection([0, 0, 1, 1], [2, 2, 3, 3]) is None


def test_bbox_area_degrees() -> None:
    assert downloader.bbox_area_degrees([0, 0, 2, 3]) == pytest.approx(6.0)
    assert downloader.bbox_area_degrees([2, 3, 0, 0]) == pytest.approx(0.0)


def test_select_coverage_candidates_groups_by_mgrs_and_ranks_best() -> None:
    selected = downloader.select_coverage_candidates(
        [
            make_candidate("older-cloudy", overlap_percent=30, cloud_cover=30),
            make_candidate("best-overlap", overlap_percent=60, cloud_cover=90),
            make_candidate("zero-overlap", mgrs_tile="44PKA", overlap_area=0, overlap_percent=0),
            make_candidate(
                "missing-assets",
                mgrs_tile="44PKA",
                missing_required_assets=("B04_10m",),
            ),
            make_candidate("complete-tile", mgrs_tile="44PKA", overlap_percent=20, cloud_cover=5),
            make_candidate("untiled-a", mgrs_tile=None, overlap_percent=5),
            make_candidate("untiled-b", mgrs_tile=None, overlap_percent=4),
        ]
    )

    assert [candidate.item_id for candidate in selected] == [
        "best-overlap",
        "complete-tile",
        "untiled-a",
        "untiled-b",
    ]


def test_default_main_writes_manifest_without_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_item = {
        "id": "S2A_MSIL2A_20260501T000000_N0511_R000_T43PGP_20260501T000000",
        "bbox": [76.0, 12.0, 78.0, 14.0],
        "properties": {
            "datetime": "2026-05-01T00:00:00Z",
            "eo:cloud_cover": 4.0,
            "grid:code": "MGRS-43PGP",
            "s2:mgrs_tile": "43PGP",
        },
        "assets": {
            "Product": {
                "href": "https://example.invalid/Products(00000000-0000-0000-0000-000000000001)/$value"
            },
            **{
                asset: {"href": f"https://example.invalid/{asset}"}
                for asset in downloader.REQUIRED_SOURCE_ASSETS
            },
        },
    }
    download_called = False

    def fail_download(*args: object, **kwargs: object) -> None:
        nonlocal download_called
        download_called = True
        raise AssertionError("download_product must not be called during dry-run")

    monkeypatch.setattr(downloader, "search_l2a_items", lambda **kwargs: [fake_item])
    monkeypatch.setattr(
        downloader,
        "get_odata_product_details",
        lambda product_uuid: {"ContentLength": 2048, "S3Path": "s3://example/product"},
    )
    monkeypatch.setattr(downloader, "download_product", fail_download)
    monkeypatch.setattr(
        downloader,
        "get_access_token",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("token not needed")),
    )

    result = downloader.main(
        [
            "--bbox-preset",
            "south-india-target",
            "--datetime",
            "2026-05-01T00:00:00Z/2026-05-31T23:59:59Z",
            "--out-dir",
            str(tmp_path),
            "--max-items",
            "1",
        ]
    )

    manifest = json.loads((tmp_path / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert result == 0
    assert download_called is False
    assert manifest["selection"]["selected_product_ids"] == [fake_item["id"]]
    assert manifest["selected_candidates"][0]["mgrs_tile"] == "43PGP"
    assert manifest["selected_candidates"][0]["download_status"] == "pending"
