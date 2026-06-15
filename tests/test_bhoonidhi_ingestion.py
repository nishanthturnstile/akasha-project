from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import bhoonidhi, sync  # noqa: E402

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


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://bhoonidhi-api.nrsc.gov.in/data/search",
        code=code,
        msg="error",
        hdrs={},
        fp=io.BytesIO(b'{"Description":"retry"}'),
    )


def json_response(payload: dict) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"))


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

    status, retries, bytes_count, error = conn.execute(
        """
        select status, retries, bytes, error
        from ingestion_ledger
        where product_id = 'RS_FAIL'
        """
    ).fetchone()
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


def test_worker_bhoonidhi_sync_dry_run_writes_filtered_manifest(monkeypatch, tmp_path):
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
            / "coverage_manifest.new.json"
        ).read_text()
    )
    assert result == 0
    assert filtered["selection"]["selected_product_ids"] == ["RS_NEW"]
    assert filtered["sync"]["skipped_existing_product_ids"] == ["RS_OLD"]
    assert not (tmp_path / "ledger.sqlite.lock").exists()
