"""Bhoonidhi provider adapter — thin wrapper around BhoonidhiClient.

Implements TASK-009 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Design notes
------------
- Wraps the existing ``BhoonidhiClient``, ``candidate_from_item``,
  ``source_collection``, ``build_search_manifest``, and ``write_manifest``
  helpers without refactoring them.
- Satisfies the ``ProviderAdapter`` protocol from ``base.py``.
- Fails closed for order/poll_order/cancel_order — Bhoonidhi is a free direct-
  download catalogue; no commercial order workflow exists.
- No network calls at import time or in the constructor.
- Constructor accepts an injected ``BhoonidhiClient``-compatible object so unit
  tests can supply a stub without hitting the real API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..bhoonidhi import (
    BhoonidhiAuthError,
    BhoonidhiClient,
    BhoonidhiDownloadUnavailable,
    BhoonidhiError,
    candidate_from_item,
    source_collection,
)
from .base import (
    CandidateItem,
    DownloadRequest,
    DownloadResult,
    NormalizedCandidate,
    OrderCancelResult,
    OrderPollResult,
    OrderRequest,
    OrderResult,
    PaginationMeta,
    ProviderActionUnsupported,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    QuotaPreflightRequest,
    QuotaPreflightResult,
    RateLimitMeta,
    ResumableState,
    SearchRequest,
    SearchResult,
    TokenRefreshMeta,
)

_ADAPTER_NAME = "bhoonidhi"


def _bbox_to_geometry(bbox: list[float]) -> dict[str, Any]:
    """Convert [W, S, E, N] bbox to a GeoJSON Polygon geometry."""
    w, s, e, n = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def _datetime_range_str(request: SearchRequest) -> str:
    """Build the ISO-8601 interval string expected by BhoonidhiClient.search."""
    dt_from = request.datetime_from or "1970-01-01T00:00:00Z"
    dt_to = request.datetime_to or "9999-12-31T23:59:59Z"
    return f"{dt_from}/{dt_to}"


def _intersects_geometry(request: SearchRequest) -> dict[str, Any]:
    """Extract the GeoJSON geometry for the spatial filter."""
    if request.aoi_geojson:
        geo = request.aoi_geojson
        # Unwrap Feature → geometry
        if isinstance(geo, dict) and geo.get("type") == "Feature":
            return geo.get("geometry") or geo
        return geo
    if request.bbox:
        return _bbox_to_geometry(request.bbox)
    raise ProviderError(
        "BhoonidhiAdapter.search requires aoi_geojson or bbox in the SearchRequest."
    )


def _candidate_to_base_item(raw: dict[str, Any]) -> CandidateItem:
    """Map a dict returned by ``candidate_from_item`` to a ``CandidateItem``."""
    props: dict[str, Any] = raw.get("properties") or {}
    online_raw = raw.get("online")
    if isinstance(online_raw, bool):
        online = online_raw
    else:
        online = str(online_raw or "").strip().upper() == "Y"

    cloud_cover: float | None = None
    for key in ("eo:cloud_cover", "cloudCover", "cloud_cover"):
        val = props.get(key)
        if val is not None:
            try:
                cloud_cover = float(val)
                break
            except (TypeError, ValueError):
                pass

    size_bytes: int | None = None
    for key in ("fileSize", "file_size", "size"):
        val = props.get(key)
        if val is not None:
            try:
                size_bytes = int(val)
                break
            except (TypeError, ValueError):
                pass

    return CandidateItem(
        provider_item_id=str(raw.get("item_id") or ""),
        raw_properties=props,
        acquisition_datetime=raw.get("datetime"),
        bbox=raw.get("bbox"),
        cloud_cover_pct=cloud_cover,
        online=online,
        download_size_bytes=size_bytes,
        estimated_cost_units=0.0,
    )


class BhoonidhiAdapter:
    """ProviderAdapter wrapping the Bhoonidhi (ISRO) direct-download catalogue.

    Parameters
    ----------
    client:
        Optional pre-constructed ``BhoonidhiClient`` (or compatible stub).
        When ``None`` (the default), a ``BhoonidhiClient`` is constructed
        lazily on the first call that needs it, using env-sourced credentials.
    """

    adapter_name: str = _ADAPTER_NAME

    def __init__(self, client: BhoonidhiClient | None = None) -> None:
        self._client: BhoonidhiClient | None = client
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> BhoonidhiClient:
        if self._closed:
            raise ProviderError("BhoonidhiAdapter has been closed; create a new instance.")
        if self._client is None:
            # Lazy construction — no network call here; BhoonidhiClient.__init__
            # does not make any network requests.
            self._client = BhoonidhiClient()
        return self._client

    # ------------------------------------------------------------------
    # Required protocol methods
    # ------------------------------------------------------------------

    def search(self, request: SearchRequest) -> SearchResult:
        """Query Bhoonidhi for available ISRO scenes.

        Maps ``SearchRequest`` → ``BhoonidhiClient.search`` → ``SearchResult``.
        Pagination is already consumed internally by ``BhoonidhiClient.search``
        (it follows ``next`` links automatically), so the result is always a
        single page containing all items.
        """
        client = self._get_client()
        collection = request.collection or source_collection(request.source_id)
        datetime_range = _datetime_range_str(request)
        intersects = _intersects_geometry(request)

        try:
            raw_items: list[dict[str, Any]] = client.search(
                collection=collection,
                datetime_range=datetime_range,
                intersects=intersects,
                limit=request.max_results,
            )
        except BhoonidhiAuthError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except BhoonidhiError as exc:
            msg = str(exc)
            if "429" in msg or "rate" in msg.lower():
                raise ProviderRateLimitError(_ADAPTER_NAME) from exc
            raise ProviderError(f"Bhoonidhi search error: {exc}") from exc

        aoi_bbox: list[float] | None = request.bbox
        if not aoi_bbox and request.aoi_geojson:
            aoi_bbox = request.aoi_geojson.get("bbox")  # type: ignore[union-attr]

        candidates: list[CandidateItem] = []
        for raw_item in raw_items:
            raw_candidate = candidate_from_item(raw_item, aoi_bbox)
            candidates.append(_candidate_to_base_item(raw_candidate))

        return SearchResult(
            source_id=request.source_id,
            candidates=candidates,
            pagination=PaginationMeta(
                next_page_token=None,
                has_more=False,
                total_count=len(candidates),
            ),
            rate_limit=RateLimitMeta(),
            token_refresh=TokenRefreshMeta(),
        )

    def normalize_candidate(
        self,
        item: CandidateItem,
        source_id: str,
        request: SearchRequest,
    ) -> NormalizedCandidate:
        """Translate a raw ``CandidateItem`` to a ``NormalizedCandidate``.

        The deterministic ``item_id`` is derived from the provider item ID (the
        STAC item id returned by Bhoonidhi), which already encodes
        satellite/date/tile in ISRO naming conventions.  Downstream deduplication
        uses this value.
        """
        provider_id = item.provider_item_id
        props = item.raw_properties or {}

        # Best-effort acquisition datetime — prefer properties, fall back to
        # item-level field.
        acq_dt: str = (
            item.acquisition_datetime
            or props.get("datetime")
            or props.get("acquisitionDate")
            or ""
        )

        bbox: list[float] = item.bbox or []

        aoi_bbox: list[float] | None = request.bbox
        if not aoi_bbox and request.aoi_geojson:
            aoi_bbox = request.aoi_geojson.get("bbox")  # type: ignore[union-attr]

        intersects_aoi: bool = False
        if bbox and aoi_bbox and len(bbox) == 4 and len(aoi_bbox) == 4:
            # Simple bbox overlap test (already computed by candidate_from_item,
            # but we recompute here to keep normalize_candidate self-contained).
            w1, s1, e1, n1 = bbox
            w2, s2, e2, n2 = aoi_bbox
            intersects_aoi = not (e1 <= w2 or e2 <= w1 or n1 <= s2 or n2 <= s1)

        # Build extra metadata from raw properties; exclude fields already
        # promoted to first-class NormalizedCandidate attributes.
        extra: dict[str, Any] = {
            k: v
            for k, v in props.items()
            if k not in {"datetime", "acquisitionDate", "eo:cloud_cover", "cloudCover",
                         "cloud_cover", "fileSize", "file_size", "size", "Online", "online"}
        }
        extra["bhoonidhi_collection"] = request.collection or source_collection(source_id)

        return NormalizedCandidate(
            source_id=source_id,
            provider_item_id=provider_id,
            item_id=provider_id,
            acquisition_datetime=acq_dt,
            bbox=bbox,
            intersects_aoi=intersects_aoi,
            cloud_cover_pct=item.cloud_cover_pct,
            online=item.online if item.online is not None else True,
            download_size_bytes=item.download_size_bytes,
            estimated_cost_units=0.0,
            download_links=list(item.download_links),
            extra=extra,
        )

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Download one Bhoonidhi product to ``dest_dir``.

        Maps ``DownloadRequest`` → ``BhoonidhiClient.download_product``.
        The destination filename is derived from the provider item ID.
        """
        client = self._get_client()
        candidate = request.candidate
        provider_id = candidate.provider_item_id
        collection = candidate.extra.get("bhoonidhi_collection") or source_collection(
            candidate.source_id
        )

        dest_dir = Path(request.dest_dir)
        dest_path = dest_dir / f"{provider_id}.zip"

        if request.dry_run:
            return DownloadResult(
                item_id=candidate.item_id,
                provider_item_id=provider_id,
                success=False,
                local_path=None,
                downloaded_bytes=0,
                resume_state=ResumableState(),
                dry_run=True,
            )

        try:
            result = client.download_product(
                product_id=provider_id,
                collection=collection,
                destination=dest_path,
            )
        except BhoonidhiAuthError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except BhoonidhiDownloadUnavailable as exc:
            return DownloadResult(
                item_id=candidate.item_id,
                provider_item_id=provider_id,
                success=False,
                local_path=None,
                downloaded_bytes=0,
                resume_state=ResumableState(
                    idempotent=True,
                    last_failure_reason=str(exc),
                ),
                failure_reason=str(exc),
            )
        except BhoonidhiError as exc:
            msg = str(exc)
            if "429" in msg or "rate" in msg.lower():
                raise ProviderRateLimitError(_ADAPTER_NAME) from exc
            raise ProviderError(f"Bhoonidhi download error: {exc}") from exc

        success = result.get("status") in {"downloaded", "exists"}
        local_path = result.get("path")
        downloaded_bytes = int(result.get("bytes") or 0)

        return DownloadResult(
            item_id=candidate.item_id,
            provider_item_id=provider_id,
            success=success,
            local_path=local_path,
            downloaded_bytes=downloaded_bytes,
            resume_state=ResumableState(
                idempotent=True,
                attempt_count=(request.resume_state.attempt_count + 1)
                if request.resume_state
                else 1,
            ),
            rate_limit=RateLimitMeta(),
            token_refresh=TokenRefreshMeta(),
        )

    def close(self) -> None:
        """Release the Bhoonidhi session (idempotent)."""
        if self._closed:
            return
        self._closed = True
        if self._client is not None:
            try:
                self._client.logout(ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Optional protocol methods — fail closed (Bhoonidhi has no order API)
    # ------------------------------------------------------------------

    def order(self, request: OrderRequest) -> OrderResult:
        raise ProviderActionUnsupported(_ADAPTER_NAME, "order")

    def poll_order(self, provider_order_id: str) -> OrderPollResult:
        raise ProviderActionUnsupported(_ADAPTER_NAME, "poll_order")

    def cancel_order(self, provider_order_id: str) -> OrderCancelResult:
        raise ProviderActionUnsupported(_ADAPTER_NAME, "cancel_order")

    def quota_preflight(self, request: QuotaPreflightRequest) -> QuotaPreflightResult:
        return QuotaPreflightResult(available=False, not_supported=True)
