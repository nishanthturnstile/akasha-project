"""Canonical manifest schema helpers for the Akasha ingestion scheduler.

Implements TASK-013 through TASK-016 from
docs/impl-plan/architecture-satellite-ingestion-scheduler-1.md.

Manifest types
--------------
- ``SearchManifest``   — output of a provider search pass: candidates found,
  providerQuery, selection criteria, redacted provider properties and links.
- ``DownloadManifest`` — outcome of download/fetch pass: downloaded items,
  failures with error-kind taxonomy, deferred items with retry metadata.
- ``OrderManifest``    — future commercial/tasked-order lifecycle: order state,
  cost metadata, provider order IDs.  No current adapter uses this; it is
  defined now so downstream stages can declare schema expectations.

Design principles
-----------------
- stdlib dataclasses + StrEnum + typing only; no Pydantic.
- Redaction is deterministic, applied before any manifest is written to disk or
  surfaced by an API.  Redact-then-write; never write-then-redact.
- Versioning and migration helpers ensure forward-compatibility: callers load
  via ``load_manifest_dict`` which applies any needed migrations before parsing.
- Legacy Bhoonidhi manifest helpers (``bhoonidhi.build_search_manifest``,
  ``bhoonidhi.write_manifest``) are preserved unchanged; this module is the new
  canonical layer above them (SEC-002, REQ-007).
- No broad silent failures: validation raises ``ManifestValidationError`` with
  a list of all missing/invalid fields so callers can produce actionable errors.

Redaction coverage (SEC-002)
-----------------------------
Passwords, tokens, bearer headers, API keys, signed URL query secrets,
provider usernames, and secret-looking nested keys are removed/masked.
The ``REDACTED`` sentinel ``"<redacted>"`` is used so downstream code can
distinguish a redacted value from a missing value without needing ``None``.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_MANIFEST_VERSION = 1
DOWNLOAD_MANIFEST_VERSION = 1
ORDER_MANIFEST_VERSION = 1

# Sentinel placed in-position for every redacted value.
REDACTED = "<redacted>"

# Current redaction-rule set version.  Bump when new redaction rules are added
# so manifests on disk can be re-redacted idempotently when rules change.
REDACTION_VERSION = 1


# ---------------------------------------------------------------------------
# StrEnums
# ---------------------------------------------------------------------------


class ManifestType(StrEnum):
    SEARCH = "search"
    DOWNLOAD = "download"
    ORDER = "order"


class DownloadStatus(StrEnum):
    """Per-candidate download lifecycle state tracked in search manifests."""

    PENDING = "pending"
    """Candidate identified; download not yet attempted."""

    DOWNLOADED = "downloaded"
    """File fully written to local storage."""

    FAILED = "failed"
    """Download attempted but failed; see FailedEntry for detail."""

    DEFERRED = "deferred"
    """Download deferred to a later run; see DeferredEntry.defer_reason."""

    SKIPPED = "skipped"
    """Candidate excluded from download by selection criteria."""

    NOT_ONLINE = "not_online"
    """Provider reported item not currently available for direct download."""


class ErrorKind(StrEnum):
    """Taxonomy of download failure categories.

    Kept narrow so monitoring can aggregate across providers without free-text parsing.
    """

    AUTH = "auth"
    """Provider authentication or authorisation failure."""

    NOT_FOUND = "not_found"
    """Item/asset no longer available at the provider (404 or equivalent)."""

    NOT_ONLINE = "not_online"
    """Provider reports item exists but is not currently available for download."""

    RATE_LIMITED = "rate_limited"
    """Provider returned a rate-limit or quota response."""

    NETWORK = "network"
    """Transient network error (timeout, connection reset, DNS)."""

    CHECKSUM = "checksum"
    """Downloaded file failed integrity/checksum verification."""

    SIZE_LIMIT = "size_limit"
    """File size exceeds configured per-item or per-run size budget."""

    DISK = "disk"
    """Local disk / storage write failure."""

    PROVIDER = "provider"
    """Provider returned a non-retryable server error."""

    UNKNOWN = "unknown"
    """Uncategorised failure; inspect ``redacted_error`` for detail."""


class OrderLifecycleState(StrEnum):
    """Lifecycle states for commercial/tasked provider orders.

    Mirrors ``providers.base.OrderState``; defined here so downstream manifest
    parsing does not need to import the provider layer.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Redaction utilities  (SEC-002)
# ---------------------------------------------------------------------------

# Dict keys that are always redacted, regardless of nesting depth.
_SECRET_KEY_EXACT: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pass",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "api_secret",
        "client_secret",
        "client_id",
        "bearer",
        "authorization",
        "username",
        "userid",
        "user_id",
        "secret",
        "private_key",
        "signing_key",
        "x-amz-security-token",
        "x-amz-credential",
        "awsaccesskeyid",
        "session_token",
        "sessiontoken",
        "credential",
    }
)

# Dict key suffixes that indicate secret values.
_SECRET_KEY_SUFFIXES: tuple[str, ...] = (
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_apikey",
    "_credential",
    "_bearer",
    "_key",
)

# Dict key prefixes that indicate secret values.
_SECRET_KEY_PREFIXES: tuple[str, ...] = (
    "x-amz-",
    "x-goog-",
)

# URL query-parameter names whose presence in a URL indicates a signed/temporary URL.
_SIGNED_URL_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "x-amz-signature",
        "x-goog-signature",
        "signature",
        "x-amz-security-token",
        "x-amz-credential",
        "awsaccesskeyid",
        "x-amz-date",
        "policy",
        "x-goog-date",
        "x-goog-credential",
        "x-goog-algorithm",
        "token",
        "access_token",
        "auth",
    }
)

# Regex that matches Bearer/Basic/Token header values in strings.
_AUTH_HEADER_RE = re.compile(
    r"((?:Bearer|Basic|Token)\s+)[A-Za-z0-9+/=._\-]{8,}",
    re.IGNORECASE,
)

# Regex for candidate URL-like secrets embedded in strings (e.g. ?token=abc).
_URL_SECRET_RE = re.compile(
    r"([?&](?:token|access_token|api_key|apikey|key|password|secret|credential"
    r"|x-amz-signature|x-goog-signature|signature)=)[^&\s\"']+",
    re.IGNORECASE,
)


def _is_secret_key(key: str) -> bool:
    """Return True if *key* matches a known secret-field pattern."""
    lower = key.lower()
    if lower in _SECRET_KEY_EXACT:
        return True
    for suffix in _SECRET_KEY_SUFFIXES:
        if lower.endswith(suffix):
            return True
    for prefix in _SECRET_KEY_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False


def _is_signed_url(url: str) -> bool:
    """Return True if *url* looks like a signed/temporary provider URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        lower_qs = {k.lower() for k in qs}
        return bool(lower_qs & _SIGNED_URL_QUERY_PARAMS)
    except Exception:  # noqa: BLE001
        return False


def redact_string(value: str) -> str:
    """Redact auth headers and URL secret-params embedded in a plain string.

    The function is idempotent: calling it on an already-redacted string returns
    the same string unchanged.
    """
    if not isinstance(value, str):
        return value
    # Replace bearer/basic/token header values.
    value = _AUTH_HEADER_RE.sub(r"\g<1>" + REDACTED, value)
    # Replace inline URL query secrets.
    value = _URL_SECRET_RE.sub(r"\g<1>" + REDACTED, value)
    return value


def redact_url(url: str) -> str:
    """Return a redacted version of *url*.

    If the URL contains query parameters that indicate a signed/temporary URL
    (e.g. ``X-Amz-Signature``, ``token``), replace those parameters with the
    redaction sentinel.  Other parameters are preserved.

    The REDACTED sentinel is inserted as a literal string (not URL-encoded) so
    downstream JSON parsing can detect it without percent-decoding.
    """
    if not isinstance(url, str):
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.query:
            return url
        qs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        parts: list[str] = []
        for k, v in qs:
            safe_k = urllib.parse.quote(k, safe="")
            if k.lower() in _SIGNED_URL_QUERY_PARAMS:
                parts.append(f"{safe_k}={REDACTED}")
            else:
                parts.append(f"{safe_k}={urllib.parse.quote(v, safe='')}")
        new_query = "&".join(parts)
        redacted = parsed._replace(query=new_query)
        return urllib.parse.urlunparse(redacted)
    except Exception:  # noqa: BLE001
        return REDACTED


def redact_value(value: Any, *, depth: int = 0, max_depth: int = 20) -> Any:
    """Recursively redact secrets from *value*.

    Handles dicts, lists, strings.  Non-string scalars (int, float, bool, None)
    are returned unchanged.  Depth-guards prevent runaway recursion on unusual
    nested structures.
    """
    if depth > max_depth:
        return REDACTED
    if isinstance(value, dict):
        return {k: (REDACTED if _is_secret_key(k) else redact_value(v, depth=depth + 1, max_depth=max_depth)) for k, v in value.items()}  # noqa: E501
    if isinstance(value, list):
        return [redact_value(item, depth=depth + 1, max_depth=max_depth) for item in value]
    if isinstance(value, str):
        if _is_signed_url(value):
            return redact_url(value)
        return redact_string(value)
    return value


def redact_links(links: list[str]) -> list[str]:
    """Redact a list of URLs, replacing signed URLs with the redaction sentinel."""
    return [redact_url(link) if isinstance(link, str) else REDACTED for link in links]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ManifestValidationError(ValueError):
    """Raised when a manifest dict is missing required fields or has invalid values.

    ``missing`` lists all missing field paths; ``invalid`` lists fields with
    invalid values.  Both are reported together so callers see all problems at once.
    """

    def __init__(
        self,
        manifest_type: str,
        missing: list[str] | None = None,
        invalid: list[str] | None = None,
    ) -> None:
        parts: list[str] = []
        if missing:
            parts.append("missing fields: " + ", ".join(missing))
        if invalid:
            parts.append("invalid fields: " + ", ".join(invalid))
        super().__init__(f"ManifestValidationError [{manifest_type}]: {'; '.join(parts)}")
        self.manifest_type = manifest_type
        self.missing = missing or []
        self.invalid = invalid or []


# ---------------------------------------------------------------------------
# Candidate entry (shared by search manifests)
# ---------------------------------------------------------------------------


@dataclass
class CandidateEntry:
    """One provider candidate as stored in a canonical search manifest.

    All provider-specific fields are redacted before this is persisted.
    """

    # Provider-native item identifier (as returned by the provider API).
    provider_item_id: str

    # Deterministic Akasha item ID: ``{satellite}:{level}:{tile}:{datetime}:{baseline}``.
    # May be empty-string when not yet computed (e.g. pre-normalisation).
    item_id: str

    # UTC ISO-8601 acquisition datetime, or None if provider did not return one.
    acquisition_datetime: str | None

    # WGS-84 bounding box [min_lon, min_lat, max_lon, max_lat], or None.
    bbox: list[float] | None

    # Whether the item intersects the requested AOI.
    intersects_aoi: bool

    # Overlap area in degrees² between item bbox and AOI bbox.
    overlap_area: float

    # Current download lifecycle state for this candidate.
    download_status: DownloadStatus

    # Reason candidate was skipped/excluded, if applicable.
    skip_reason: str | None = None

    # Cloud-cover percentage [0–100].  None = not available from provider.
    cloud_cover_pct: float | None = None

    # Redacted provider properties (scalar values, no secrets).
    provider_properties: dict[str, Any] = field(default_factory=dict)

    # Redacted download/asset links.
    links: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerItemId": self.provider_item_id,
            "itemId": self.item_id,
            "acquisitionDatetime": self.acquisition_datetime,
            "bbox": self.bbox,
            "intersectsAoi": self.intersects_aoi,
            "overlapArea": self.overlap_area,
            "downloadStatus": str(self.download_status),
            "skipReason": self.skip_reason,
            "cloudCoverPct": self.cloud_cover_pct,
            "providerProperties": self.provider_properties,
            "links": self.links,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CandidateEntry:
        return cls(
            provider_item_id=str(d.get("providerItemId") or ""),
            item_id=str(d.get("itemId") or ""),
            acquisition_datetime=d.get("acquisitionDatetime"),
            bbox=d.get("bbox"),
            intersects_aoi=bool(d.get("intersectsAoi", False)),
            overlap_area=float(d.get("overlapArea") or 0.0),
            download_status=DownloadStatus(d.get("downloadStatus") or DownloadStatus.PENDING),
            skip_reason=d.get("skipReason"),
            cloud_cover_pct=d.get("cloudCoverPct"),
            provider_properties=d.get("providerProperties") or {},
            links=list(d.get("links") or []),
        )


# ---------------------------------------------------------------------------
# Search manifest
# ---------------------------------------------------------------------------


@dataclass
class SearchManifest:
    """Canonical search-pass manifest.

    Written once per provider search call.  All sensitive fields are redacted
    before this is serialised to disk or returned via an API.

    JSON camelCase keys are used for on-disk/API compatibility; Python fields use
    snake_case.  Use ``to_dict()`` / ``SearchManifest.from_dict()`` for I/O.
    """

    manifest_type: ManifestType
    version: int
    source_id: str
    provider: str
    adapter: str
    collection: str

    # AOI metadata: ``{id, name, bbox}``.
    aoi: dict[str, Any]

    # ISO-8601 datetime range string used for the search (e.g. "2024-01-01T00:00:00Z/...").
    datetime_range: str

    # Redacted provider-specific query parameters/filters sent to the API.
    provider_query: dict[str, Any]

    # All candidates returned (and normalised) from the provider.
    candidates: list[CandidateEntry]

    # Selection result: ``{selectedItemIds: [...], selectionCriteria: {...}}``.
    selection: dict[str, Any]

    # Scheduler job identifier for traceability.
    job_id: str | None = None

    # UTC ISO-8601 timestamp when the manifest was created.
    created_at: str | None = None

    # Redaction rule-set version applied to this manifest.
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestType": str(self.manifest_type),
            "version": self.version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "provider": self.provider,
            "adapter": self.adapter,
            "collection": self.collection,
            "aoi": self.aoi,
            "datetimeRange": self.datetime_range,
            "providerQuery": self.provider_query,
            "candidates": [c.to_dict() for c in self.candidates],
            "selection": self.selection,
            "createdAt": self.created_at,
            "redactionVersion": self.redaction_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SearchManifest:
        return cls(
            manifest_type=ManifestType(d.get("manifestType") or ManifestType.SEARCH),
            version=int(d.get("version") or SEARCH_MANIFEST_VERSION),
            job_id=d.get("jobId"),
            source_id=str(d.get("sourceId") or ""),
            provider=str(d.get("provider") or ""),
            adapter=str(d.get("adapter") or ""),
            collection=str(d.get("collection") or ""),
            aoi=d.get("aoi") or {},
            datetime_range=str(d.get("datetimeRange") or ""),
            provider_query=d.get("providerQuery") or {},
            candidates=[CandidateEntry.from_dict(c) for c in (d.get("candidates") or [])],
            selection=d.get("selection") or {},
            created_at=d.get("createdAt"),
            redaction_version=int(d.get("redactionVersion") or REDACTION_VERSION),
        )


# ---------------------------------------------------------------------------
# Download manifest entries
# ---------------------------------------------------------------------------


@dataclass
class DownloadedEntry:
    """One successfully downloaded item in a download manifest."""

    # Provider-native item identifier.
    provider_item_id: str

    # Deterministic Akasha item ID.
    item_id: str

    # Absolute local path to the downloaded archive/file.
    local_path: str

    # Actual downloaded file size in bytes.
    downloaded_bytes: int

    # UTC ISO-8601 timestamp when the download completed.
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerItemId": self.provider_item_id,
            "itemId": self.item_id,
            "localPath": self.local_path,
            "downloadedBytes": self.downloaded_bytes,
            "completedAt": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DownloadedEntry:
        return cls(
            provider_item_id=str(d.get("providerItemId") or ""),
            item_id=str(d.get("itemId") or ""),
            local_path=str(d.get("localPath") or ""),
            downloaded_bytes=int(d.get("downloadedBytes") or 0),
            completed_at=d.get("completedAt"),
        )


@dataclass
class FailedEntry:
    """One failed download attempt in a download manifest."""

    # Provider-native item identifier.
    provider_item_id: str

    # Deterministic Akasha item ID.
    item_id: str

    # Categorised error kind for monitoring aggregation.
    error_kind: ErrorKind

    # Redacted human-readable error string (no secrets).
    redacted_error: str

    # Whether this failure is worth retrying in a later run.
    retryable: bool

    # Total number of download attempts made for this item.
    attempt_count: int = 1

    # UTC ISO-8601 timestamp of the last failed attempt.
    failed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerItemId": self.provider_item_id,
            "itemId": self.item_id,
            "errorKind": str(self.error_kind),
            "redactedError": self.redacted_error,
            "retryable": self.retryable,
            "attemptCount": self.attempt_count,
            "failedAt": self.failed_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FailedEntry:
        return cls(
            provider_item_id=str(d.get("providerItemId") or ""),
            item_id=str(d.get("itemId") or ""),
            error_kind=ErrorKind(d.get("errorKind") or ErrorKind.UNKNOWN),
            redacted_error=str(d.get("redactedError") or ""),
            retryable=bool(d.get("retryable", True)),
            attempt_count=int(d.get("attemptCount") or 1),
            failed_at=d.get("failedAt"),
        )


@dataclass
class DeferredEntry:
    """One deferred download in a download manifest.

    Items are deferred (rather than failed) when they are not currently available
    but may become available in a future run (e.g. not-yet-online products).
    """

    # Provider-native item identifier.
    provider_item_id: str

    # Deterministic Akasha item ID.
    item_id: str

    # Human-readable reason why the download was deferred.
    defer_reason: str

    # UTC ISO-8601 earliest timestamp at which to retry, if known.
    retry_after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerItemId": self.provider_item_id,
            "itemId": self.item_id,
            "deferReason": self.defer_reason,
            "retryAfter": self.retry_after,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeferredEntry:
        return cls(
            provider_item_id=str(d.get("providerItemId") or ""),
            item_id=str(d.get("itemId") or ""),
            defer_reason=str(d.get("deferReason") or ""),
            retry_after=d.get("retryAfter"),
        )


# ---------------------------------------------------------------------------
# Download manifest
# ---------------------------------------------------------------------------


@dataclass
class DownloadManifest:
    """Canonical download-pass manifest.

    Records every downloaded, failed, and deferred item from one download run.
    No credentials, bearer tokens, or signed URLs are persisted: all paths are
    local filesystem paths under the approved storage root.
    """

    manifest_type: ManifestType
    version: int
    source_id: str
    provider: str
    adapter: str

    # Successfully downloaded items.
    downloaded: list[DownloadedEntry]

    # Items where download failed.
    failed: list[FailedEntry]

    # Items deferred to a later run.
    deferred: list[DeferredEntry]

    # Scheduler job identifier.
    job_id: str | None = None

    # UTC ISO-8601 timestamp when the manifest was created.
    created_at: str | None = None

    # Redaction rule-set version applied to this manifest.
    redaction_version: int = REDACTION_VERSION

    # --- aggregate counters (derived; set by builder for convenience) ---

    # Total bytes across all downloaded items.
    total_downloaded_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestType": str(self.manifest_type),
            "version": self.version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "provider": self.provider,
            "adapter": self.adapter,
            "downloaded": [d.to_dict() for d in self.downloaded],
            "failed": [f.to_dict() for f in self.failed],
            "deferred": [d.to_dict() for d in self.deferred],
            "totalDownloadedBytes": self.total_downloaded_bytes,
            "createdAt": self.created_at,
            "redactionVersion": self.redaction_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DownloadManifest:
        downloaded = [DownloadedEntry.from_dict(x) for x in (d.get("downloaded") or [])]
        total_bytes = sum(e.downloaded_bytes for e in downloaded)
        return cls(
            manifest_type=ManifestType(d.get("manifestType") or ManifestType.DOWNLOAD),
            version=int(d.get("version") or DOWNLOAD_MANIFEST_VERSION),
            job_id=d.get("jobId"),
            source_id=str(d.get("sourceId") or ""),
            provider=str(d.get("provider") or ""),
            adapter=str(d.get("adapter") or ""),
            downloaded=downloaded,
            failed=[FailedEntry.from_dict(x) for x in (d.get("failed") or [])],
            deferred=[DeferredEntry.from_dict(x) for x in (d.get("deferred") or [])],
            total_downloaded_bytes=int(d.get("totalDownloadedBytes") or total_bytes),
            created_at=d.get("createdAt"),
            redaction_version=int(d.get("redactionVersion") or REDACTION_VERSION),
        )


# ---------------------------------------------------------------------------
# Order manifest  (future commercial/tasked provider phases)
# ---------------------------------------------------------------------------


@dataclass
class OrderManifest:
    """Canonical order-lifecycle manifest for future commercial/tasked providers.

    No current provider adapter uses this manifest; it is defined now so
    downstream stages can declare schema expectations and so commercial
    provider onboarding (Planet, JAXA, vendor) has a documented target shape.

    SEC-007: the ``allow_paid_order`` flag MUST be True and the
    ``commercial_readiness_record_id`` MUST be non-empty for any adapter that
    actually executes a paid order call.
    """

    manifest_type: ManifestType
    version: int
    source_id: str
    provider: str
    adapter: str

    # Candidate item this order was placed for.
    candidate_item_id: str

    # Provider-assigned order/task identifier; None until order is submitted.
    provider_order_id: str | None

    # Current canonical order lifecycle state.
    state: OrderLifecycleState

    # Whether the operator explicitly approved paid order execution (SEC-007).
    allow_paid_order: bool

    # Scheduler job identifier.
    job_id: str | None = None

    # UTC ISO-8601 timestamp of order submission.
    submitted_at: str | None = None

    # UTC ISO-8601 timestamp of order completion (any terminal state).
    completed_at: str | None = None

    # Operator-provided commercial-readiness record identifier for audit trail.
    commercial_readiness_record_id: str | None = None

    # Estimated cost in provider quota units at submission time.
    estimated_cost_units: float | None = None

    # Actual cost in provider quota units (populated after order completion).
    actual_cost_units: float | None = None

    # Currency/unit label for cost fields (e.g. "sqkm", "credits", "USD").
    cost_unit_label: str | None = None

    # Raw provider state string for debugging/logging.
    raw_state: str | None = None

    # Failure reason for terminal FAILED state (redacted).
    failure_reason: str | None = None

    # Redacted download links produced by provider after order completion.
    download_links: list[str] = field(default_factory=list)

    # UTC ISO-8601 timestamp when the manifest was created.
    created_at: str | None = None

    # Redaction rule-set version applied to this manifest.
    redaction_version: int = REDACTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestType": str(self.manifest_type),
            "version": self.version,
            "jobId": self.job_id,
            "sourceId": self.source_id,
            "provider": self.provider,
            "adapter": self.adapter,
            "candidateItemId": self.candidate_item_id,
            "providerOrderId": self.provider_order_id,
            "state": str(self.state),
            "allowPaidOrder": self.allow_paid_order,
            "submittedAt": self.submitted_at,
            "completedAt": self.completed_at,
            "commercialReadinessRecordId": self.commercial_readiness_record_id,
            "estimatedCostUnits": self.estimated_cost_units,
            "actualCostUnits": self.actual_cost_units,
            "costUnitLabel": self.cost_unit_label,
            "rawState": self.raw_state,
            "failureReason": self.failure_reason,
            "downloadLinks": self.download_links,
            "createdAt": self.created_at,
            "redactionVersion": self.redaction_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OrderManifest:
        return cls(
            manifest_type=ManifestType(d.get("manifestType") or ManifestType.ORDER),
            version=int(d.get("version") or ORDER_MANIFEST_VERSION),
            job_id=d.get("jobId"),
            source_id=str(d.get("sourceId") or ""),
            provider=str(d.get("provider") or ""),
            adapter=str(d.get("adapter") or ""),
            candidate_item_id=str(d.get("candidateItemId") or ""),
            provider_order_id=d.get("providerOrderId"),
            state=OrderLifecycleState(d.get("state") or OrderLifecycleState.UNKNOWN),
            allow_paid_order=bool(d.get("allowPaidOrder", False)),
            submitted_at=d.get("submittedAt"),
            completed_at=d.get("completedAt"),
            commercial_readiness_record_id=d.get("commercialReadinessRecordId"),
            estimated_cost_units=d.get("estimatedCostUnits"),
            actual_cost_units=d.get("actualCostUnits"),
            cost_unit_label=d.get("costUnitLabel"),
            raw_state=d.get("rawState"),
            failure_reason=d.get("failureReason"),
            download_links=list(d.get("downloadLinks") or []),
            created_at=d.get("createdAt"),
            redaction_version=int(d.get("redactionVersion") or REDACTION_VERSION),
        )


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def build_search_manifest(
    *,
    source_id: str,
    provider: str,
    adapter: str,
    collection: str,
    aoi: dict[str, Any],
    datetime_range: str,
    provider_query: dict[str, Any],
    candidates: list[CandidateEntry],
    selection: dict[str, Any] | None = None,
    job_id: str | None = None,
    created_at: str | None = None,
) -> SearchManifest:
    """Build a fully-redacted ``SearchManifest``.

    ``provider_query`` is redacted before storage.
    ``CandidateEntry.provider_properties`` and ``.links`` are expected to be
    pre-redacted by the caller (adapter layer); this function applies a
    second-pass redaction as a safety net.
    """
    redacted_query = redact_value(provider_query)
    safe_candidates = []
    for c in candidates:
        safe_candidates.append(
            CandidateEntry(
                provider_item_id=c.provider_item_id,
                item_id=c.item_id,
                acquisition_datetime=c.acquisition_datetime,
                bbox=c.bbox,
                intersects_aoi=c.intersects_aoi,
                overlap_area=c.overlap_area,
                download_status=c.download_status,
                skip_reason=c.skip_reason,
                cloud_cover_pct=c.cloud_cover_pct,
                provider_properties=redact_value(c.provider_properties),
                links=redact_links(c.links),
            )
        )
    return SearchManifest(
        manifest_type=ManifestType.SEARCH,
        version=SEARCH_MANIFEST_VERSION,
        job_id=job_id,
        source_id=source_id,
        provider=provider,
        adapter=adapter,
        collection=collection,
        aoi={
            "id": aoi.get("id"),
            "name": aoi.get("name"),
            "bbox": aoi.get("bbox"),
        },
        datetime_range=datetime_range,
        provider_query=redacted_query,
        candidates=safe_candidates,
        selection=selection or {"selectedItemIds": [], "selectionCriteria": {}},
        created_at=created_at,
        redaction_version=REDACTION_VERSION,
    )


def build_download_manifest(
    *,
    source_id: str,
    provider: str,
    adapter: str,
    downloaded: list[DownloadedEntry] | None = None,
    failed: list[FailedEntry] | None = None,
    deferred: list[DeferredEntry] | None = None,
    job_id: str | None = None,
    created_at: str | None = None,
) -> DownloadManifest:
    """Build a ``DownloadManifest`` with aggregate byte counts computed."""
    dl = downloaded or []
    total_bytes = sum(e.downloaded_bytes for e in dl)
    return DownloadManifest(
        manifest_type=ManifestType.DOWNLOAD,
        version=DOWNLOAD_MANIFEST_VERSION,
        job_id=job_id,
        source_id=source_id,
        provider=provider,
        adapter=adapter,
        downloaded=dl,
        failed=failed or [],
        deferred=deferred or [],
        total_downloaded_bytes=total_bytes,
        created_at=created_at,
        redaction_version=REDACTION_VERSION,
    )


def build_order_manifest(
    *,
    source_id: str,
    provider: str,
    adapter: str,
    candidate_item_id: str,
    provider_order_id: str | None,
    state: OrderLifecycleState,
    allow_paid_order: bool,
    job_id: str | None = None,
    submitted_at: str | None = None,
    completed_at: str | None = None,
    commercial_readiness_record_id: str | None = None,
    estimated_cost_units: float | None = None,
    actual_cost_units: float | None = None,
    cost_unit_label: str | None = None,
    raw_state: str | None = None,
    failure_reason: str | None = None,
    download_links: list[str] | None = None,
    created_at: str | None = None,
) -> OrderManifest:
    """Build a fully-redacted ``OrderManifest`` for a commercial/tasked order."""
    return OrderManifest(
        manifest_type=ManifestType.ORDER,
        version=ORDER_MANIFEST_VERSION,
        job_id=job_id,
        source_id=source_id,
        provider=provider,
        adapter=adapter,
        candidate_item_id=candidate_item_id,
        provider_order_id=provider_order_id,
        state=state,
        allow_paid_order=allow_paid_order,
        submitted_at=submitted_at,
        completed_at=completed_at,
        commercial_readiness_record_id=commercial_readiness_record_id,
        estimated_cost_units=estimated_cost_units,
        actual_cost_units=actual_cost_units,
        cost_unit_label=cost_unit_label,
        raw_state=raw_state,
        failure_reason=failure_reason,
        download_links=redact_links(download_links or []),
        created_at=created_at,
        redaction_version=REDACTION_VERSION,
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_SEARCH_REQUIRED = (
    "manifestType",
    "version",
    "sourceId",
    "provider",
    "adapter",
    "collection",
    "aoi",
    "datetimeRange",
    "providerQuery",
    "candidates",
    "selection",
    "redactionVersion",
)

_DOWNLOAD_REQUIRED = (
    "manifestType",
    "version",
    "sourceId",
    "provider",
    "adapter",
    "downloaded",
    "failed",
    "deferred",
    "redactionVersion",
)

_ORDER_REQUIRED = (
    "manifestType",
    "version",
    "sourceId",
    "provider",
    "adapter",
    "candidateItemId",
    "state",
    "allowPaidOrder",
    "redactionVersion",
)

_CANDIDATE_REQUIRED = (
    "providerItemId",
    "itemId",
    "bbox",
    "intersectsAoi",
    "overlapArea",
    "downloadStatus",
    "providerProperties",
    "links",
)


def _collect_missing(d: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [key for key in required if key not in d]


def validate_search_manifest_dict(d: dict[str, Any]) -> None:
    """Validate a raw search-manifest dict against required fields.

    Raises ``ManifestValidationError`` listing all missing fields.
    Validates candidate sub-dicts as well.
    """
    missing = _collect_missing(d, _SEARCH_REQUIRED)
    invalid: list[str] = []
    if missing or invalid:
        raise ManifestValidationError("search", missing=missing, invalid=invalid)
    # Validate each candidate.
    candidate_missing: list[str] = []
    for idx, c in enumerate(d.get("candidates") or []):
        if not isinstance(c, dict):
            invalid.append(f"candidates[{idx}] is not a dict")
            continue
        for key in _CANDIDATE_REQUIRED:
            if key not in c:
                candidate_missing.append(f"candidates[{idx}].{key}")
    if candidate_missing or invalid:
        raise ManifestValidationError("search", missing=candidate_missing, invalid=invalid)


def validate_download_manifest_dict(d: dict[str, Any]) -> None:
    """Validate a raw download-manifest dict against required fields.

    Raises ``ManifestValidationError`` listing all missing fields.
    """
    missing = _collect_missing(d, _DOWNLOAD_REQUIRED)
    if missing:
        raise ManifestValidationError("download", missing=missing)


def validate_order_manifest_dict(d: dict[str, Any]) -> None:
    """Validate a raw order-manifest dict against required fields.

    Raises ``ManifestValidationError`` listing all missing fields.
    """
    missing = _collect_missing(d, _ORDER_REQUIRED)
    if missing:
        raise ManifestValidationError("order", missing=missing)


# ---------------------------------------------------------------------------
# Versioning and migration
# ---------------------------------------------------------------------------

# Registry of known manifest schema versions per type.
_KNOWN_VERSIONS: dict[str, set[int]] = {
    ManifestType.SEARCH: {1},
    ManifestType.DOWNLOAD: {1},
    ManifestType.ORDER: {1},
}


def _migrate_search_v1(d: dict[str, Any]) -> dict[str, Any]:
    """Return *d* migrated to search manifest version 1.

    Handles legacy bhoonidhi_search_manifest keys:
    - ``type`` → ``manifestType``
    - ``source_id`` → ``sourceId``
    - ``search.datetime`` → ``datetimeRange``
    - ``selection.selected_product_ids`` → ``selection.selectedItemIds``
    - adds ``provider``, ``adapter``, ``providerQuery``, ``redactionVersion``
      if absent.

    This migration is one-way and idempotent: calling it on an already-v1 dict
    returns the same dict unchanged.
    """
    out = dict(d)

    # Normalise ``type`` → ``manifestType``
    if "manifestType" not in out and "type" in out:
        out["manifestType"] = ManifestType.SEARCH

    # Normalise ``source_id`` → ``sourceId``
    if "sourceId" not in out and "source_id" in out:
        out["sourceId"] = out.pop("source_id")

    # Normalise ``search.datetime`` → ``datetimeRange``
    if "datetimeRange" not in out:
        search_block = out.get("search") or {}
        dt = search_block.get("datetime") or search_block.get("datetimeRange") or ""
        out["datetimeRange"] = dt

    # Flatten ``search.filter`` into ``providerQuery``
    if "providerQuery" not in out:
        search_block = out.get("search") or {}
        out["providerQuery"] = {"filter": search_block.get("filter")}

    # Add missing provider/adapter fields.
    out.setdefault("provider", "bhoonidhi")
    out.setdefault("adapter", "bhoonidhi")
    out.setdefault("version", SEARCH_MANIFEST_VERSION)
    out.setdefault("redactionVersion", REDACTION_VERSION)

    # Normalise ``selection.selected_product_ids`` → ``selection.selectedItemIds``
    selection = out.get("selection") or {}
    if isinstance(selection, dict) and "selectedItemIds" not in selection:
        legacy_ids = selection.get("selected_product_ids") or []
        selection = dict(selection)
        selection["selectedItemIds"] = legacy_ids
        selection.setdefault("selectionCriteria", {})
        out["selection"] = selection

    # Normalise candidate keys from legacy bhoonidhi shape.
    if "candidates" in out:
        normalised: list[dict[str, Any]] = []
        for c in out["candidates"]:
            if not isinstance(c, dict):
                continue
            nc: dict[str, Any] = dict(c)
            # Legacy keys → canonical keys
            if "providerItemId" not in nc:
                nc["providerItemId"] = nc.pop("item_id", "")
            if "itemId" not in nc:
                nc["itemId"] = nc.get("providerItemId", "")
            if "acquisitionDatetime" not in nc:
                nc["acquisitionDatetime"] = nc.pop("datetime", None)
            if "intersectsAoi" not in nc:
                nc["intersectsAoi"] = bool(nc.get("overlap_area") or nc.get("overlapArea") or 0)
            if "overlapArea" not in nc:
                nc["overlapArea"] = float(nc.pop("overlap_area", 0.0))
            if "downloadStatus" not in nc:
                nc["downloadStatus"] = nc.pop("download_status", DownloadStatus.PENDING)
            if "skipReason" not in nc:
                nc["skipReason"] = None
            if "providerProperties" not in nc:
                nc["providerProperties"] = nc.pop("properties", {})
            if "links" not in nc:
                nc["links"] = []
            normalised.append(nc)
        out["candidates"] = normalised

    return out


def migrate_manifest(d: dict[str, Any]) -> dict[str, Any]:
    """Apply any needed schema migrations to a raw manifest dict.

    Returns a new dict at the current canonical version.  Raises
    ``ManifestValidationError`` if ``manifestType`` is unrecognised.

    Migration is additive and idempotent; call this on every manifest loaded
    from disk before parsing into typed dataclasses.
    """
    manifest_type_raw = d.get("manifestType") or d.get("type") or ""
    # Map legacy type strings to canonical ManifestType values.
    legacy_type_map = {
        "bhoonidhi_search_manifest": ManifestType.SEARCH,
        "search": ManifestType.SEARCH,
        "download": ManifestType.DOWNLOAD,
        "order": ManifestType.ORDER,
    }
    manifest_type = legacy_type_map.get(str(manifest_type_raw).lower())
    if manifest_type is None:
        raise ManifestValidationError(
            str(manifest_type_raw),
            invalid=[f"manifestType '{manifest_type_raw}' is not a recognised manifest type"],
        )
    version = int(d.get("version") or 1)
    if manifest_type == ManifestType.SEARCH and version <= 1:
        return _migrate_search_v1(d)
    # Download and order manifests are new; no legacy keys to migrate yet.
    return d


# ---------------------------------------------------------------------------
# JSON I/O helpers
# ---------------------------------------------------------------------------


def manifest_to_dict(
    manifest: SearchManifest | DownloadManifest | OrderManifest,
) -> dict[str, Any]:
    """Serialise any canonical manifest to a JSON-safe dict."""
    return manifest.to_dict()


def manifest_from_dict(d: dict[str, Any]) -> SearchManifest | DownloadManifest | OrderManifest:
    """Parse a (possibly-migrated) manifest dict into a typed dataclass.

    Applies ``migrate_manifest`` first so legacy Bhoonidhi manifests are
    supported transparently.  Validates required fields before parsing.
    """
    migrated = migrate_manifest(d)
    manifest_type_str = str(migrated.get("manifestType") or "")
    if manifest_type_str == ManifestType.SEARCH:
        validate_search_manifest_dict(migrated)
        return SearchManifest.from_dict(migrated)
    if manifest_type_str == ManifestType.DOWNLOAD:
        validate_download_manifest_dict(migrated)
        return DownloadManifest.from_dict(migrated)
    if manifest_type_str == ManifestType.ORDER:
        validate_order_manifest_dict(migrated)
        return OrderManifest.from_dict(migrated)
    raise ManifestValidationError(
        manifest_type_str,
        invalid=[f"manifestType '{manifest_type_str}' is not a recognised manifest type"],
    )
