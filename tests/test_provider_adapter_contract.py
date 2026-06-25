"""Provider adapter contract tests (TASK-011 and TASK-012A).

Validates:
1. Bhoonidhi adapter emits normalized candidate/download shapes consistent with
   the existing ``candidate_from_item`` path — using a stub client, no live calls.
2. Unknown providers fail closed via ``get_provider_adapter("unknown")``.
3. Placeholder adapters raise ``ProviderActionUnsupported`` for search/download/
   normalize_candidate (and unsupported order methods).
4. Commercial placeholders raise ``CommercialPreflightFailed`` from ``order()``
   by default; ``assert_commercial_ready`` allows only fully-approved calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest.bhoonidhi import candidate_from_item  # noqa: E402
from akasha_ingest.providers.base import (  # noqa: E402
    CandidateItem,
    CommercialPreflightFailed,
    DownloadRequest,
    NormalizedCandidate,
    OrderRequest,
    ProviderActionUnsupported,
    ResumableState,
    SearchRequest,
    assert_commercial_ready,
)
from akasha_ingest.providers.bhoonidhi_adapter import BhoonidhiAdapter  # noqa: E402
from akasha_ingest.providers.registry import (  # noqa: E402
    UnknownProviderError,
    get_provider_adapter,
)

# ---------------------------------------------------------------------------
# Shared fake Bhoonidhi item (representative of what the real API returns)
# ---------------------------------------------------------------------------

_FAKE_BHOONIDHI_ITEM: dict[str, Any] = {
    "id": "RS2A_LISS3_20240315_112233_BLR",
    "collection": "ResourceSat-2A_LISS3_BOA",
    "datetime": "2024-03-15T11:22:33Z",
    "bbox": [77.0, 12.5, 78.5, 13.5],
    "properties": {
        "datetime": "2024-03-15T11:22:33Z",
        "Online": "Y",
        "eo:cloud_cover": 5.2,
        "fileSize": 204800,
        "acquisitionDate": "2024-03-15",
        "satelliteName": "ResourceSat-2A",
        "sensorName": "LISS3",
        "productLevel": "BOA",
    },
}

_SOURCE_ID = "resourcesat-2a-liss3-boa"
_AOI_BBOX = [77.0, 12.5, 78.5, 13.5]


# ---------------------------------------------------------------------------
# Helpers: build a stub BhoonidhiClient
# ---------------------------------------------------------------------------


def _make_stub_client(items: list[dict[str, Any]]) -> MagicMock:
    """Return a mock BhoonidhiClient that returns *items* from search()."""
    stub = MagicMock()
    stub.search.return_value = items
    return stub


def _make_search_request(**kwargs: Any) -> SearchRequest:
    defaults: dict[str, Any] = {
        "source_id": _SOURCE_ID,
        "collection": "ResourceSat-2A_LISS3_BOA",
        "bbox": _AOI_BBOX,
        "datetime_from": "2024-03-01T00:00:00Z",
        "datetime_to": "2024-03-31T23:59:59Z",
    }
    defaults.update(kwargs)
    return SearchRequest(**defaults)


# ---------------------------------------------------------------------------
# 1. Bhoonidhi adapter — search() shape matches candidate_from_item()
# ---------------------------------------------------------------------------


class TestBhoonidhiAdapterSearch:
    def test_search_returns_search_result_with_candidates(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        req = _make_search_request()

        result = adapter.search(req)

        assert result.source_id == _SOURCE_ID
        assert len(result.candidates) == 1
        assert result.pagination.has_more is False
        assert result.pagination.next_page_token is None
        assert result.pagination.total_count == 1

    def test_search_candidate_item_id_matches_candidate_from_item(self) -> None:
        """CandidateItem.provider_item_id must equal the item_id from candidate_from_item."""
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        req = _make_search_request()

        result = adapter.search(req)
        candidate = result.candidates[0]

        # Reference value from the existing bhoonidhi helper
        ref = candidate_from_item(_FAKE_BHOONIDHI_ITEM, _AOI_BBOX)
        assert candidate.provider_item_id == ref["item_id"]

    def test_search_candidate_online_flag_matches_candidate_from_item(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())
        candidate = result.candidates[0]

        ref = candidate_from_item(_FAKE_BHOONIDHI_ITEM, _AOI_BBOX)
        ref_online = str(ref.get("online") or "").strip().upper() == "Y"
        assert candidate.online == ref_online

    def test_search_candidate_bbox_matches_candidate_from_item(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())
        candidate = result.candidates[0]

        ref = candidate_from_item(_FAKE_BHOONIDHI_ITEM, _AOI_BBOX)
        assert candidate.bbox == ref["bbox"]

    def test_search_candidate_cloud_cover_extracted(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())
        candidate = result.candidates[0]

        assert candidate.cloud_cover_pct == pytest.approx(5.2)

    def test_search_candidate_download_size_bytes_extracted(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())
        candidate = result.candidates[0]

        assert candidate.download_size_bytes == 204800

    def test_search_estimated_cost_units_is_zero_for_bhoonidhi(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())
        candidate = result.candidates[0]

        assert candidate.estimated_cost_units == 0.0

    def test_search_no_items_returns_empty_candidates(self) -> None:
        stub = _make_stub_client([])
        adapter = BhoonidhiAdapter(client=stub)

        result = adapter.search(_make_search_request())

        assert result.candidates == []
        assert result.pagination.total_count == 0

    def test_search_passes_bbox_as_polygon_geometry_to_client(self) -> None:
        stub = _make_stub_client([])
        adapter = BhoonidhiAdapter(client=stub)

        adapter.search(_make_search_request())

        _args, kwargs = stub.search.call_args
        if "intersects" in kwargs:
            intersects = kwargs["intersects"]
        else:
            intersects = _args[2]
        assert intersects["type"] == "Polygon"

    def test_search_passes_datetime_range_to_client(self) -> None:
        stub = _make_stub_client([])
        adapter = BhoonidhiAdapter(client=stub)
        req = _make_search_request(
            datetime_from="2024-01-01T00:00:00Z",
            datetime_to="2024-01-31T23:59:59Z",
        )

        adapter.search(req)

        _args, kwargs = stub.search.call_args
        datetime_range = kwargs.get("datetime_range") or (_args[1] if len(_args) > 1 else None)
        assert "2024-01-01" in datetime_range
        assert "2024-01-31" in datetime_range


# ---------------------------------------------------------------------------
# 2. Bhoonidhi adapter — normalize_candidate() shape
# ---------------------------------------------------------------------------


class TestBhoonidhiAdapterNormalizeCandidate:
    def _get_candidate_item(self) -> CandidateItem:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        result = adapter.search(_make_search_request())
        return result.candidates[0]

    def test_normalize_candidate_returns_normalized_candidate(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()
        req = _make_search_request()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, req)

        assert isinstance(nc, NormalizedCandidate)

    def test_normalize_candidate_item_id_matches_provider_item_id(self) -> None:
        """For Bhoonidhi, item_id == provider_item_id (ISRO naming encodes provenance)."""
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()
        req = _make_search_request()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, req)

        assert nc.item_id == nc.provider_item_id

    def test_normalize_candidate_source_id_echoed(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert nc.source_id == _SOURCE_ID

    def test_normalize_candidate_acquisition_datetime_populated(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert nc.acquisition_datetime
        assert "2024-03-15" in nc.acquisition_datetime

    def test_normalize_candidate_bbox_echoed(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert nc.bbox == _AOI_BBOX

    def test_normalize_candidate_online_true_for_online_item(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert nc.online is True

    def test_normalize_candidate_estimated_cost_units_zero(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert nc.estimated_cost_units == 0.0

    def test_normalize_candidate_bhoonidhi_collection_in_extra(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()

        nc = adapter.normalize_candidate(item, _SOURCE_ID, _make_search_request())

        assert "bhoonidhi_collection" in nc.extra
        assert nc.extra["bhoonidhi_collection"] == "ResourceSat-2A_LISS3_BOA"

    def test_normalize_candidate_intersects_aoi_for_overlapping_item(self) -> None:
        stub = _make_stub_client([_FAKE_BHOONIDHI_ITEM])
        adapter = BhoonidhiAdapter(client=stub)
        item = self._get_candidate_item()
        # Request AOI fully overlaps item bbox
        req = _make_search_request(bbox=[77.0, 12.5, 78.5, 13.5])

        nc = adapter.normalize_candidate(item, _SOURCE_ID, req)

        assert nc.intersects_aoi is True


# ---------------------------------------------------------------------------
# 3. Bhoonidhi adapter — download() maps to DownloadResult
# ---------------------------------------------------------------------------


class TestBhoonidhiAdapterDownload:
    def _make_normalized_candidate(self) -> NormalizedCandidate:
        return NormalizedCandidate(
            source_id=_SOURCE_ID,
            provider_item_id="RS2A_LISS3_20240315_112233_BLR",
            item_id="RS2A_LISS3_20240315_112233_BLR",
            acquisition_datetime="2024-03-15T11:22:33Z",
            bbox=_AOI_BBOX,
            intersects_aoi=True,
            extra={"bhoonidhi_collection": "ResourceSat-2A_LISS3_BOA"},
        )

    def test_download_dry_run_returns_no_success_and_no_path(self, tmp_path: Path) -> None:
        stub = _make_stub_client([])
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(
            candidate=candidate,
            dest_dir=str(tmp_path),
            dry_run=True,
        )

        result = adapter.download(req)

        assert result.dry_run is True
        assert result.success is False
        assert result.local_path is None
        assert result.downloaded_bytes == 0

    def test_download_dry_run_no_network_call(self, tmp_path: Path) -> None:
        stub = _make_stub_client([])
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(
            candidate=candidate,
            dest_dir=str(tmp_path),
            dry_run=True,
        )

        adapter.download(req)

        stub.download_product.assert_not_called()

    def test_download_success_maps_client_result_to_download_result(
        self, tmp_path: Path
    ) -> None:
        stub = _make_stub_client([])
        stub.download_product.return_value = {
            "status": "downloaded",
            "path": str(tmp_path / "RS2A_LISS3_20240315_112233_BLR.zip"),
            "bytes": 204800,
        }
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(
            candidate=candidate,
            dest_dir=str(tmp_path),
            dry_run=False,
        )

        result = adapter.download(req)

        assert result.success is True
        assert result.downloaded_bytes == 204800
        assert result.local_path is not None
        assert result.item_id == candidate.item_id
        assert result.provider_item_id == candidate.provider_item_id

    def test_download_existing_file_maps_status_exists_to_success(
        self, tmp_path: Path
    ) -> None:
        stub = _make_stub_client([])
        stub.download_product.return_value = {
            "status": "exists",
            "path": str(tmp_path / "RS2A_LISS3_20240315_112233_BLR.zip"),
            "bytes": 0,
        }
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(
            candidate=candidate,
            dest_dir=str(tmp_path),
            dry_run=False,
        )

        result = adapter.download(req)

        assert result.success is True

    def test_download_increments_attempt_count_from_resume_state(
        self, tmp_path: Path
    ) -> None:
        stub = _make_stub_client([])
        stub.download_product.return_value = {
            "status": "downloaded",
            "path": str(tmp_path / "RS2A_LISS3_20240315_112233_BLR.zip"),
            "bytes": 1,
        }
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(
            candidate=candidate,
            dest_dir=str(tmp_path),
            resume_state=ResumableState(attempt_count=2),
        )

        result = adapter.download(req)

        assert result.resume_state.attempt_count == 3

    def test_download_item_id_and_provider_item_id_in_result(
        self, tmp_path: Path
    ) -> None:
        stub = _make_stub_client([])
        stub.download_product.return_value = {
            "status": "downloaded",
            "path": str(tmp_path / "RS2A_LISS3_20240315_112233_BLR.zip"),
            "bytes": 1,
        }
        adapter = BhoonidhiAdapter(client=stub)
        candidate = self._make_normalized_candidate()
        req = DownloadRequest(candidate=candidate, dest_dir=str(tmp_path))

        result = adapter.download(req)

        assert result.item_id == "RS2A_LISS3_20240315_112233_BLR"
        assert result.provider_item_id == "RS2A_LISS3_20240315_112233_BLR"


# ---------------------------------------------------------------------------
# 4. Bhoonidhi order/poll_order/cancel_order raise ProviderActionUnsupported
# ---------------------------------------------------------------------------


class TestBhoonidhiAdapterFailClosedOrderMethods:
    def test_order_raises_provider_action_unsupported(self) -> None:
        adapter = BhoonidhiAdapter()
        candidate = NormalizedCandidate(
            source_id=_SOURCE_ID,
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(candidate=candidate, allow_paid_order=False)

        with pytest.raises(ProviderActionUnsupported):
            adapter.order(req)

    def test_poll_order_raises_provider_action_unsupported(self) -> None:
        adapter = BhoonidhiAdapter()

        with pytest.raises(ProviderActionUnsupported):
            adapter.poll_order("fake-order-id")

    def test_cancel_order_raises_provider_action_unsupported(self) -> None:
        adapter = BhoonidhiAdapter()

        with pytest.raises(ProviderActionUnsupported):
            adapter.cancel_order("fake-order-id")

    def test_quota_preflight_returns_not_supported(self) -> None:
        from akasha_ingest.providers.base import QuotaPreflightRequest

        adapter = BhoonidhiAdapter()
        candidate = NormalizedCandidate(
            source_id=_SOURCE_ID,
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        result = adapter.quota_preflight(QuotaPreflightRequest(candidate=candidate))

        assert result.not_supported is True
        assert result.available is False


# ---------------------------------------------------------------------------
# 5. Registry — unknown provider fails closed
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_unknown_provider_raises_unknown_provider_error(self) -> None:
        with pytest.raises(UnknownProviderError):
            get_provider_adapter("unknown")

    def test_unknown_provider_error_is_provider_error(self) -> None:
        from akasha_ingest.providers.base import ProviderError

        with pytest.raises(ProviderError):
            get_provider_adapter("totally_unknown_provider_xyz")

    def test_unknown_provider_error_contains_provider_name(self) -> None:
        with pytest.raises(UnknownProviderError) as exc_info:
            get_provider_adapter("not_a_provider")

        assert "not_a_provider" in str(exc_info.value)

    def test_bhoonidhi_registry_returns_bhoonidhi_adapter(self) -> None:
        adapter = get_provider_adapter("bhoonidhi")
        assert adapter.adapter_name == "bhoonidhi"

    def test_planet_registry_returns_planet_adapter(self) -> None:
        adapter = get_provider_adapter("planet")
        assert adapter.adapter_name == "planet"

    def test_jaxa_registry_returns_jaxa_adapter(self) -> None:
        adapter = get_provider_adapter("jaxa")
        assert adapter.adapter_name == "jaxa"

    def test_vendor_registry_returns_vendor_adapter(self) -> None:
        adapter = get_provider_adapter("vendor")
        assert adapter.adapter_name == "vendor"

    def test_cdse_registry_returns_cdse_adapter(self) -> None:
        adapter = get_provider_adapter("cdse")
        assert adapter.adapter_name == "cdse"

    def test_usgs_registry_returns_usgs_adapter(self) -> None:
        adapter = get_provider_adapter("usgs")
        assert adapter.adapter_name == "usgs"

    def test_usda_registry_returns_usda_adapter(self) -> None:
        adapter = get_provider_adapter("usda")
        assert adapter.adapter_name == "usda"

    # Phase 12 — TASK-075 (Earthdata/ASF): registry must resolve these placeholders
    def test_earthdata_registry_returns_earthdata_adapter(self) -> None:
        """TASK-075: earthdata provider must resolve to a registered placeholder adapter."""
        adapter = get_provider_adapter("earthdata")
        assert adapter.adapter_name == "earthdata"

    def test_asf_registry_returns_asf_adapter(self) -> None:
        """TASK-075: asf provider must resolve to a registered placeholder adapter."""
        adapter = get_provider_adapter("asf")
        assert adapter.adapter_name == "asf"


# ---------------------------------------------------------------------------
# 6. Placeholder adapters — fail closed for search/download/normalize_candidate
# ---------------------------------------------------------------------------


class TestPlaceholderAdapterFailClosed:
    """All placeholder adapters must raise ProviderActionUnsupported for core methods."""

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_search_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        req = SearchRequest(
            source_id="test-source",
            collection="test-collection",
            bbox=[77.0, 12.5, 78.5, 13.5],
        )

        with pytest.raises(ProviderActionUnsupported):
            adapter.search(req)

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_download_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = DownloadRequest(candidate=candidate, dest_dir="/tmp")

        with pytest.raises(ProviderActionUnsupported):
            adapter.download(req)

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_normalize_candidate_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        item = CandidateItem(provider_item_id="x", raw_properties={})
        req = SearchRequest(source_id="test-source", collection="test-collection")

        with pytest.raises(ProviderActionUnsupported):
            adapter.normalize_candidate(item, "test-source", req)

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_order_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(candidate=candidate, allow_paid_order=False)

        with pytest.raises(ProviderActionUnsupported):
            adapter.order(req)

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_poll_order_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)

        with pytest.raises(ProviderActionUnsupported):
            adapter.poll_order("fake-id")

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_cancel_order_raises(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)

        with pytest.raises(ProviderActionUnsupported):
            adapter.cancel_order("fake-id")

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_quota_preflight_returns_not_supported(
        self, provider_key: str
    ) -> None:
        from akasha_ingest.providers.base import QuotaPreflightRequest

        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        result = adapter.quota_preflight(QuotaPreflightRequest(candidate=candidate))

        assert result.not_supported is True
        assert result.available is False

    @pytest.mark.parametrize("provider_key", ["cdse", "usgs", "earthdata", "asf", "usda"])
    def test_free_placeholder_close_is_safe_noop(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        adapter.close()  # must not raise


# ---------------------------------------------------------------------------
# 7. Commercial placeholder adapters — order() raises CommercialPreflightFailed
# ---------------------------------------------------------------------------


class TestCommercialPlaceholderFailClosed:
    """Commercial placeholders must raise CommercialPreflightFailed from order()."""

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_order_raises_commercial_preflight_failed_by_default(
        self, provider_key: str
    ) -> None:
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(
            candidate=candidate,
            allow_paid_order=False,
            commercial_readiness_record_id=None,
        )

        with pytest.raises(CommercialPreflightFailed):
            adapter.order(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_order_raises_even_with_allow_paid_order_true_when_no_record(
        self, provider_key: str
    ) -> None:
        """Allowed flag alone is insufficient — a readiness record is also required."""
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(
            candidate=candidate,
            allow_paid_order=True,  # set but no record
            commercial_readiness_record_id=None,
        )

        with pytest.raises(CommercialPreflightFailed):
            adapter.order(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_order_raises_even_with_record_but_no_allow_flag(
        self, provider_key: str
    ) -> None:
        """Record alone without allow_paid_order flag must also fail."""
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(
            candidate=candidate,
            allow_paid_order=False,
            commercial_readiness_record_id="readiness-2024-001",
        )

        with pytest.raises(CommercialPreflightFailed):
            adapter.order(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_order_commercial_blocked_state_always_raises(
        self, provider_key: str
    ) -> None:
        """commercial_blocked state must prevent any order regardless of other flags."""
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        # Even with all other flags set, commercial_blocked state blocks the call
        req = OrderRequest(
            candidate=candidate,
            allow_paid_order=True,
            commercial_readiness_record_id="readiness-2024-001",
        )

        # CommercialPlaceholderAdapterBase hardcodes commercial_state="commercial_blocked"
        with pytest.raises(CommercialPreflightFailed):
            adapter.order(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_order_error_message_contains_adapter_name(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = OrderRequest(candidate=candidate, allow_paid_order=False)

        with pytest.raises(CommercialPreflightFailed) as exc_info:
            adapter.order(req)

        assert provider_key in str(exc_info.value)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_search_raises_provider_action_unsupported(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        req = SearchRequest(source_id="test-source", collection="test-collection")

        with pytest.raises(ProviderActionUnsupported):
            adapter.search(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_download_raises_provider_action_unsupported(self, provider_key: str) -> None:
        adapter = get_provider_adapter(provider_key)
        candidate = NormalizedCandidate(
            source_id="test-source",
            provider_item_id="x",
            item_id="x",
            acquisition_datetime="2024-01-01T00:00:00Z",
            bbox=[77.0, 12.5, 78.5, 13.5],
            intersects_aoi=True,
        )
        req = DownloadRequest(candidate=candidate, dest_dir="/tmp")

        with pytest.raises(ProviderActionUnsupported):
            adapter.download(req)

    @pytest.mark.parametrize("provider_key", ["planet", "jaxa", "vendor"])
    def test_normalize_candidate_raises_provider_action_unsupported(
        self, provider_key: str
    ) -> None:
        adapter = get_provider_adapter(provider_key)
        item = CandidateItem(provider_item_id="x", raw_properties={})
        req = SearchRequest(source_id="test-source", collection="test-collection")

        with pytest.raises(ProviderActionUnsupported):
            adapter.normalize_candidate(item, "test-source", req)


# ---------------------------------------------------------------------------
# 8. assert_commercial_ready — unit tests
# ---------------------------------------------------------------------------


class TestAssertCommercialReady:
    def test_passes_when_all_criteria_met(self) -> None:
        # Must NOT raise — this is the only valid path
        assert_commercial_ready(
            adapter_name="planet",
            source_id="planet-ps-orthotile",
            allow_paid_order=True,
            commercial_readiness_record_id="readiness-2024-001",
            commercial_state="approved",  # not "commercial_blocked"
        )

    def test_raises_when_commercial_blocked(self) -> None:
        with pytest.raises(CommercialPreflightFailed) as exc_info:
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=True,
                commercial_readiness_record_id="readiness-2024-001",
                commercial_state="commercial_blocked",
            )

        assert "commercial_blocked" in str(exc_info.value)

    def test_raises_when_allow_paid_order_false(self) -> None:
        with pytest.raises(CommercialPreflightFailed) as exc_info:
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=False,
                commercial_readiness_record_id="readiness-2024-001",
                commercial_state="approved",
            )

        assert "allow_paid_order" in str(exc_info.value)

    def test_raises_when_readiness_record_missing(self) -> None:
        with pytest.raises(CommercialPreflightFailed) as exc_info:
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=True,
                commercial_readiness_record_id=None,
                commercial_state="approved",
            )

        assert "commercial_readiness_record_id" in str(exc_info.value)

    def test_raises_when_readiness_record_empty_string(self) -> None:
        with pytest.raises(CommercialPreflightFailed):
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=True,
                commercial_readiness_record_id="",
                commercial_state="approved",
            )

    def test_error_includes_all_failure_reasons(self) -> None:
        """When multiple criteria fail, all reasons are reported."""
        with pytest.raises(CommercialPreflightFailed) as exc_info:
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=False,
                commercial_readiness_record_id=None,
                commercial_state="commercial_blocked",
            )

        exc = exc_info.value
        assert len(exc.reasons) == 3

    def test_error_attributes_populated(self) -> None:
        with pytest.raises(CommercialPreflightFailed) as exc_info:
            assert_commercial_ready(
                adapter_name="planet",
                source_id="planet-ps-orthotile",
                allow_paid_order=False,
                commercial_readiness_record_id=None,
                commercial_state="commercial_blocked",
            )

        exc = exc_info.value
        assert exc.adapter_name == "planet"
        assert exc.source_id == "planet-ps-orthotile"
        assert isinstance(exc.reasons, list)
        assert len(exc.reasons) > 0

    def test_custom_commercial_blocked_value_respected(self) -> None:
        """Custom blocked sentinel value is honoured."""
        # Should not raise when using custom blocked value and state does not match it
        assert_commercial_ready(
            adapter_name="test",
            source_id="test-source",
            allow_paid_order=True,
            commercial_readiness_record_id="rec-001",
            commercial_state="default_blocked",  # not the custom blocked value
            commercial_blocked_value="custom_blocked",
        )

    def test_custom_commercial_blocked_value_blocks_when_matched(self) -> None:
        with pytest.raises(CommercialPreflightFailed):
            assert_commercial_ready(
                adapter_name="test",
                source_id="test-source",
                allow_paid_order=True,
                commercial_readiness_record_id="rec-001",
                commercial_state="custom_blocked",
                commercial_blocked_value="custom_blocked",
            )


# ---------------------------------------------------------------------------
# 9. SOURCE_REGISTRY coverage — every provider_adapter must resolve
# ---------------------------------------------------------------------------


class TestSourceRegistryAdapterCoverage:
    """Every distinct provider_adapter value in SOURCE_REGISTRY must resolve."""

    def test_all_source_registry_provider_adapters_resolve(self) -> None:
        from akasha_ingest.source_registry import SOURCE_REGISTRY

        seen_adapters: set[str] = set()
        for source_id, row in SOURCE_REGISTRY.items():
            adapter_key = row.provider_adapter
            if adapter_key in seen_adapters:
                continue
            seen_adapters.add(adapter_key)
            adapter = get_provider_adapter(adapter_key)
            assert adapter.adapter_name == adapter_key, (
                f"source_id={source_id!r}: adapter_name mismatch: "
                f"expected {adapter_key!r}, got {adapter.adapter_name!r}"
            )
