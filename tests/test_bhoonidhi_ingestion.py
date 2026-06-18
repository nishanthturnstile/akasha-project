from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
import urllib.error
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import bhoonidhi, catalog, composite, config, storage, sync  # noqa: E402

WORKER_PATH = INGESTION_ROOT / "worker.py"
spec = importlib.util.spec_from_file_location("akasha_worker_for_bhoonidhi_tests", WORKER_PATH)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, _size: int | None = None) -> bytes:
        if _size is None:
            payload, self.payload = self.payload, b""
            return payload
        payload, self.payload = self.payload[:_size], self.payload[_size:]
        return payload


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, req, timeout=0):
        self.requests.append(req)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def http_error(code: int, body: bytes = b'{"Description":"retry"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://bhoonidhi-api.nrsc.gov.in/data/search",
        code=code,
        msg="error",
        hdrs={},
        fp=io.BytesIO(body),
    )


def json_response(payload: dict) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"))


def sqlite_row(path: Path, query: str) -> tuple:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(query).fetchone()
    finally:
        conn.close()
    assert row is not None
    return tuple(row)


def _write_test_aoi(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"id": "bangalore-60km", "name": "Bangalore"},
                "bbox": [77.0, 12.0, 78.0, 13.0],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [77.0, 12.0],
                            [78.0, 12.0],
                            [78.0, 13.0],
                            [77.0, 13.0],
                            [77.0, 12.0],
                        ]
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_source_collection_supports_awifs_phase5_source():
    assert (
        bhoonidhi.source_collection("resourcesat-2a-awifs-boa")
        == bhoonidhi.RESOURCESAT_AWIFS_BHOONIDHI_COLLECTION
    )


def test_source_collection_supports_liss4_phase_a_source():
    assert (
        bhoonidhi.source_collection("resourcesat-2a-liss4-mx70-l2")
        == "ResourceSat-2A_LISS4-MX70_L2"
    )


def test_resourcesat_guards_include_liss4_without_changing_worker_defaults():
    parser = worker.build_parser()
    sync_args = parser.parse_args(["bhoonidhi-sync"])
    composite_args = parser.parse_args(
        ["build-composite", "--window-start", "2026-03-01", "--window-end", "2026-03-31"]
    )

    assert sync_args.source == "resourcesat-2a-liss3-boa"
    assert composite_args.source == "resourcesat-2a-liss3-boa"
    assert "resourcesat-2a-liss4-mx70-l2" in config.RESOURCESAT_BOA_COLLECTION_IDS


def test_catalog_emits_three_band_liss4_resourcesat_item():
    manifest = {
        "source_id": "resourcesat-2a-liss4-mx70-l2",
        "collection": "ResourceSat-2A_LISS4-MX70_L2",
        "product_id": "LISS4_PRODUCT",
        "platform": "resourcesat-2a",
        "product_level": "BOA",
        "acquisition_datetime": "2026-03-19T00:00:00Z",
        "path": "99",
        "row": "65",
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[77.0, 12.0], [78.0, 12.0], [78.0, 13.0], [77.0, 13.0], [77.0, 12.0]]],
        },
        "outputs": {
            "analytic": {
                "path": "analytic.tif",
                "band_count": 3,
                "dtype": "uint16",
                "nodata": 0,
                "resolution": [5.8, 5.8],
                "crs": "EPSG:32643",
                "width": 2,
                "height": 2,
            },
            "mask": {
                "path": "mask.tif",
                "band_count": 1,
                "dtype": "uint8",
                "nodata": 0,
                "resolution": [5.8, 5.8],
                "crs": "EPSG:32643",
                "width": 2,
                "height": 2,
            },
        },
        "properties": {"akasha:metrics_provisional": True},
    }

    item = catalog.build_stac_item_from_prepare_manifest(manifest)

    assert item["collection"] == "resourcesat-2a-liss4-mx70-l2"
    assert item["properties"]["instruments"] == ["liss-4"]
    assert item["properties"]["gsd"] == 5.8
    assert item["properties"]["akasha:band_role_mapping"] == {
        "GREEN": "BAND2",
        "RED": "BAND3",
        "NIR": "BAND4",
    }
    assert [band["name"] for band in item["assets"]["analytic"]["eo:bands"]] == [
        "BAND2",
        "BAND3",
        "BAND4",
    ]
    assert len(item["assets"]["analytic"]["raster:bands"]) == 3
    assert {
        band["spatial_resolution"] for band in item["assets"]["analytic"]["raster:bands"]
    } == {5.8}


def test_source_collection_supports_eos06_phase5_context_source():
    assert (
        bhoonidhi.source_collection("eos-06-ocm-lac-ndvi-8day-360m")
        == bhoonidhi.EOS06_CONTEXT_BHOONIDHI_COLLECTION
    )


def test_source_collection_supports_phase6_sar_sources():
    assert (
        bhoonidhi.source_collection("eos-04-sar-mrs-l2b")
        == bhoonidhi.EOS04_SAR_BHOONIDHI_COLLECTION
    )
    assert (
        bhoonidhi.source_collection("nisar-ssar-beta-gcov")
        == bhoonidhi.NISAR_GCOV_BHOONIDHI_COLLECTION
    )


def test_cartosat3_has_no_unvalidated_bhoonidhi_collection_mapping():
    with pytest.raises(ValueError, match="unsupported Bhoonidhi source"):
        bhoonidhi.source_collection("cartosat-3-gated")


def test_composite_grid_crs_derives_utm_zone_when_aoi_has_no_crs_metadata():
    chennai_aoi = {
        "type": "Feature",
        "properties": {"id": "chennai-60km"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [79.7, 12.5],
                    [80.8, 12.5],
                    [80.8, 13.6],
                    [79.7, 13.6],
                    [79.7, 12.5],
                ]
            ],
        },
    }

    assert composite.aoi_composite_grid_crs(chennai_aoi) == "EPSG:32644"


def test_composite_grid_crs_prefers_aoi_metadata_over_derived_zone():
    aoi = {
        "type": "Feature",
        "properties": {"id": "custom-aoi", "compositeGridCrs": "EPSG:32645"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [79.7, 12.5],
                    [80.8, 12.5],
                    [80.8, 13.6],
                    [79.7, 13.6],
                    [79.7, 12.5],
                ]
            ],
        },
    }

    assert composite.aoi_composite_grid_crs(aoi) == "EPSG:32645"


def test_client_reuses_token_and_retries_search_429():
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            http_error(429),
            json_response({"features": [{"id": "product-1", "properties": {"Online": "Y"}}]}),
        ]
    )
    sleeps: list[float] = []
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        sleep=sleeps.append,
        now=lambda: 1000.0,
        max_retries=1,
    )

    items = client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-01-01T00:00:00Z/2026-02-01T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    assert [item["id"] for item in items] == ["product-1"]
    assert sleeps == [10.0]
    assert len([req for req in opener.requests if req.full_url.endswith("/auth/token")]) == 1
    assert opener.requests[-1].headers["Authorization"] == "Bearer token-a"


def test_client_treats_search_no_results_404_as_empty():
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            http_error(
                404,
                json.dumps(
                    {
                        "ErrorCode": "404",
                        "Description": "NO RESULTS FOUND",
                        "Action": "No results found. Please modify the inputs and try again.",
                    }
                ).encode("utf-8"),
            ),
        ]
    )
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        now=lambda: 1000.0,
    )

    items = client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-05-03T00:00:00Z/2026-06-16T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    assert items == []
    assert len(opener.requests) == 2


def test_client_reauthenticates_and_retries_search_401():
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            http_error(401),
            json_response(
                {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "expires_in": 1200,
                }
            ),
            json_response({"features": [{"id": "product-2", "properties": {"Online": "Y"}}]}),
        ]
    )
    sleeps: list[float] = []
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        sleep=sleeps.append,
        now=lambda: 1000.0,
        max_retries=1,
    )

    items = client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-01-01T00:00:00Z/2026-02-01T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    assert [item["id"] for item in items] == ["product-2"]
    assert sleeps == [2.0]
    auth_requests = [req for req in opener.requests if req.full_url.endswith("/auth/token")]
    search_requests = [req for req in opener.requests if req.full_url.endswith("/data/search")]
    assert len(auth_requests) == 2
    assert [req.headers["Authorization"] for req in search_requests] == [
        "Bearer token-a",
        "Bearer token-b",
    ]


def test_client_logs_out_stale_session_when_refresh_is_rejected_before_password_retry():
    opener = FakeOpener(
        [
            http_error(401),
            json_response({}),
            json_response(
                {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "expires_in": 1200,
                }
            ),
            json_response({"features": [{"id": "product-2", "properties": {"Online": "Y"}}]}),
        ]
    )
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        now=lambda: 1000.0,
        max_retries=1,
    )
    client.session = bhoonidhi.TokenSession(
        access_token="stale-token",
        refresh_token="refresh-a",
        expires_at=900.0,
    )

    items = client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-01-01T00:00:00Z/2026-02-01T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    assert [item["id"] for item in items] == ["product-2"]
    logout_requests = [req for req in opener.requests if req.full_url.endswith("/auth/logout")]
    assert len(logout_requests) == 1
    assert logout_requests[0].headers["Authorization"] == "Bearer stale-token"
    token_payloads = [
        json.loads(req.data.decode("utf-8"))
        for req in opener.requests
        if req.full_url.endswith("/auth/token")
    ]
    assert [payload["grant_type"] for payload in token_payloads] == [
        "refresh_token",
        "password",
    ]


def test_client_follows_search_next_links_with_rate_delay(monkeypatch):
    monkeypatch.setattr(config, "BHOONIDHI_SEARCH_RPS", "2")
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            json_response(
                {
                    "features": [{"id": "product-1", "properties": {"Online": "Y"}}],
                    "links": [{"rel": "next", "href": "/data/search?page=2"}],
                }
            ),
            json_response({"features": [{"id": "product-2", "properties": {"Online": "Y"}}]}),
        ]
    )
    sleeps: list[float] = []
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        sleep=sleeps.append,
        now=lambda: 1000.0,
    )

    items = client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-01-01T00:00:00Z/2026-02-01T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    assert [item["id"] for item in items] == ["product-1", "product-2"]
    assert sleeps == [0.5]
    assert [req.get_method() for req in opener.requests] == ["POST", "POST", "GET"]
    assert opener.requests[2].full_url == "https://bhoonidhi-api.nrsc.gov.in/data/search?page=2"
    assert opener.requests[2].headers["Authorization"] == "Bearer token-a"


def test_client_reauthenticates_and_retries_download_401(tmp_path):
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            http_error(401),
            json_response(
                {
                    "access_token": "token-b",
                    "refresh_token": "refresh-b",
                    "expires_in": 1200,
                }
            ),
            FakeResponse(b"download-bytes"),
        ]
    )
    sleeps: list[float] = []
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        sleep=sleeps.append,
        now=lambda: 1000.0,
        max_retries=1,
    )

    destination = tmp_path / "raw" / "product.zip"
    result = client.download_product(
        product_id="RS_RETRY",
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        destination=destination,
    )

    assert result == {
        "status": "downloaded",
        "path": destination.as_posix(),
        "bytes": len(b"download-bytes"),
    }
    assert destination.read_bytes() == b"download-bytes"
    assert sleeps == [2.0]
    download_requests = [req for req in opener.requests if "/download?" in req.full_url]
    assert [req.headers["Authorization"] for req in download_requests] == [
        "Bearer token-a",
        "Bearer token-b",
    ]


def test_search_uses_bhoonidhi_cql2_filter_shape():
    opener = FakeOpener(
        [
            json_response(
                {
                    "access_token": "token-a",
                    "refresh_token": "refresh-a",
                    "expires_in": 1200,
                }
            ),
            json_response({"features": []}),
        ]
    )
    client = bhoonidhi.BhoonidhiClient(
        user_id="user",
        password="pw",
        opener=opener,
        now=lambda: 1000.0,
    )

    client.search(
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        intersects={"type": "Polygon", "coordinates": []},
    )

    payload = json.loads(opener.requests[-1].data.decode("utf-8"))
    assert payload["filter"] == {
        "op": "eq",
        "args": [{"property": "Online"}, "Y"],
    }
    assert payload["filter-lang"] == "cql2-json"


def test_search_manifest_filters_online_positive_overlap():
    aoi = {
        "id": "bangalore-60km",
        "name": "Bangalore 60 km",
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "geometry": {"type": "Polygon", "coordinates": []},
    }
    manifest = bhoonidhi.build_search_manifest(
        source_id="resourcesat-2a-liss3-boa",
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        aoi=aoi,
        datetime_range="2026-01-01T00:00:00Z/2026-02-01T23:59:59Z",
        items=[
            {
                "id": "online-overlap",
                "bbox": [77.5, 12.5, 78.5, 13.5],
                "properties": {"Online": "Y"},
            },
            {
                "id": "online-overlap-reversed-lat-bbox",
                "bbox": [77.5, 13.5, 78.5, 12.5],
                "properties": {"Online": "Y"},
            },
            {
                "id": "offline-overlap",
                "bbox": [77.5, 12.5, 78.5, 13.5],
                "properties": {"Online": "N"},
            },
            {
                "id": "online-outside",
                "bbox": [80.0, 12.0, 81.0, 13.0],
                "properties": {"Online": "Y"},
            },
        ],
    )

    assert manifest["selection"]["selected_product_ids"] == [
        "online-overlap",
        "online-overlap-reversed-lat-bbox",
    ]
    assert manifest["candidates"][0]["overlap_area"] > 0
    assert manifest["candidates"][1]["bbox"] == [77.5, 12.5, 78.5, 13.5]


def test_load_aoi_selects_feature_collection_member(tmp_path):
    aoi_path = tmp_path / "aois.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "bangalore-60km", "name": "Bangalore"},
                        "bbox": [77.0, 12.0, 78.0, 13.0],
                        "geometry": {"type": "Polygon", "coordinates": [[[]]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"id": "mysore-60km", "name": "Mysore"},
                        "bbox": [75.9, 11.8, 77.0, 12.9],
                        "geometry": {"type": "Polygon", "coordinates": [[[1, 2]]]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    aoi = bhoonidhi.load_aoi(aoi_path, aoi_id="mysore-60km")

    assert aoi["id"] == "mysore-60km"
    assert aoi["name"] == "Mysore"
    assert aoi["bbox"] == [75.9, 11.8, 77.0, 12.9]
    assert aoi["geometry"] == {"type": "Polygon", "coordinates": [[[1, 2]]]}


def test_load_aoi_selects_from_directory(tmp_path):
    aoi_dir = tmp_path / "aois"
    aoi_dir.mkdir()
    (aoi_dir / "mysore-60km.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"id": "mysore-60km", "name": "Mysore"},
                "bbox": [75.9, 11.8, 77.0, 12.9],
                "geometry": {"type": "Polygon", "coordinates": [[[1, 2]]]},
            }
        ),
        encoding="utf-8",
    )

    aoi = bhoonidhi.load_aoi(aoi_dir, aoi_id="mysore-60km")

    assert aoi["id"] == "mysore-60km"
    assert aoi["bbox"] == [75.9, 11.8, 77.0, 12.9]


def test_load_aoi_preserves_top_level_composite_grid_crs_alias(tmp_path):
    aoi_path = tmp_path / "mysore-60km.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "bbox": [75.9, 11.8, 77.0, 12.9],
                "composite_grid_crs": "EPSG:32644",
                "properties": {"id": "mysore-60km", "name": "Mysore"},
                "geometry": {"type": "Polygon", "coordinates": [[[1, 2]]]},
            }
        ),
        encoding="utf-8",
    )

    aoi = bhoonidhi.load_aoi(aoi_path, aoi_id="mysore-60km")

    assert aoi["properties"]["composite_grid_crs"] == "EPSG:32644"
    assert worker._aoi_composite_crs(aoi) == "EPSG:32644"


def test_worker_bhoonidhi_search_writes_manifest(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"id": "bangalore-60km", "name": "Bangalore"},
                "bbox": [77.0, 12.0, 78.0, 13.0],
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def search(self, **kwargs):
            assert kwargs["collection"] == bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION
            return [
                {
                    "id": "RS2A_TEST",
                    "bbox": [77.2, 12.2, 77.8, 12.8],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    result = worker.main(
        [
            "bhoonidhi-search",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--datetime",
            "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
            "--out-dir",
            str(tmp_path),
        ]
    )

    manifest = json.loads(
        (tmp_path / "resourcesat-2a-liss3-boa" / "coverage_manifest.json").read_text()
    )
    assert result == 0
    assert manifest["selection"]["selected_product_ids"] == ["RS2A_TEST"]
    assert manifest["source_id"] == "resourcesat-2a-liss3-boa"


def test_worker_bhoonidhi_search_selects_aoi_from_directory(monkeypatch, tmp_path):
    aoi_dir = tmp_path / "aois"
    aoi_dir.mkdir()
    (aoi_dir / "mysore-60km.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"id": "mysore-60km", "name": "Mysore"},
                "bbox": [75.9, 11.8, 77.0, 12.9],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[75.9, 11.8], [77.0, 11.8], [77.0, 12.9], [75.9, 11.8]]],
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def search(self, **kwargs):
            assert kwargs["intersects"] == {
                "type": "Polygon",
                "coordinates": [[[75.9, 11.8], [77.0, 11.8], [77.0, 12.9], [75.9, 11.8]]],
            }
            return [
                {
                    "id": "RS2A_MYSORE",
                    "bbox": [76.0, 12.0, 76.5, 12.5],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    result = worker.main(
        [
            "bhoonidhi-search",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi",
            "mysore-60km",
            "--aoi-dir",
            str(aoi_dir),
            "--datetime",
            "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
            "--out-dir",
            str(tmp_path / "work"),
        ]
    )

    manifest = json.loads(
        (
            tmp_path
            / "work"
            / "resourcesat-2a-liss3-boa"
            / "coverage_manifest.json"
        ).read_text()
    )
    assert result == 0
    assert manifest["aoi"]["id"] == "mysore-60km"
    assert manifest["selection"]["selected_product_ids"] == ["RS2A_MYSORE"]


def test_worker_build_composite_selects_aoi_from_feature_collection(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aois.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "bangalore-60km", "name": "Bangalore"},
                        "bbox": [77.0, 12.0, 78.0, 13.0],
                        "geometry": {"type": "Polygon", "coordinates": [[[]]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"id": "mysore-60km", "name": "Mysore"},
                        "bbox": [75.9, 11.8, 77.0, 12.9],
                        "geometry": {"type": "Polygon", "coordinates": [[[1, 2]]]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    scene_manifest = tmp_path / "prepare_manifest.json"
    scene_manifest.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_scene_manifest_paths_for_window(paths, **kwargs):
        captured["window"] = kwargs
        return list(paths)

    class FakeBuildResult:
        output_dir = tmp_path / "out" / "resourcesat-2a-liss3-boa" / "composite" / "mysore-60km"
        analytic_cog = output_dir / "analytic.tif"
        mask_cog = output_dir / "mask.tif"
        manifest = output_dir / "prepare_manifest.json"
        metrics = {
            "coverage_percent": 100.0,
            "usable_pixel_percent": 75.0,
            "cloud_masked_percent": 25.0,
        }

    def fake_build_resource_sat_composite(**kwargs):
        captured["aoi"] = kwargs["aoi"]
        captured["source_id"] = kwargs["source_id"]
        return FakeBuildResult()

    monkeypatch.setattr(
        composite, "scene_manifest_paths_for_window", fake_scene_manifest_paths_for_window
    )
    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(
        composite, "build_resource_sat_composite", fake_build_resource_sat_composite
    )

    result = worker.main(
        [
            "build-composite",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi",
            "mysore-60km",
            "--aoi-path",
            str(aoi_path),
            "--manifest-glob",
            str(scene_manifest),
            "--window-start",
            "2026-03-01",
            "--window-end",
            "2026-03-31",
            "--output-root",
            str(tmp_path / "out"),
        ]
    )

    assert result == 0
    assert captured["source_id"] == "resourcesat-2a-liss3-boa"
    assert captured["aoi"]["id"] == "mysore-60km"
    assert captured["aoi"]["bbox"] == [75.9, 11.8, 77.0, 12.9]
    assert captured["window"]["window_start"] == "2026-03-01"
    assert captured["window"]["window_end"] == "2026-03-31"
    assert captured["window"]["aoi_id"] == "mysore-60km"


def test_worker_verify_composite_infers_expected_crs_from_selected_aoi(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aois.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "bangalore-60km", "compositeGridCrs": "EPSG:32643"},
                        "geometry": {"type": "Polygon", "coordinates": [[[77, 12]]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"id": "mysore-60km", "compositeGridCrs": "EPSG:32644"},
                        "geometry": {"type": "Polygon", "coordinates": [[[76, 12]]]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "prepare_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_verify_composite_manifest(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True, detail="ok", checks=["checked"], problems=[])

    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "verify_composite_manifest", fake_verify_composite_manifest)

    result = worker.main(
        [
            "verify-composite",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi",
            "mysore-60km",
            "--aoi-path",
            str(aoi_path),
            "--manifest",
            str(manifest_path),
        ]
    )

    assert result == 0
    assert captured["manifest_path"] == manifest_path
    assert captured["expected_crs"] == "EPSG:32644"
    assert captured["expected_aoi_id"] == "mysore-60km"


def test_worker_verify_composite_derives_expected_crs_without_aoi_metadata(monkeypatch, tmp_path):
    aoi_path = tmp_path / "chennai.geojson"
    aoi_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"id": "chennai-60km"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [79.7, 12.5],
                            [80.8, 12.5],
                            [80.8, 13.6],
                            [79.7, 13.6],
                            [79.7, 12.5],
                        ]
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "prepare_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_verify_composite_manifest(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True, detail="ok", checks=["checked"], problems=[])

    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "verify_composite_manifest", fake_verify_composite_manifest)

    result = worker.main(
        [
            "verify-composite",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi",
            "chennai-60km",
            "--aoi-path",
            str(aoi_path),
            "--manifest",
            str(manifest_path),
        ]
    )

    assert result == 0
    assert captured["expected_crs"] == "EPSG:32644"
    assert captured["expected_aoi_id"] == "chennai-60km"


def test_worker_bhoonidhi_download_updates_manifest(monkeypatch, tmp_path):
    manifest_path = tmp_path / "coverage_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "collection": bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
                "candidates": [{"item_id": "RS2A_TEST", "download_status": "pending"}],
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def download_product(self, *, product_id, collection, destination):
            assert product_id == "RS2A_TEST"
            assert collection == bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 123}

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    result = worker.main(
        [
            "bhoonidhi-download",
            "--manifest",
            str(manifest_path),
            "--raw-root",
            str(tmp_path / "raw"),
        ]
    )

    download_manifest = json.loads((tmp_path / "download_manifest.json").read_text())
    assert result == 0
    assert download_manifest["downloaded"][0]["item_id"] == "RS2A_TEST"
    assert download_manifest["candidates"][0]["download_status"] == "downloaded"


def test_worker_bhoonidhi_download_caps_manifest_products(monkeypatch, tmp_path):
    manifest_path = tmp_path / "coverage_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "collection": bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
                "candidates": [
                    {"item_id": "RS_A", "download_status": "pending"},
                    {"item_id": "RS_B", "download_status": "pending"},
                    {"item_id": "RS_C", "download_status": "pending"},
                ],
            }
        ),
        encoding="utf-8",
    )
    downloaded_ids: list[str] = []

    class FakeClient:
        def download_product(self, *, product_id, collection, destination):
            downloaded_ids.append(product_id)
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 123}

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    result = worker.main(
        [
            "bhoonidhi-download",
            "--manifest",
            str(manifest_path),
            "--raw-root",
            str(tmp_path / "raw"),
            "--max-downloads",
            "2",
        ]
    )

    download_manifest = json.loads((tmp_path / "download_manifest.json").read_text())
    assert result == 0
    assert downloaded_ids == ["RS_A", "RS_B"]
    assert [row["item_id"] for row in download_manifest["downloaded"]] == ["RS_A", "RS_B"]
    assert [row["item_id"] for row in download_manifest["candidates"]] == ["RS_A", "RS_B"]
    assert download_manifest["download"]["deferred_product_ids"] == ["RS_C"]
    assert download_manifest["download"]["max_downloads"] == 2


def test_bhoonidhi_sync_prepare_command_uses_temp_root_derived_work_dir(
    monkeypatch,
    tmp_path,
):
    captured: dict[str, object] = {}

    monkeypatch.setattr(config, "BHOONIDHI_TEMP_ROOT", str(tmp_path / "temp-root"))
    monkeypatch.setattr(config, "BHOONIDHI_RAW_ROOT", str(tmp_path / "raw-root"))
    monkeypatch.setattr(config, "raster_source_root", lambda: tmp_path / "rasters")

    def fake_prepare_script_path(_worker_path: Path) -> Path:
        return tmp_path / "prepare_resourcesat_liss3_boa_cogs.py"

    def fake_run(command, check):
        captured["command"] = command
        captured["check"] = check

    monkeypatch.setattr(sync, "prepare_script_path", fake_prepare_script_path)
    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    args = SimpleNamespace(
        source="resourcesat-2a-liss3-boa",
        aoi="bangalore-60km",
        out_dir=None,
        raw_root=None,
        skip_prepare_validation=False,
        overwrite=False,
        keep_intermediate=False,
    )

    worker._run_prepare_script(args, tmp_path / "download_manifest.json")

    command = captured["command"]
    assert captured["check"] is True
    assert "--work-dir" in command
    work_dir = Path(command[command.index("--work-dir") + 1])
    assert work_dir == (
        tmp_path
        / "temp-root"
        / "resourcesat-2a-liss3-boa"
        / "bangalore-60km"
        / "prepare"
    )


def test_worker_verify_composite_requires_catalog_item_by_default(monkeypatch, tmp_path):
    manifest_path = tmp_path / "prepare_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_verify_composite_manifest(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True, detail="ok", checks=["checked"], problems=[])

    monkeypatch.setattr(config, "STAC_API_URL", "http://stac-api")
    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "verify_composite_manifest", fake_verify_composite_manifest)

    result = worker.main(
        [
            "verify-composite",
            "--manifest",
            str(manifest_path),
        ]
    )

    assert result == 0
    assert captured["require_catalog_item"] is True
    assert captured["stac_api_url"] == "http://stac-api"


def test_worker_verify_composite_local_only_opts_out_of_catalog_check(monkeypatch, tmp_path):
    manifest_path = tmp_path / "prepare_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_verify_composite_manifest(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True, detail="ok", checks=["checked"], problems=[])

    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "verify_composite_manifest", fake_verify_composite_manifest)

    result = worker.main(
        [
            "verify-composite",
            "--manifest",
            str(manifest_path),
            "--local-only",
        ]
    )

    assert result == 0
    assert captured["require_catalog_item"] is False


def test_worker_bhoonidhi_download_writes_failure_manifest(monkeypatch, tmp_path):
    manifest_path = tmp_path / "coverage_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_id": "resourcesat-2a-liss3-boa",
                "collection": bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
                "candidates": [
                    {"item_id": "RS_A", "download_status": "pending"},
                    {"item_id": "RS_B", "download_status": "pending"},
                ],
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def download_product(self, *, product_id, collection, destination):
            if product_id == "RS_B":
                raise RuntimeError("temporary 504")
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 123}

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="temporary 504"):
        worker.main(
            [
                "bhoonidhi-download",
                "--manifest",
                str(manifest_path),
                "--raw-root",
                str(tmp_path / "raw"),
            ]
        )

    download_manifest = json.loads((tmp_path / "download_manifest.json").read_text())
    assert [row["item_id"] for row in download_manifest["downloaded"]] == ["RS_A"]
    assert download_manifest["failed"][0]["item_id"] == "RS_B"
    assert download_manifest["failed"][0]["download_status"] == "failed"
    assert "temporary 504" in download_manifest["failed"][0]["download_error"]
    assert download_manifest["candidates"][1]["download_status"] == "failed"


def test_sync_ledger_filters_terminal_product_statuses(tmp_path):
    conn = sync.connect_ledger(tmp_path / "ledger.sqlite")
    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_OLD",
        status="prepared",
    )
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "selection": {"selected_product_ids": ["RS_OLD", "RS_NEW"]},
        "candidates": [
            {"item_id": "RS_OLD", "download_status": "pending"},
            {"item_id": "RS_NEW", "download_status": "pending"},
        ],
    }

    selection = sync.filter_new_candidates(
        manifest,
        conn=conn,
        source_id="resourcesat-2a-liss3-boa",
    )

    assert selection.selected_product_ids == ["RS_NEW"]
    assert selection.skipped_product_ids == ["RS_OLD"]
    assert selection.manifest["selection"]["selected_product_ids"] == ["RS_NEW"]
    assert selection.manifest["sync"]["skipped_existing_product_ids"] == ["RS_OLD"]


def test_sync_ledger_keeps_downloaded_products_resumable(tmp_path):
    conn = sync.connect_ledger(tmp_path / "ledger.sqlite")
    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_DOWNLOADED_ONLY",
        status="downloaded",
        bytes_count=123,
    )
    manifest = {
        "source_id": "resourcesat-2a-liss3-boa",
        "selection": {"selected_product_ids": ["RS_DOWNLOADED_ONLY"]},
        "candidates": [
            {"item_id": "RS_DOWNLOADED_ONLY", "download_status": "pending"},
        ],
    }

    selection = sync.filter_new_candidates(
        manifest,
        conn=conn,
        source_id="resourcesat-2a-liss3-boa",
    )

    assert selection.selected_product_ids == ["RS_DOWNLOADED_ONLY"]
    assert selection.skipped_product_ids == []
    assert selection.manifest["sync"]["skipped_existing_product_ids"] == []


def test_sync_lock_rejects_second_instance_and_releases(tmp_path):
    lock_path = tmp_path / "sync.lock"
    lock = sync.acquire_lock(lock_path)
    assert lock_path.exists()
    with pytest.raises(sync.SyncLockError):
        sync.acquire_lock(lock_path)

    sync.release_lock(lock)
    assert not lock_path.exists()

    lock = sync.acquire_lock(lock_path)
    sync.release_lock(lock)


def test_sync_ledger_failed_status_increments_retries(tmp_path):
    conn = sync.connect_ledger(tmp_path / "ledger.sqlite")

    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_FAIL",
        status="failed",
        error="timeout",
    )
    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_FAIL",
        status="failed",
        error="rate limit",
    )
    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_FAIL",
        status="downloaded",
        bytes_count=123,
    )

    status, retries, bytes_count, error = conn.execute("""
        select status, retries, bytes, error
        from ingestion_ledger
        where product_id = 'RS_FAIL'
        """).fetchone()
    assert status == "downloaded"
    assert retries == 2
    assert bytes_count == 123
    assert error is None


def test_sync_cleanup_downloads_removes_raw_files_after_success(tmp_path):
    first = tmp_path / "RS_A.zip"
    second = tmp_path / "RS_B.zip"
    first.write_bytes(b"scene-a")
    second.write_bytes(b"scene-b")

    retained = sync.cleanup_downloads(
        [{"path": first.as_posix()}],
        audit_retention=True,
    )
    deleted = sync.cleanup_downloads(
        [{"path": first.as_posix()}, {"downloaded_path": second.as_posix()}],
        audit_retention=False,
    )

    assert retained == []
    assert [path.name for path in deleted] == ["RS_A.zip", "RS_B.zip"]
    assert not first.exists()
    assert not second.exists()


def test_sync_backfill_windows_are_bounded_and_rotated(tmp_path):
    windows = sync.backfill_windows(
        anchor_date=date(2026, 6, 16),
        history_days=90,
        window_days=45,
        step_days=15,
    )

    assert windows[0] == ("2026-03-19", "2026-05-02")
    assert windows[-1] == ("2026-06-02", "2026-06-16")

    state_path = tmp_path / "backfill-state.json"
    first = sync.next_backfill_window(
        state_path,
        source_id="resourcesat-2a-liss3-boa",
        aoi_id="bangalore-60km",
        anchor_date=date(2026, 6, 16),
        history_days=90,
        window_days=45,
        step_days=15,
    )
    second = sync.next_backfill_window(
        state_path,
        source_id="resourcesat-2a-liss3-boa",
        aoi_id="bangalore-60km",
        anchor_date=date(2026, 6, 16),
        history_days=90,
        window_days=45,
        step_days=15,
    )
    third_next_day = sync.next_backfill_window(
        state_path,
        source_id="resourcesat-2a-liss3-boa",
        aoi_id="bangalore-60km",
        anchor_date=date(2026, 6, 17),
        history_days=90,
        window_days=45,
        step_days=15,
    )

    assert first.window_start == "2026-03-19"
    assert first.window_end == "2026-05-02"
    assert first.backfill_index == 1
    assert first.backfill_total == len(windows)
    assert second.window_start == "2026-04-03"
    assert second.window_end == "2026-05-17"
    assert third_next_day.window_start == "2026-04-18"
    assert third_next_day.window_end == "2026-06-01"
    assert json.loads(state_path.read_text(encoding="utf-8"))


def test_worker_bhoonidhi_sync_dry_run_writes_filtered_manifest(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"
    conn = sync.connect_ledger(ledger_path)
    sync.record_product(
        conn,
        source_id="resourcesat-2a-liss3-boa",
        product_id="RS_OLD",
        status="ingested",
    )

    class FakeClient:
        def search(self, **kwargs):
            assert kwargs["collection"] == bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION
            return [
                {
                    "id": "RS_OLD",
                    "bbox": [77.2, 12.2, 77.8, 12.8],
                    "properties": {"Online": "Y", "datetime": "2026-03-05T00:00:00Z"},
                },
                {
                    "id": "RS_NEW",
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                },
            ]

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    result = worker.main(
        [
            "bhoonidhi-sync",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--datetime",
            "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
            "--window-start",
            "2026-03-01",
            "--window-end",
            "2026-03-31",
            "--out-dir",
            str(tmp_path / "work"),
            "--ledger-path",
            str(ledger_path),
            "--dry-run",
        ]
    )

    filtered = json.loads(
        (
            tmp_path
            / "work"
            / "resourcesat-2a-liss3-boa"
            / "bangalore-60km"
            / "coverage_manifest.new.json"
        ).read_text()
    )
    assert result == 0
    assert filtered["selection"]["selected_product_ids"] == ["RS_NEW"]
    assert filtered["sync"]["skipped_existing_product_ids"] == ["RS_OLD"]
    assert not (tmp_path / "ledger.sqlite.lock").exists()


def test_worker_bhoonidhi_sync_empty_search_is_noop_without_composite_failure(
    monkeypatch, tmp_path
):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"

    class FakeClient:
        def search(self, **_kwargs):
            return []

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(config, "raster_source_root", lambda: tmp_path / "missing-rasters")

    result = worker.main(
        [
            "bhoonidhi-sync",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--datetime",
            "2026-05-03T00:00:00Z/2026-06-16T23:59:59Z",
            "--window-start",
            "2026-05-03",
            "--window-end",
            "2026-06-16",
            "--out-dir",
            str(tmp_path / "work"),
            "--ledger-path",
            str(ledger_path),
        ]
    )

    filtered = json.loads(
        (
            tmp_path
            / "work"
            / "resourcesat-2a-liss3-boa"
            / "bangalore-60km"
            / "coverage_manifest.new.json"
        ).read_text()
    )
    assert result == 0
    assert filtered["selection"]["selected_product_ids"] == []
    conn = sqlite3.connect(ledger_path)
    try:
        assert conn.execute("select count(*) from ingestion_ledger").fetchone() == (1,)
        row = conn.execute(
            "select product_id, status, error from ingestion_ledger"
        ).fetchone()
    finally:
        conn.close()
    assert row == (
        "sync:bangalore-60km:2026-05-03T00:00:00Z/2026-06-16T23:59:59Z",
        "searched",
        None,
    )


def test_worker_bhoonidhi_sync_scopes_scratch_manifests_by_aoi(monkeypatch, tmp_path):
    aoi_dir = tmp_path / "aois"
    aoi_dir.mkdir()
    for aoi_id, bbox in {
        "bangalore-60km": [77.0, 12.0, 78.0, 13.0],
        "mysore-60km": [75.9, 11.8, 77.0, 12.9],
    }.items():
        west, south, east, north = bbox
        (aoi_dir / f"{aoi_id}.geojson").write_text(
            json.dumps(
                {
                    "type": "Feature",
                    "properties": {"id": aoi_id, "name": aoi_id},
                    "bbox": bbox,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [west, south],
                                [east, south],
                                [east, north],
                                [west, north],
                                [west, south],
                            ]
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

    class FakeClient:
        def search(self, **_kwargs):
            return []

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(config, "raster_source_root", lambda: tmp_path / "missing-rasters")

    for aoi_id in ("bangalore-60km", "mysore-60km"):
        assert (
            worker.main(
                [
                    "bhoonidhi-sync",
                    "--source",
                    "resourcesat-2a-liss3-boa",
                    "--aoi",
                    aoi_id,
                    "--aoi-dir",
                    str(aoi_dir),
                    "--datetime",
                    "2026-05-03T00:00:00Z/2026-06-16T23:59:59Z",
                    "--window-start",
                    "2026-05-03",
                    "--window-end",
                    "2026-06-16",
                    "--out-dir",
                    str(tmp_path / "work"),
                    "--ledger-path",
                    str(tmp_path / "ledger.sqlite"),
                ]
            )
            == 0
        )

    bangalore_manifest = (
        tmp_path
        / "work"
        / "resourcesat-2a-liss3-boa"
        / "bangalore-60km"
        / "coverage_manifest.new.json"
    )
    mysore_manifest = (
        tmp_path
        / "work"
        / "resourcesat-2a-liss3-boa"
        / "mysore-60km"
        / "coverage_manifest.new.json"
    )
    assert bangalore_manifest.is_file()
    assert mysore_manifest.is_file()
    assert json.loads(bangalore_manifest.read_text())["aoi"]["id"] == "bangalore-60km"
    assert json.loads(mysore_manifest.read_text())["aoi"]["id"] == "mysore-60km"


def test_worker_bhoonidhi_sync_rotates_backfill_window(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"
    state_path = tmp_path / "backfill.json"
    captured_datetimes: list[str] = []

    class FakeClient:
        def search(self, **kwargs):
            captured_datetimes.append(kwargs["datetime_range"])
            return [
                {
                    "id": "RS_BACKFILL",
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    result = worker.main(
        [
            "bhoonidhi-sync",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--backfill-days",
            "90",
            "--window-days",
            "45",
            "--backfill-step-days",
            "15",
            "--backfill-anchor-date",
            "2026-06-16",
            "--backfill-state-path",
            str(state_path),
            "--out-dir",
            str(tmp_path / "work"),
            "--ledger-path",
            str(ledger_path),
            "--dry-run",
        ]
    )

    filtered = json.loads(
        (
            tmp_path
            / "work"
            / "resourcesat-2a-liss3-boa"
            / "bangalore-60km"
            / "coverage_manifest.new.json"
        ).read_text()
    )
    assert result == 0
    assert captured_datetimes == ["2026-03-19T00:00:00Z/2026-05-02T23:59:59Z"]
    assert filtered["sync"]["window_start"] == "2026-03-19"
    assert filtered["sync"]["window_end"] == "2026-05-02"
    assert filtered["sync"]["backfill_index"] == 1
    assert filtered["sync"]["backfill_total"] == 6
    assert not state_path.exists()


def test_worker_bhoonidhi_sync_caps_downloads_per_run(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"
    downloaded_ids: list[str] = []

    class FakeClient:
        def search(self, **_kwargs):
            return [
                {
                    "id": product_id,
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": f"2026-03-{day:02d}T00:00:00Z"},
                }
                for product_id, day in [("RS_A", 5), ("RS_B", 12), ("RS_C", 19)]
            ]

        def download_product(self, *, product_id, collection, destination):
            downloaded_ids.append(product_id)
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 123}

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(worker, "_run_prepare_script", lambda *_args, **_kwargs: None)

    result = worker.main(
        [
            "bhoonidhi-sync",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--datetime",
            "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
            "--window-start",
            "2026-03-01",
            "--window-end",
            "2026-03-31",
            "--out-dir",
            str(tmp_path / "work"),
            "--ledger-path",
            str(ledger_path),
            "--max-downloads",
            "2",
            "--skip-composite",
        ]
    )

    filtered = json.loads(
        (
            tmp_path
            / "work"
            / "resourcesat-2a-liss3-boa"
            / "bangalore-60km"
            / "coverage_manifest.new.json"
        ).read_text()
    )
    assert result == 0
    assert downloaded_ids == ["RS_A", "RS_B"]
    assert filtered["selection"]["selected_product_ids"] == ["RS_A", "RS_B"]
    assert filtered["sync"]["selected_new_product_ids"] == ["RS_A", "RS_B", "RS_C"]
    assert filtered["sync"]["deferred_product_ids"] == ["RS_C"]
    assert filtered["sync"]["max_downloads_per_sync"] == 2
    assert sqlite_row(
        ledger_path,
        "select count(*) from ingestion_ledger where status = 'prepared'",
    ) == (2,)
    assert sqlite_row(
        ledger_path,
        "select count(*) from ingestion_ledger where product_id = 'RS_C'",
    ) == (0,)


def test_worker_bhoonidhi_sync_records_search_failure(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"

    class FakeClient:
        def search(self, **_kwargs):
            raise RuntimeError("Bhoonidhi search HTTP 429")

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="Bhoonidhi search HTTP 429"):
        worker.main(
            [
                "bhoonidhi-sync",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--aoi-path",
                str(aoi_path),
                "--datetime",
                "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
                "--window-start",
                "2026-03-01",
                "--window-end",
                "2026-03-31",
                "--out-dir",
                str(tmp_path / "work"),
                "--ledger-path",
                str(ledger_path),
            ]
        )

    row = sqlite_row(
        ledger_path,
        "select product_id, status, error from ingestion_ledger",
    )
    assert row[0] == "sync:bangalore-60km:2026-03-01T00:00:00Z/2026-03-31T23:59:59Z"
    assert row[1] == "failed"
    assert "Bhoonidhi search failed" in row[2]
    assert "HTTP 429" in row[2]


def test_worker_bhoonidhi_sync_records_download_failure_with_triage_prefix(
    monkeypatch, tmp_path
):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"

    class FakeClient:
        def search(self, **_kwargs):
            return [
                {
                    "id": "RS_NEW",
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

        def download_product(self, *, product_id, collection, destination):
            raise RuntimeError(f"temporary 504 for {product_id}")

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="temporary 504"):
        worker.main(
            [
                "bhoonidhi-sync",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--aoi-path",
                str(aoi_path),
                "--datetime",
                "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
                "--window-start",
                "2026-03-01",
                "--window-end",
                "2026-03-31",
                "--out-dir",
                str(tmp_path / "work"),
                "--ledger-path",
                str(ledger_path),
            ]
        )

    status, error = sqlite_row(
        ledger_path,
        "select status, error from ingestion_ledger where product_id = 'RS_NEW'",
    )
    assert status == "failed"
    assert "download failed" in error
    assert "temporary 504" in error


def test_worker_bhoonidhi_sync_records_prepare_failure(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"

    class FakeClient:
        def search(self, **_kwargs):
            return [
                {
                    "id": "RS_NEW",
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

        def download_product(self, *, product_id, collection, destination):
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 123}

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(
        worker,
        "_run_prepare_script",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("GDAL convert failed")),
    )

    with pytest.raises(RuntimeError, match="GDAL convert failed"):
        worker.main(
            [
                "bhoonidhi-sync",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--aoi-path",
                str(aoi_path),
                "--datetime",
                "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
                "--window-start",
                "2026-03-01",
                "--window-end",
                "2026-03-31",
                "--out-dir",
                str(tmp_path / "work"),
                "--ledger-path",
                str(ledger_path),
            ]
        )

    status, error = sqlite_row(
        ledger_path,
        "select status, error from ingestion_ledger where product_id = 'RS_NEW'",
    )
    assert status == "failed"
    assert "conversion failed" in error
    assert "GDAL convert failed" in error


def test_worker_bhoonidhi_sync_records_stac_registration_failure(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"
    scene_manifest = tmp_path / "prepared" / "prepare_manifest.json"
    scene_manifest.parent.mkdir(parents=True)
    scene_manifest.write_text("{}", encoding="utf-8")
    composite_manifest = tmp_path / "composite" / "2026-03-19" / "prepare_manifest.json"
    composite_manifest.parent.mkdir(parents=True)
    composite_manifest.write_text("{}", encoding="utf-8")

    class FakeClient:
        def search(self, **_kwargs):
            return []

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(config, "prepared_manifest_files", lambda source_id=None: [scene_manifest])
    monkeypatch.setattr(
        composite,
        "scene_manifest_paths_for_window",
        lambda *args, **kwargs: [scene_manifest],
    )
    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "default_resolution", lambda source_id: 24)
    monkeypatch.setattr(
        composite,
        "build_resource_sat_composite",
        lambda **_kwargs: SimpleNamespace(manifest=composite_manifest),
    )
    monkeypatch.setattr(
        composite,
        "verify_composite_manifest",
        lambda **_kwargs: SimpleNamespace(ok=True, detail="composite ok"),
    )
    monkeypatch.setattr(storage, "ensure_bucket", lambda: "bucket exists")
    monkeypatch.setattr(storage, "seed_manifest_cogs", lambda *_args, **_kwargs: ["uploaded"])
    monkeypatch.setattr(
        catalog,
        "load_manifest_items",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("pgSTAC load failed")),
    )

    with pytest.raises(RuntimeError, match="pgSTAC load failed"):
        worker.main(
            [
                "bhoonidhi-sync",
                "--source",
                "resourcesat-2a-liss3-boa",
                "--aoi-path",
                str(aoi_path),
                "--datetime",
                "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
                "--window-start",
                "2026-03-01",
                "--window-end",
                "2026-03-31",
                "--out-dir",
                str(tmp_path / "work"),
                "--ledger-path",
                str(ledger_path),
            ]
        )

    status, error = sqlite_row(
        ledger_path,
        "select status, error from ingestion_ledger "
        "where product_id = 'composite:bangalore-60km:2026-03-19'",
    )
    assert status == "failed"
    assert "STAC registration failed" in error
    assert "pgSTAC load failed" in error


def test_worker_bhoonidhi_sync_deletes_raw_downloads_after_success(monkeypatch, tmp_path):
    aoi_path = tmp_path / "aoi.geojson"
    _write_test_aoi(aoi_path)
    ledger_path = tmp_path / "ledger.sqlite"
    scene_manifest = tmp_path / "prepared" / "prepare_manifest.json"
    scene_manifest.parent.mkdir(parents=True)
    scene_manifest.write_text("{}", encoding="utf-8")
    composite_manifest = tmp_path / "composite" / "2026-03-19" / "prepare_manifest.json"
    composite_manifest.parent.mkdir(parents=True)
    composite_manifest.write_text("{}", encoding="utf-8")
    raw_root = tmp_path / "raw"
    downloaded_path = raw_root / "resourcesat-2a-liss3-boa" / "RS_SUCCESS.zip"

    class FakeClient:
        def search(self, **_kwargs):
            return [
                {
                    "id": "RS_SUCCESS",
                    "bbox": [77.3, 12.3, 77.9, 12.9],
                    "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
                }
            ]

        def download_product(self, *, product_id, collection, destination):
            assert product_id == "RS_SUCCESS"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"raw-product")
            return {"status": "downloaded", "path": destination.as_posix(), "bytes": 11}

    def fake_prepare(_args, _manifest_path):
        scene_manifest.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(bhoonidhi, "BhoonidhiClient", lambda: FakeClient())
    monkeypatch.setattr(worker, "_run_prepare_script", fake_prepare)
    monkeypatch.setattr(config, "prepared_manifest_files", lambda source_id=None: [scene_manifest])
    monkeypatch.setattr(
        composite,
        "scene_manifest_paths_for_window",
        lambda *args, **kwargs: [scene_manifest],
    )
    monkeypatch.setattr(composite, "require_raster_deps", lambda: object())
    monkeypatch.setattr(composite, "default_resolution", lambda source_id: 24)
    monkeypatch.setattr(
        composite,
        "build_resource_sat_composite",
        lambda **_kwargs: SimpleNamespace(manifest=composite_manifest),
    )
    monkeypatch.setattr(
        composite,
        "verify_composite_manifest",
        lambda **_kwargs: SimpleNamespace(ok=True, detail="composite ok"),
    )
    monkeypatch.setattr(storage, "ensure_bucket", lambda: "bucket exists")
    monkeypatch.setattr(storage, "seed_manifest_cogs", lambda *_args, **_kwargs: ["uploaded"])
    monkeypatch.setattr(catalog, "load_manifest_items", lambda *_args, **_kwargs: "loaded")

    result = worker.main(
        [
            "bhoonidhi-sync",
            "--source",
            "resourcesat-2a-liss3-boa",
            "--aoi-path",
            str(aoi_path),
            "--datetime",
            "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
            "--window-start",
            "2026-03-01",
            "--window-end",
            "2026-03-31",
            "--raw-root",
            str(raw_root),
            "--out-dir",
            str(tmp_path / "work"),
            "--ledger-path",
            str(ledger_path),
        ]
    )

    status = sqlite_row(
        ledger_path,
        "select status from ingestion_ledger "
        "where product_id = 'composite:bangalore-60km:2026-03-19'",
    )
    assert result == 0
    assert status == ("composited",)
    assert not downloaded_path.exists()
