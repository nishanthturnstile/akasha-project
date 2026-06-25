"""Typed provider adapter contract for the Akasha ingestion scheduler.

Implements TASK-007 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Design principles
-----------------
- Synchronous-first: all protocol methods are blocking/sync; async wrapping is the
  responsibility of the caller (orchestrator), not the adapter.
- Fail-closed: unsupported optional methods raise ``ProviderActionUnsupported``;
  commercial preflights raise ``CommercialPreflightFailed`` before any paid call.
- No heavy deps: dataclasses + StrEnum + typing.Protocol; no requests/httpx/pydantic.
- Pagination, rate-limit backoff, token-refresh, resumable download idempotency,
  quota/cost preflight, and order-lifecycle state are first-class fields — adapters
  must populate what they know; callers must not assume fields are always populated.

Layered type hierarchy
----------------------
::

    SearchRequest
        ↓  adapter.search()
    SearchResult          (page of CandidateItem + PaginationMeta + RateLimitMeta)
        ↓  adapter.normalize_candidate()
    NormalizedCandidate
        ↓  adapter.download()
    DownloadResult        (local path + ResumableState + idempotency)

    OrderRequest
        ↓  adapter.order()
    OrderResult           (OrderState lifecycle)
        ↓  adapter.poll_order()
    OrderPollResult
        ↓  adapter.cancel_order()
    OrderCancelResult

Exceptions
----------
``ProviderActionUnsupported``   — raised by default stub implementations for
                                  optional methods the concrete adapter does not support.
``CommercialPreflightFailed``   — raised before any quota/cost-incurring call when
                                  commercial-readiness criteria are not met.
``ProviderAuthError``           — raised when token refresh or credential lookup fails.
``ProviderRateLimitError``      — raised when a hard rate-limit is exceeded and the
                                  caller should not retry immediately.
``ProviderError``               — base class for all provider-layer errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Exceptions — fail-closed contract (SEC-005, SEC-007)
# ---------------------------------------------------------------------------


class ProviderError(RuntimeError):
    """Base class for all provider-adapter errors."""


class ProviderActionUnsupported(ProviderError):
    """Raised when a concrete adapter does not support an optional action.

    Example::

        raise ProviderActionUnsupported("bhoonidhi", "order")
    """

    def __init__(self, adapter_name: str, action: str) -> None:
        super().__init__(
            f"Provider adapter '{adapter_name}' does not support action '{action}'. "
            "Ensure the source capabilities list does not advertise this action, "
            "or implement the method before calling it."
        )
        self.adapter_name = adapter_name
        self.action = action


class CommercialPreflightFailed(ProviderError):
    """Raised before any quota/cost-incurring call when readiness criteria fail.

    Enforces SEC-007: commercial order APIs require ALL of —
    - ``CommercialState != commercial_blocked``
    - ``allow_paid_order = True`` flag passed by operator
    - explicit preflight record documenting the approval

    Example::

        raise CommercialPreflightFailed(
            adapter_name="planet",
            source_id="planet-ps-orthotile-l3h",
            reasons=["commercial_blocked", "allow_paid_order not set"],
        )
    """

    def __init__(
        self,
        adapter_name: str,
        source_id: str,
        reasons: list[str],
    ) -> None:
        reason_str = "; ".join(reasons)
        super().__init__(
            f"Commercial preflight failed for adapter '{adapter_name}' "
            f"source '{source_id}': {reason_str}. "
            "Set allow_paid_order=True and ensure commercial_state=approved "
            "with a documented readiness record before placing paid orders."
        )
        self.adapter_name = adapter_name
        self.source_id = source_id
        self.reasons = reasons


class ProviderAuthError(ProviderError):
    """Raised when token refresh or credential lookup fails."""


class ProviderRateLimitError(ProviderError):
    """Raised when a hard rate-limit is exceeded; caller should back off.

    ``retry_after_seconds`` is advisory and may be ``None`` if the provider
    does not return a Retry-After header or equivalent.
    """

    def __init__(self, adapter_name: str, retry_after_seconds: float | None = None) -> None:
        msg = f"Rate limit exceeded for provider '{adapter_name}'."
        if retry_after_seconds is not None:
            msg += f" Retry after {retry_after_seconds:.1f}s."
        super().__init__(msg)
        self.adapter_name = adapter_name
        self.retry_after_seconds = retry_after_seconds


# ---------------------------------------------------------------------------
# Order lifecycle state
# ---------------------------------------------------------------------------


class OrderState(StrEnum):
    """Lifecycle states for provider-side orders/tasks (future commercial providers).

    Not all providers expose every state.  Adapters must map provider-specific
    status strings to the closest canonical state and set ``raw_state`` for detail.
    """

    PENDING = "pending"
    """Order submitted; provider has not yet started processing."""

    QUEUED = "queued"
    """Order accepted and queued by provider."""

    RUNNING = "running"
    """Provider is actively processing the order."""

    SUCCEEDED = "succeeded"
    """Order completed; assets are ready for download."""

    FAILED = "failed"
    """Order failed; ``failure_reason`` should be populated."""

    CANCELLED = "cancelled"
    """Order was cancelled by operator or provider."""

    EXPIRED = "expired"
    """Order expired before completion (provider TTL)."""

    UNKNOWN = "unknown"
    """Provider returned an unrecognised state; inspect ``raw_state``."""


# ---------------------------------------------------------------------------
# Pagination metadata
# ---------------------------------------------------------------------------


@dataclass
class PaginationMeta:
    """Pagination state returned with every search result page.

    Adapters fill whichever fields the provider exposes; callers must handle
    ``None`` as "information not available" — not as "no more pages".
    The only reliable "end of results" signal is ``next_page_token is None``
    together with ``has_more == False`` (or ``has_more is None`` and an empty page).
    """

    # Token/cursor to pass in the next SearchRequest to retrieve the next page.
    # None means this is the last page (or provider does not support pagination).
    next_page_token: str | None = None

    # Whether the provider explicitly indicates more pages are available.
    has_more: bool = False

    # Total result count across all pages, if provider returns it.
    total_count: int | None = None

    # Current page number (1-based), if provider returns it.
    page_number: int | None = None

    # Page size used by provider for this response.
    page_size: int | None = None


# ---------------------------------------------------------------------------
# Rate-limit / backoff metadata
# ---------------------------------------------------------------------------


@dataclass
class RateLimitMeta:
    """Rate-limit / backoff advisory returned alongside provider API responses.

    All fields are advisory; callers may ignore fields they do not recognise.
    Adapters must raise ``ProviderRateLimitError`` when a hard limit is hit
    (e.g. HTTP 429 with no usable Retry-After) *in addition to* returning
    these fields on partial responses.
    """

    # Seconds to wait before the next request is allowed (Retry-After equivalent).
    retry_after_seconds: float | None = None

    # Remaining request quota in current window, if provider exposes it.
    requests_remaining: int | None = None

    # Quota reset time (Unix epoch), if provider exposes it.
    quota_reset_at: float | None = None

    # Whether the scheduler should apply exponential back-off on this response.
    # Adapters set this on soft throttle signals (e.g. 503 / slow response).
    suggest_backoff: bool = False

    # Provider-specific throttle hint string for logging/debugging.
    raw_throttle_hint: str | None = None


# ---------------------------------------------------------------------------
# Token refresh metadata
# ---------------------------------------------------------------------------


@dataclass
class TokenRefreshMeta:
    """Token / credential refresh state surfaced by the adapter after a call.

    Adapters that perform automatic token refresh (e.g. OAuth2 credential flow)
    populate this so the scheduler can persist updated tokens without re-authenticating.
    """

    # Whether a token refresh occurred during this call.
    refreshed: bool = False

    # New access token, if refreshed.  Must be treated as a secret; never log.
    new_access_token: str | None = None

    # New refresh token, if the provider rotates refresh tokens.
    new_refresh_token: str | None = None

    # Expiry of the new access token (Unix epoch).
    new_expires_at: float | None = None

    # Whether the refresh itself failed (adapter may have fallen back to an older token).
    refresh_failed: bool = False

    # Reason for refresh failure, if any (redacted error string).
    refresh_failure_reason: str | None = None


# ---------------------------------------------------------------------------
# Search request / result
# ---------------------------------------------------------------------------


@dataclass
class SearchRequest:
    """Parameters for a provider search call.

    Only ``source_id`` and ``collection`` are required; all other fields are
    optional and may be ignored by providers that do not support them.
    """

    # Akasha source identifier (e.g. "resourcesat-2a-liss3-boa").
    source_id: str

    # Provider-specific collection name (e.g. "ResourceSat-2A_LISS3_BOA").
    collection: str

    # ISO-8601 datetime range strings for the search window.
    datetime_from: str | None = None
    datetime_to: str | None = None

    # GeoJSON geometry dict (polygon/bbox) for spatial filter.
    aoi_geojson: dict[str, Any] | None = None

    # Bounding-box as [min_lon, min_lat, max_lon, max_lat].
    bbox: list[float] | None = None

    # Maximum number of results to return per page.
    max_results: int = 100

    # Pagination token from PaginationMeta.next_page_token of a previous call.
    page_token: str | None = None

    # Provider-specific extra filters (e.g. cloud-cover threshold, Online=Y).
    extra_filters: dict[str, Any] = field(default_factory=dict)

    # Scheduler job identifier for traceability (not sent to provider).
    job_id: str | None = None


@dataclass
class CandidateItem:
    """Raw provider search result item, before normalisation.

    Adapters must return at minimum ``provider_item_id`` and ``raw_properties``.
    All other fields are best-effort; callers must tolerate ``None``.
    """

    # Unique item identifier as returned by the provider.
    provider_item_id: str

    # Full raw properties dict from provider (may contain sensitive fields).
    raw_properties: dict[str, Any]

    # Acquisition datetime string as returned by provider (ISO-8601 or provider format).
    acquisition_datetime: str | None = None

    # Bounding box [min_lon, min_lat, max_lon, max_lat] in WGS-84.
    bbox: list[float] | None = None

    # Cloud-cover percentage [0–100] if provider returns it.
    cloud_cover_pct: float | None = None

    # Whether the item is currently available for direct download.
    online: bool | None = None

    # Download size in bytes if known at search time.
    download_size_bytes: int | None = None

    # Estimated cost/quota units for downloading this item (0 for free sources).
    estimated_cost_units: float | None = None

    # Provider-specific asset download URLs; must be redacted before persisting.
    download_links: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Result of a single provider search call (one page)."""

    # Source identifier echoed from the request.
    source_id: str

    # Raw candidate items returned by the provider for this page.
    candidates: list[CandidateItem]

    # Pagination state for follow-up calls.
    pagination: PaginationMeta = field(default_factory=PaginationMeta)

    # Rate-limit advisory from this response.
    rate_limit: RateLimitMeta = field(default_factory=RateLimitMeta)

    # Token refresh information from this call, if applicable.
    token_refresh: TokenRefreshMeta = field(default_factory=TokenRefreshMeta)

    # Provider-level error or warning message (non-fatal; page may be partial).
    provider_warning: str | None = None

    # True if the search itself was a dry-run and no network call was made.
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Normalized candidate
# ---------------------------------------------------------------------------


@dataclass
class NormalizedCandidate:
    """Provider-agnostic candidate after adapter normalisation.

    This is the shape that flows into selection, download, and manifest stages.
    Adapters translate provider-specific field names into Akasha canonical names here.
    """

    # Akasha source identifier.
    source_id: str

    # Provider-specific item ID (preserved for downstream deduplication).
    provider_item_id: str

    # Deterministic Akasha item ID: ``{satellite}:{level}:{tile}:{datetime}:{baseline}``.
    item_id: str

    # Acquisition datetime (UTC ISO-8601).
    acquisition_datetime: str

    # Bounding box [min_lon, min_lat, max_lon, max_lat].
    bbox: list[float]

    # Whether item falls within or intersects the target AOI.
    intersects_aoi: bool

    # Cloud-cover percentage [0–100].  None = not available.
    cloud_cover_pct: float | None = None

    # True if provider reports item as immediately downloadable.
    online: bool = True

    # Estimated download size in bytes.
    download_size_bytes: int | None = None

    # Estimated cost/quota units (0 = free).
    estimated_cost_units: float = 0.0

    # Provider-specific download links; redacted before persisting.
    download_links: list[str] = field(default_factory=list)

    # Additional provenance/metadata from normalisation.
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Resumable download state / idempotency
# ---------------------------------------------------------------------------


@dataclass
class ResumableState:
    """State for resumable or idempotent download of a single asset.

    Adapters that support HTTP range-request resumption or server-side
    download tasks populate this so the orchestrator can resume interrupted
    downloads without re-requesting from byte 0.
    """

    # Byte offset to resume from (0 = start from beginning).
    resume_offset_bytes: int = 0

    # ETag or content-hash from a previous partial download (for validation).
    etag: str | None = None

    # Provider-specific download session or task ID (for server-side tasking).
    provider_session_id: str | None = None

    # Whether this download can be safely retried without data loss.
    idempotent: bool = True

    # Number of times this download has been attempted.
    attempt_count: int = 0

    # Last failure reason (short string; must not contain secrets).
    last_failure_reason: str | None = None


# ---------------------------------------------------------------------------
# Download request / result
# ---------------------------------------------------------------------------


@dataclass
class DownloadRequest:
    """Parameters for a provider download call."""

    # Normalized candidate to download.
    candidate: NormalizedCandidate

    # Local destination directory.
    dest_dir: str

    # Resumable state from a previous attempt, if any.
    resume_state: ResumableState | None = None

    # Whether to skip the download and only return a ResumableState estimate.
    dry_run: bool = False

    # Scheduler job identifier for traceability.
    job_id: str | None = None

    # Maximum allowed download size in bytes (0 = no limit).
    max_size_bytes: int = 0


@dataclass
class DownloadResult:
    """Result of a provider download call for one asset/candidate."""

    # Akasha item ID.
    item_id: str

    # Provider item ID.
    provider_item_id: str

    # True if the file is fully written to ``local_path``.
    success: bool

    # Absolute local path to the downloaded file; ``None`` on failure or dry-run.
    local_path: str | None

    # Actual downloaded size in bytes (may differ from estimate).
    downloaded_bytes: int = 0

    # Updated resumable state after this attempt.
    resume_state: ResumableState = field(default_factory=ResumableState)

    # Rate-limit advisory from this call.
    rate_limit: RateLimitMeta = field(default_factory=RateLimitMeta)

    # Token refresh information from this call.
    token_refresh: TokenRefreshMeta = field(default_factory=TokenRefreshMeta)

    # Failure reason (short, redacted string).  None on success.
    failure_reason: str | None = None

    # Whether this result came from a dry-run (no actual download).
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Order request / result / poll / cancel
# ---------------------------------------------------------------------------


@dataclass
class OrderRequest:
    """Parameters for a paid/tasked order call.

    The caller **must** perform commercial preflight checks (CommercialPreflightFailed)
    before constructing this object and calling ``adapter.order()``.
    """

    # Normalized candidate to order.
    candidate: NormalizedCandidate

    # Whether the operator has explicitly approved paid order execution.
    allow_paid_order: bool

    # Operator-provided commercial-readiness record ID for audit trail.
    commercial_readiness_record_id: str | None = None

    # Provider-specific order parameters.
    order_params: dict[str, Any] = field(default_factory=dict)

    # Scheduler job identifier for traceability.
    job_id: str | None = None


@dataclass
class OrderResult:
    """Result of a provider order/task submission."""

    # Akasha item ID.
    item_id: str

    # Provider-assigned order/task identifier.
    provider_order_id: str

    # Canonical order lifecycle state.
    state: OrderState

    # Raw provider state string (for debugging/logging).
    raw_state: str | None = None

    # Estimated completion time (Unix epoch), if provider returns it.
    estimated_ready_at: float | None = None

    # Estimated cost in provider quota units.
    estimated_cost_units: float | None = None

    # Provider-specific order metadata (may contain URLs; redact before persisting).
    order_metadata: dict[str, Any] = field(default_factory=dict)

    # Rate-limit advisory from this call.
    rate_limit: RateLimitMeta = field(default_factory=RateLimitMeta)

    # Token refresh information from this call.
    token_refresh: TokenRefreshMeta = field(default_factory=TokenRefreshMeta)

    # Failure reason if submission failed.
    failure_reason: str | None = None


@dataclass
class OrderPollResult:
    """Result of polling an existing provider order."""

    # Provider-assigned order ID being polled.
    provider_order_id: str

    # Current canonical order lifecycle state.
    state: OrderState

    # Raw provider state string.
    raw_state: str | None = None

    # True if the order is in a terminal state (SUCCEEDED/FAILED/CANCELLED/EXPIRED).
    terminal: bool = False

    # Download links available now (only populated when state == SUCCEEDED).
    download_links: list[str] = field(default_factory=list)

    # Failure reason if state == FAILED.
    failure_reason: str | None = None

    # Rate-limit advisory from this call.
    rate_limit: RateLimitMeta = field(default_factory=RateLimitMeta)

    # Token refresh information from this call.
    token_refresh: TokenRefreshMeta = field(default_factory=TokenRefreshMeta)


@dataclass
class OrderCancelResult:
    """Result of cancelling a provider order."""

    # Provider-assigned order ID that was cancelled.
    provider_order_id: str

    # True if the cancel request was accepted.
    accepted: bool

    # Canonical state after cancellation (usually CANCELLED or FAILED).
    state: OrderState

    # Provider message if any.
    provider_message: str | None = None

    # Rate-limit advisory from this call.
    rate_limit: RateLimitMeta = field(default_factory=RateLimitMeta)

    # Token refresh information from this call.
    token_refresh: TokenRefreshMeta = field(default_factory=TokenRefreshMeta)


# ---------------------------------------------------------------------------
# Quota / cost preflight
# ---------------------------------------------------------------------------


@dataclass
class QuotaPreflightRequest:
    """Parameters for a quota/cost preflight check before placing an order.

    Adapters that support preflight checks return a ``QuotaPreflightResult``
    without placing the actual order.  Adapters that cannot estimate cost
    must return ``QuotaPreflightResult(available=False, not_supported=True)``
    rather than raising an exception, so the caller can decide whether to proceed.
    """

    # Normalized candidate to preflight.
    candidate: NormalizedCandidate

    # Scheduler job identifier for traceability.
    job_id: str | None = None


@dataclass
class QuotaPreflightResult:
    """Result of a quota/cost preflight check."""

    # Whether the order can proceed based on quota/cost checks.
    available: bool

    # True if the adapter does not support preflight (caller decides how to handle).
    not_supported: bool = False

    # Estimated cost in provider quota units.
    estimated_cost_units: float | None = None

    # Current remaining quota, if provider exposes it.
    quota_remaining: float | None = None

    # Human-readable reason if ``available`` is False.
    unavailability_reason: str | None = None


# ---------------------------------------------------------------------------
# ProviderAdapter Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ProviderAdapter(Protocol):
    """Synchronous provider adapter contract for the Akasha ingestion scheduler.

    **Required methods** (all concrete adapters must implement):
    - ``search`` — query provider for available scenes/items.
    - ``normalize_candidate`` — translate a raw ``CandidateItem`` to a
      provider-agnostic ``NormalizedCandidate``.
    - ``download`` — download one item to local storage.
    - ``close`` — release any held resources (sessions, file handles, locks).

    **Optional methods** (raise ``ProviderActionUnsupported`` by default):
    - ``order`` — submit a paid/tasked order for an item.
    - ``poll_order`` — poll the state of a submitted order.
    - ``cancel_order`` — cancel a pending or running order.
    - ``quota_preflight`` — check quota/cost before placing an order.

    All methods are synchronous (blocking). The scheduler/orchestrator is
    responsible for thread-pool or async wrapping if concurrency is needed.

    Commercial guard (SEC-007)
    --------------------------
    Implementations of ``order`` **must** call ``_assert_commercial_ready``
    (or equivalent logic) before performing any network call that incurs cost.
    The base protocol provides ``_assert_commercial_ready`` as a default helper
    that raises ``CommercialPreflightFailed`` unless all criteria are met.
    """

    # Human-readable adapter name for logging/errors (e.g. "bhoonidhi").
    adapter_name: str

    def search(self, request: SearchRequest) -> SearchResult:
        """Query the provider for available scenes/items.

        Parameters
        ----------
        request:
            Structured search parameters.

        Returns
        -------
        SearchResult:
            One page of raw candidate items plus pagination/rate-limit metadata.

        Raises
        ------
        ProviderAuthError:
            If authentication fails and cannot be refreshed.
        ProviderRateLimitError:
            If a hard rate limit is encountered.
        ProviderError:
            For any other provider-level failure.
        """
        ...

    def normalize_candidate(
        self,
        item: CandidateItem,
        source_id: str,
        request: SearchRequest,
    ) -> NormalizedCandidate:
        """Translate a raw provider item into a canonical ``NormalizedCandidate``.

        Parameters
        ----------
        item:
            Raw candidate as returned by the provider search API.
        source_id:
            Akasha source identifier (e.g. ``"resourcesat-2a-liss3-boa"``).
        request:
            Original search request for context (AOI, datetime range).

        Returns
        -------
        NormalizedCandidate:
            Provider-agnostic candidate with deterministic ``item_id``.
        """
        ...

    def download(self, request: DownloadRequest) -> DownloadResult:
        """Download one item asset to local storage.

        Parameters
        ----------
        request:
            Download parameters including destination, resume state, and limits.

        Returns
        -------
        DownloadResult:
            Outcome including local path, bytes downloaded, and updated resume state.

        Raises
        ------
        ProviderAuthError:
            If authentication fails and cannot be refreshed.
        ProviderRateLimitError:
            If a hard rate limit is encountered.
        ProviderError:
            For any other provider-level failure.
        """
        ...

    def order(self, request: OrderRequest) -> OrderResult:
        """Submit a paid/tasked order for an item.

        **Default**: raises ``ProviderActionUnsupported``.
        Override in adapters that support commercial order workflows.

        Implementations **must**:
        1. Call ``_assert_commercial_ready(request)`` before any network call.
        2. Populate ``OrderResult.state`` using canonical ``OrderState`` values.

        Parameters
        ----------
        request:
            Order parameters including the candidate and commercial-readiness proof.

        Returns
        -------
        OrderResult:
            Submitted order state and provider order ID.

        Raises
        ------
        ProviderActionUnsupported:
            If this adapter does not support orders.
        CommercialPreflightFailed:
            If commercial-readiness criteria are not met.
        ProviderAuthError, ProviderRateLimitError, ProviderError:
            On provider-level failures.
        """
        raise ProviderActionUnsupported(self.adapter_name, "order")

    def poll_order(self, provider_order_id: str) -> OrderPollResult:
        """Poll the state of a previously submitted order.

        **Default**: raises ``ProviderActionUnsupported``.

        Parameters
        ----------
        provider_order_id:
            Provider-assigned order/task identifier from a prior ``order()`` call.

        Returns
        -------
        OrderPollResult:
            Current order state and, when SUCCEEDED, available download links.

        Raises
        ------
        ProviderActionUnsupported:
            If this adapter does not support order polling.
        """
        raise ProviderActionUnsupported(self.adapter_name, "poll_order")

    def cancel_order(self, provider_order_id: str) -> OrderCancelResult:
        """Cancel a pending or running order.

        **Default**: raises ``ProviderActionUnsupported``.

        Parameters
        ----------
        provider_order_id:
            Provider-assigned order/task identifier to cancel.

        Returns
        -------
        OrderCancelResult:
            Confirmation and terminal state after cancellation.

        Raises
        ------
        ProviderActionUnsupported:
            If this adapter does not support order cancellation.
        """
        raise ProviderActionUnsupported(self.adapter_name, "cancel_order")

    def quota_preflight(self, request: QuotaPreflightRequest) -> QuotaPreflightResult:
        """Check quota/cost before placing an order.

        **Default**: returns ``QuotaPreflightResult(available=False, not_supported=True)``.
        Override in adapters that support cost estimation.

        Parameters
        ----------
        request:
            Preflight check parameters.

        Returns
        -------
        QuotaPreflightResult:
            Estimated cost and quota availability.
        """
        return QuotaPreflightResult(available=False, not_supported=True)

    def close(self) -> None:
        """Release any held resources (sessions, file handles, locks).

        Called by the scheduler after all adapter calls for a job are complete.
        Must be safe to call multiple times (idempotent).
        """
        ...


# ---------------------------------------------------------------------------
# Commercial preflight helper (standalone function, usable by adapters)
# ---------------------------------------------------------------------------


def assert_commercial_ready(
    *,
    adapter_name: str,
    source_id: str,
    allow_paid_order: bool,
    commercial_readiness_record_id: str | None,
    commercial_state: str,
    commercial_blocked_value: str = "commercial_blocked",
) -> None:
    """Raise ``CommercialPreflightFailed`` if commercial-readiness criteria are not met.

    Adapters implementing ``order()`` must call this before any network request
    that incurs provider quota or cost charges (SEC-007).

    Parameters
    ----------
    adapter_name:
        Adapter name for error messages.
    source_id:
        Akasha source identifier for error messages.
    allow_paid_order:
        Explicit operator-provided flag; must be ``True``.
    commercial_readiness_record_id:
        Operator-provided audit record; must not be ``None``.
    commercial_state:
        Current commercial state string from ``SourceStateRow.commercial_state``.
    commercial_blocked_value:
        The string value that represents a blocked commercial state
        (default: ``"commercial_blocked"``).

    Raises
    ------
    CommercialPreflightFailed:
        If any criterion is not satisfied.
    """
    reasons: list[str] = []

    if commercial_state == commercial_blocked_value:
        reasons.append(f"commercial_state={commercial_state!r}")

    if not allow_paid_order:
        reasons.append("allow_paid_order is False or not set")

    if not commercial_readiness_record_id:
        reasons.append("commercial_readiness_record_id is missing")

    if reasons:
        raise CommercialPreflightFailed(
            adapter_name=adapter_name,
            source_id=source_id,
            reasons=reasons,
        )
