"""Shared base classes for placeholder (not-yet-implemented) provider adapters.

Provides two base classes:
- ``PlaceholderAdapterBase``: for free/non-commercial data providers where
  order/task flows are not needed.
- ``CommercialPlaceholderAdapterBase``: for commercial providers — enforces
  fail-closed semantics for ``order()`` / ``poll_order()`` / ``cancel_order()``
  via ``assert_commercial_ready`` with ``commercial_state="commercial_blocked"``.

All required protocol methods raise ``ProviderActionUnsupported`` until the
provider phase begins and a real implementation replaces this placeholder.
"""

from __future__ import annotations

from .base import (
    CandidateItem,
    CommercialPreflightFailed,  # noqa: F401 — re-exported for adapter clarity
    DownloadRequest,
    DownloadResult,
    NormalizedCandidate,
    OrderCancelResult,
    OrderPollResult,
    OrderRequest,
    OrderResult,
    ProviderActionUnsupported,
    QuotaPreflightRequest,
    QuotaPreflightResult,
    SearchRequest,
    SearchResult,
    assert_commercial_ready,
)

__all__ = [
    "PlaceholderAdapterBase",
    "CommercialPlaceholderAdapterBase",
]


class PlaceholderAdapterBase:
    """Stub base for free/open data provider adapters not yet implemented.

    Every method that the provider does not yet support raises
    ``ProviderActionUnsupported``.  ``close()`` is a safe no-op.
    Subclasses must override ``adapter_name``.
    """

    adapter_name: str = "placeholder"

    def search(self, request: SearchRequest) -> SearchResult:
        raise ProviderActionUnsupported(self.adapter_name, "search")

    def normalize_candidate(
        self,
        item: CandidateItem,
        source_id: str,
        request: SearchRequest,
    ) -> NormalizedCandidate:
        raise ProviderActionUnsupported(self.adapter_name, "normalize_candidate")

    def download(self, request: DownloadRequest) -> DownloadResult:
        raise ProviderActionUnsupported(self.adapter_name, "download")

    def order(self, request: OrderRequest) -> OrderResult:
        raise ProviderActionUnsupported(self.adapter_name, "order")

    def poll_order(self, provider_order_id: str) -> OrderPollResult:
        raise ProviderActionUnsupported(self.adapter_name, "poll_order")

    def cancel_order(self, provider_order_id: str) -> OrderCancelResult:
        raise ProviderActionUnsupported(self.adapter_name, "cancel_order")

    def quota_preflight(self, request: QuotaPreflightRequest) -> QuotaPreflightResult:
        return QuotaPreflightResult(available=False, not_supported=True)

    def close(self) -> None:
        pass  # no resources held in placeholder


class CommercialPlaceholderAdapterBase(PlaceholderAdapterBase):
    """Stub base for commercial provider adapters not yet implemented.

    Overrides ``order()`` to call ``assert_commercial_ready`` with
    ``commercial_state="commercial_blocked"`` *before* raising
    ``ProviderActionUnsupported``, ensuring that:

    1. ``CommercialPreflightFailed`` is raised for any attempt with valid
       credentials because the commercial state is always blocked in this stub.
    2. If somehow preflight passes in future (state changed in subclass), the
       method still raises ``ProviderActionUnsupported`` until implemented.

    This satisfies SEC-007: paid actions are impossible by default.
    """

    def order(self, request: OrderRequest) -> OrderResult:
        assert_commercial_ready(
            adapter_name=self.adapter_name,
            source_id=request.candidate.source_id,
            allow_paid_order=request.allow_paid_order,
            commercial_readiness_record_id=request.commercial_readiness_record_id,
            commercial_state="commercial_blocked",
        )
        # assert_commercial_ready always raises above because commercial_state
        # is hardcoded to "commercial_blocked".  This line is unreachable in
        # placeholder state but makes the intent explicit for future implementors.
        raise ProviderActionUnsupported(self.adapter_name, "order")
