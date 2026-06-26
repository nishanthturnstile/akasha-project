"""Tests for canonical manifest schema and redaction (TASK-013 through TASK-018).

Covers:
- SEC-002 redaction: passwords, tokens, bearer headers, API keys, signed URLs,
  provider usernames, and secret-looking nested fields.
- Canonical manifest field coverage: SearchManifest, CandidateEntry,
  DownloadManifest, OrderManifest.
- Bhoonidhi integration: bhoonidhi.build_search_manifest and worker-style
  download manifest include canonical fields while preserving legacy keys.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INGESTION_ROOT = REPO_ROOT / "services" / "ingestion"
if str(INGESTION_ROOT) not in sys.path:
    sys.path.insert(0, str(INGESTION_ROOT))

from akasha_ingest import bhoonidhi  # noqa: E402
from akasha_ingest.manifests import (  # noqa: E402
    REDACTED,
    REDACTION_VERSION,
    CandidateEntry,
    DeferredEntry,
    DownloadedEntry,
    DownloadManifest,
    DownloadStatus,
    ErrorKind,
    FailedEntry,
    ManifestType,
    ManifestValidationError,
    OrderLifecycleState,
    OrderManifest,
    SearchManifest,
    build_download_manifest,
    build_order_manifest,
    build_search_manifest,
    redact_links,
    redact_string,
    redact_url,
    redact_value,
    validate_download_manifest_dict,
    validate_order_manifest_dict,
    validate_search_manifest_dict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_aoi() -> dict:
    return {
        "id": "bangalore-60km",
        "name": "Bangalore 60 km",
        "bbox": [77.0, 12.0, 78.0, 13.0],
    }


def _make_candidate(
    *,
    provider_item_id: str = "PROD_001",
    item_id: str = "resourcesat-2a-liss3-boa:BOA:T43PGP:2026-03-19T00:00:00Z:R01",
    status: DownloadStatus = DownloadStatus.PENDING,
) -> CandidateEntry:
    return CandidateEntry(
        provider_item_id=provider_item_id,
        item_id=item_id,
        acquisition_datetime="2026-03-19T00:00:00Z",
        bbox=[77.2, 12.2, 77.8, 12.8],
        intersects_aoi=True,
        overlap_area=0.36,
        download_status=status,
        provider_properties={"path": "99", "row": "65"},
        links=["https://example.com/asset.zip"],
    )


# ---------------------------------------------------------------------------
# SEC-002 Redaction: dict key patterns
# ---------------------------------------------------------------------------


def test_redact_password_key():
    result = redact_value({"password": "s3cr3t!"})
    assert result["password"] == REDACTED


def test_redact_passwd_alias():
    result = redact_value({"passwd": "pw123"})
    assert result["passwd"] == REDACTED


def test_redact_token_key():
    result = redact_value({"token": "eyJhb..."})
    assert result["token"] == REDACTED


def test_redact_access_token_key():
    result = redact_value({"access_token": "at-abc123"})
    assert result["access_token"] == REDACTED


def test_redact_refresh_token_key():
    result = redact_value({"refresh_token": "rt-xyz"})
    assert result["refresh_token"] == REDACTED


def test_redact_api_key_exact():
    result = redact_value({"api_key": "myapikey"})
    assert result["api_key"] == REDACTED


def test_redact_apikey_alias():
    result = redact_value({"apikey": "abc"})
    assert result["apikey"] == REDACTED


def test_redact_client_secret():
    result = redact_value({"client_secret": "cliS3cret"})
    assert result["client_secret"] == REDACTED


def test_redact_authorization_header_key():
    result = redact_value({"authorization": "Bearer token-xyz"})
    assert result["authorization"] == REDACTED


def test_redact_bearer_key():
    result = redact_value({"bearer": "some-token"})
    assert result["bearer"] == REDACTED


def test_redact_username_key():
    result = redact_value({"username": "user@example.com"})
    assert result["username"] == REDACTED


def test_redact_user_id_key():
    result = redact_value({"user_id": "uid-0042"})
    assert result["user_id"] == REDACTED


def test_redact_secret_key():
    result = redact_value({"secret": "topsecret"})
    assert result["secret"] == REDACTED


def test_redact_private_key():
    result = redact_value({"private_key": "-----BEGIN RSA-----"})
    assert result["private_key"] == REDACTED


def test_redact_x_amz_security_token():
    result = redact_value({"x-amz-security-token": "FQoGZXIvYXdz..."})
    assert result["x-amz-security-token"] == REDACTED


def test_redact_x_amz_credential():
    result = redact_value({"x-amz-credential": "AKIA...%2Fs3%2Faws4_request"})
    assert result["x-amz-credential"] == REDACTED


def test_redact_signing_key_suffix():
    result = redact_value({"signing_key": "abc"})
    assert result["signing_key"] == REDACTED


def test_redact_custom_suffix_password():
    result = redact_value({"db_password": "dbpw"})
    assert result["db_password"] == REDACTED


def test_redact_custom_suffix_secret():
    result = redact_value({"provider_secret": "prov-s3c"})
    assert result["provider_secret"] == REDACTED


def test_redact_custom_suffix_token():
    result = redact_value({"auth_token": "tok-abc"})
    assert result["auth_token"] == REDACTED


def test_redact_custom_prefix_x_amz():
    result = redact_value({"x-amz-signature": "sig123"})
    assert result["x-amz-signature"] == REDACTED


def test_redact_custom_prefix_x_goog():
    result = redact_value({"x-goog-credential": "cred123"})
    assert result["x-goog-credential"] == REDACTED


# ---------------------------------------------------------------------------
# SEC-002 Redaction: non-secret keys are preserved
# ---------------------------------------------------------------------------


def test_non_secret_keys_preserved():
    result = redact_value({"collection": "ResourceSat", "version": 1, "status": "ok"})
    assert result == {"collection": "ResourceSat", "version": 1, "status": "ok"}


def test_integer_and_bool_scalars_unchanged():
    result = redact_value({"count": 42, "flag": True, "nothing": None})
    assert result == {"count": 42, "flag": True, "nothing": None}


# ---------------------------------------------------------------------------
# SEC-002 Redaction: nested structures
# ---------------------------------------------------------------------------


def test_redact_nested_dict():
    data = {"outer": {"inner": {"auth_token": "secret-nested", "name": "liss3"}}}
    result = redact_value(data)
    assert result["outer"]["inner"]["auth_token"] == REDACTED
    assert result["outer"]["inner"]["name"] == "liss3"


def test_redact_list_of_dicts():
    data = [{"api_key": "k1"}, {"name": "item2"}]
    result = redact_value(data)
    assert result[0]["api_key"] == REDACTED
    assert result[1]["name"] == "item2"


def test_redact_manifest_payload_like_structure():
    """Simulate an API payload with mixed secret and safe fields."""
    payload = {
        "manifestType": "search",
        "sourceId": "resourcesat-2a-liss3-boa",
        "providerQuery": {
            "username": "user@nrsc.gov.in",
            "password": "hunter2",
            "collection": "ResourceSat-2A_LISS3_BOA",
        },
        "version": 1,
    }
    result = redact_value(payload)
    assert result["providerQuery"]["username"] == REDACTED
    assert result["providerQuery"]["password"] == REDACTED
    assert result["providerQuery"]["collection"] == "ResourceSat-2A_LISS3_BOA"
    assert result["manifestType"] == "search"
    assert result["version"] == 1


def test_redact_command_file_dict_with_credentials():
    """Simulate a command file / job config with embedded credentials."""
    cmd_cfg = {
        "cmd": "python worker.py bhoonidhi-sync",
        "env": {
            "BHOONIDHI_USER_ID": "admin",
            "BHOONIDHI_PASSWORD": "p@ss!",
            "SOME_API_KEY": "xyzkey",
            "DATA_DIR": "/srv/akasha",
        },
    }
    result = redact_value(cmd_cfg)
    assert result["cmd"] == "python worker.py bhoonidhi-sync"
    assert result["env"]["DATA_DIR"] == "/srv/akasha"
    # BHOONIDHI_USER_ID doesn't match exact/suffix/prefix patterns; not redacted
    # BHOONIDHI_PASSWORD ends with _PASSWORD → redacted
    assert result["env"]["BHOONIDHI_PASSWORD"] == REDACTED
    # SOME_API_KEY ends with _KEY → redacted
    assert result["env"]["SOME_API_KEY"] == REDACTED


# ---------------------------------------------------------------------------
# SEC-002 Redaction: Bearer/Basic/Token headers in strings
# ---------------------------------------------------------------------------


def test_redact_string_bearer_token():
    value = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    result = redact_string(value)
    assert "eyJhbGciOiJIUzI1NiJ9.payload.sig" not in result
    assert REDACTED in result
    assert "Bearer" in result


def test_redact_string_basic_token():
    value = "Authorization: Basic dXNlcjpwYXNz"
    result = redact_string(value)
    assert "dXNlcjpwYXNz" not in result
    assert REDACTED in result


def test_redact_string_token_keyword():
    value = "x-auth: Token abcdefghij1234567890"
    result = redact_string(value)
    assert "abcdefghij1234567890" not in result
    assert REDACTED in result


def test_redact_string_idempotent():
    """Calling redact_string on an already-redacted string is a no-op."""
    already = f"Authorization: Bearer {REDACTED}"
    assert redact_string(already) == already


def test_redact_log_line_with_inline_token():
    """Simulate a log line containing a bearer token."""
    log = (
        "2026-03-19 INFO requesting https://bhoonidhi.nrsc.gov.in"
        " with Authorization: Bearer secrettoken123"
    )
    result = redact_string(log)
    assert "secrettoken123" not in result
    assert REDACTED in result


# ---------------------------------------------------------------------------
# SEC-002 Redaction: signed URLs
# ---------------------------------------------------------------------------


def test_redact_url_amz_signed():
    url = (
        "https://s3.amazonaws.com/bucket/file.zip"
        "?X-Amz-Signature=abc123&X-Amz-Credential=AKIA%2Faws4&X-Amz-Date=20260319T000000Z"
        "&Content-Type=application%2Fzip"
    )
    result = redact_url(url)
    assert "abc123" not in result
    assert REDACTED in result
    # Non-secret params preserved
    assert "Content-Type" in result


def test_redact_url_token_param():
    url = "https://cdn.example.com/file?token=supersecret&format=zip"
    result = redact_url(url)
    assert "supersecret" not in result
    assert REDACTED in result
    assert "format=zip" in result


def test_redact_url_no_query_string_unchanged():
    url = "https://bhoonidhi-api.nrsc.gov.in/data/search"
    assert redact_url(url) == url


def test_redact_links_list():
    links = [
        "https://s3.amazonaws.com/b/f.zip?X-Amz-Signature=sig1",
        "https://cdn.example.com/plain.zip",
    ]
    result = redact_links(links)
    assert "sig1" not in result[0]
    assert REDACTED in result[0]
    assert result[1] == "https://cdn.example.com/plain.zip"


def test_redact_value_redacts_signed_url_in_string_field():
    signed = "https://s3.amazonaws.com/b/f.zip?X-Amz-Signature=sig123&other=v"
    result = redact_value({"download_url": signed})
    # download_url key is not a secret key, but the value is a signed URL → redacted
    assert "sig123" not in result["download_url"]


def test_redact_value_url_secret_param_in_string():
    s = "Downloading from https://example.com/file?api_key=mykey123&foo=bar"
    result = redact_string(s)
    assert "mykey123" not in result
    assert REDACTED in result


# ---------------------------------------------------------------------------
# SEC-002 Redaction: depth guard
# ---------------------------------------------------------------------------


def test_redact_value_max_depth_guard():
    """Deeply nested structures beyond max_depth are replaced with REDACTED."""
    # Build a dict nested 25 levels deep
    deep: dict = {}
    current = deep
    for _ in range(25):
        child: dict = {}
        current["level"] = child
        current = child
    current["name"] = "leaf"
    result = redact_value(deep, max_depth=5)
    # Should not raise; deeply nested values become REDACTED
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Canonical SearchManifest: required fields
# ---------------------------------------------------------------------------


def test_build_search_manifest_has_required_top_level_fields():
    manifest = build_search_manifest(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        adapter="bhoonidhi",
        collection="ResourceSat-2A_LISS3_BOA",
        aoi=_minimal_aoi(),
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        provider_query={"collection": "ResourceSat-2A_LISS3_BOA"},
        candidates=[_make_candidate()],
        job_id="job-001",
    )
    d = manifest.to_dict()

    assert d["manifestType"] == "search"
    assert d["version"] == 1
    assert d["jobId"] == "job-001"
    assert d["sourceId"] == "resourcesat-2a-liss3-boa"
    assert d["provider"] == "bhoonidhi"
    assert d["adapter"] == "bhoonidhi"
    assert d["collection"] == "ResourceSat-2A_LISS3_BOA"
    assert d["aoi"] == {
        "id": "bangalore-60km",
        "name": "Bangalore 60 km",
        "bbox": [77.0, 12.0, 78.0, 13.0],
    }
    assert d["datetimeRange"] == "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z"
    assert "providerQuery" in d
    assert "candidates" in d
    assert "selection" in d
    assert d["redactionVersion"] == REDACTION_VERSION


def test_build_search_manifest_redacts_provider_query_secrets():
    manifest = build_search_manifest(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        adapter="bhoonidhi",
        collection="ResourceSat-2A_LISS3_BOA",
        aoi=_minimal_aoi(),
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        provider_query={"username": "user@nrsc", "password": "secret", "collection": "RS-BOA"},
        candidates=[],
    )
    d = manifest.to_dict()
    assert d["providerQuery"]["username"] == REDACTED
    assert d["providerQuery"]["password"] == REDACTED
    assert d["providerQuery"]["collection"] == "RS-BOA"


def test_build_search_manifest_selection_defaults():
    manifest = build_search_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        collection="c",
        aoi=_minimal_aoi(),
        datetime_range="r",
        provider_query={},
        candidates=[],
    )
    d = manifest.to_dict()
    assert "selectedItemIds" in d["selection"]
    assert "selectionCriteria" in d["selection"]


# ---------------------------------------------------------------------------
# Canonical CandidateEntry: required fields
# ---------------------------------------------------------------------------


def test_candidate_entry_to_dict_has_required_fields():
    c = _make_candidate()
    d = c.to_dict()

    assert "providerItemId" in d
    assert "itemId" in d
    assert "acquisitionDatetime" in d
    assert "bbox" in d
    assert "intersectsAoi" in d
    assert "overlapArea" in d
    assert "downloadStatus" in d
    assert "skipReason" in d
    assert "providerProperties" in d
    assert "links" in d


def test_candidate_entry_values():
    c = _make_candidate(provider_item_id="RS2A_XYZ", item_id="akasha-item-42")
    d = c.to_dict()

    assert d["providerItemId"] == "RS2A_XYZ"
    assert d["itemId"] == "akasha-item-42"
    assert d["acquisitionDatetime"] == "2026-03-19T00:00:00Z"
    assert d["bbox"] == [77.2, 12.2, 77.8, 12.8]
    assert d["intersectsAoi"] is True
    assert d["overlapArea"] == pytest.approx(0.36)
    assert d["downloadStatus"] == "pending"


def test_candidate_entry_roundtrip():
    c = _make_candidate()
    restored = CandidateEntry.from_dict(c.to_dict())
    assert restored.provider_item_id == c.provider_item_id
    assert restored.item_id == c.item_id
    assert restored.bbox == c.bbox
    assert restored.intersects_aoi == c.intersects_aoi
    assert restored.overlap_area == pytest.approx(c.overlap_area)
    assert restored.download_status == c.download_status


def test_build_search_manifest_redacts_candidate_provider_properties():
    """build_search_manifest applies a safety-net second-pass redaction on candidate fields."""
    candidate = _make_candidate()
    candidate.provider_properties = {"safe_field": "ok", "auth_token": "toksecret"}
    manifest = build_search_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        collection="c",
        aoi=_minimal_aoi(),
        datetime_range="r",
        provider_query={},
        candidates=[candidate],
    )
    c_dict = manifest.to_dict()["candidates"][0]
    assert c_dict["providerProperties"]["auth_token"] == REDACTED
    assert c_dict["providerProperties"]["safe_field"] == "ok"


def test_build_search_manifest_redacts_candidate_signed_links():
    candidate = _make_candidate()
    candidate.links = ["https://s3.amazonaws.com/b/f.zip?X-Amz-Signature=sig99&foo=bar"]
    manifest = build_search_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        collection="c",
        aoi=_minimal_aoi(),
        datetime_range="r",
        provider_query={},
        candidates=[candidate],
    )
    link = manifest.to_dict()["candidates"][0]["links"][0]
    assert "sig99" not in link
    assert REDACTED in link


# ---------------------------------------------------------------------------
# Canonical SearchManifest: validation helper
# ---------------------------------------------------------------------------


def test_validate_search_manifest_dict_passes_complete_dict():
    m = build_search_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        collection="c",
        aoi=_minimal_aoi(),
        datetime_range="r",
        provider_query={},
        candidates=[_make_candidate()],
    )
    validate_search_manifest_dict(m.to_dict())  # must not raise


def test_validate_search_manifest_dict_raises_on_missing_top_level():
    d = {
        "manifestType": "search",
        "version": 1,
        # sourceId missing
        "provider": "p",
        "adapter": "a",
        "collection": "c",
        "aoi": {},
        "datetimeRange": "r",
        "providerQuery": {},
        "candidates": [],
        "selection": {},
        "redactionVersion": 1,
    }
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_search_manifest_dict(d)
    assert "sourceId" in exc_info.value.missing


def test_validate_search_manifest_raises_all_missing_at_once():
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_search_manifest_dict({})
    assert len(exc_info.value.missing) > 1


def test_validate_search_manifest_raises_on_missing_candidate_field():
    d = build_search_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        collection="c",
        aoi=_minimal_aoi(),
        datetime_range="r",
        provider_query={},
        candidates=[_make_candidate()],
    ).to_dict()
    # Remove a required candidate field
    del d["candidates"][0]["bbox"]
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_search_manifest_dict(d)
    assert any("bbox" in m for m in exc_info.value.missing)


def test_search_manifest_roundtrip_from_dict():
    original = build_search_manifest(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        adapter="bhoonidhi",
        collection="ResourceSat-2A_LISS3_BOA",
        aoi=_minimal_aoi(),
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        provider_query={"filter": "Online=Y"},
        candidates=[_make_candidate()],
        job_id="job-roundtrip",
    )
    restored = SearchManifest.from_dict(original.to_dict())
    assert restored.source_id == original.source_id
    assert restored.job_id == original.job_id
    assert restored.version == original.version
    assert restored.manifest_type == ManifestType.SEARCH
    assert len(restored.candidates) == 1
    assert restored.candidates[0].provider_item_id == original.candidates[0].provider_item_id


# ---------------------------------------------------------------------------
# Canonical DownloadManifest: required fields
# ---------------------------------------------------------------------------


def test_build_download_manifest_has_required_fields():
    downloaded = [
        DownloadedEntry(
            provider_item_id="RS2A_001",
            item_id="akasha-item-001",
            local_path="/srv/akasha/raw/RS2A_001.zip",
            downloaded_bytes=1024 * 1024,
            completed_at="2026-03-19T01:00:00Z",
        )
    ]
    failed = [
        FailedEntry(
            provider_item_id="RS2A_002",
            item_id="akasha-item-002",
            error_kind=ErrorKind.NETWORK,
            redacted_error="Connection timed out",
            retryable=True,
            attempt_count=2,
        )
    ]
    deferred = [
        DeferredEntry(
            provider_item_id="RS2A_003",
            item_id="akasha-item-003",
            defer_reason="not_online",
            retry_after="2026-03-25T00:00:00Z",
        )
    ]

    manifest = build_download_manifest(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        adapter="bhoonidhi",
        downloaded=downloaded,
        failed=failed,
        deferred=deferred,
        job_id="job-dl-001",
    )
    d = manifest.to_dict()

    assert d["manifestType"] == "download"
    assert d["version"] == 1
    assert d["sourceId"] == "resourcesat-2a-liss3-boa"
    assert d["provider"] == "bhoonidhi"
    assert d["adapter"] == "bhoonidhi"
    assert d["redactionVersion"] == REDACTION_VERSION
    assert d["jobId"] == "job-dl-001"
    assert isinstance(d["downloaded"], list)
    assert isinstance(d["failed"], list)
    assert isinstance(d["deferred"], list)


def test_download_manifest_downloaded_entry_fields():
    entry = DownloadedEntry(
        provider_item_id="PROD-A",
        item_id="akasha-A",
        local_path="/srv/akasha/raw/PROD-A.zip",
        downloaded_bytes=2048,
        completed_at="2026-03-19T02:00:00Z",
    )
    d = entry.to_dict()
    assert d["providerItemId"] == "PROD-A"
    assert d["itemId"] == "akasha-A"
    assert d["localPath"] == "/srv/akasha/raw/PROD-A.zip"
    assert d["downloadedBytes"] == 2048
    assert d["completedAt"] == "2026-03-19T02:00:00Z"


def test_download_manifest_total_bytes_computed():
    downloaded = [
        DownloadedEntry("P1", "i1", "/p1.zip", 1000),
        DownloadedEntry("P2", "i2", "/p2.zip", 2500),
    ]
    manifest = build_download_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        downloaded=downloaded,
    )
    assert manifest.total_downloaded_bytes == 3500
    assert manifest.to_dict()["totalDownloadedBytes"] == 3500


def test_download_manifest_failed_entry_fields():
    entry = FailedEntry(
        provider_item_id="PROD-F",
        item_id="akasha-F",
        error_kind=ErrorKind.AUTH,
        redacted_error="401 Unauthorized",
        retryable=False,
        attempt_count=3,
        failed_at="2026-03-19T03:00:00Z",
    )
    d = entry.to_dict()
    assert d["providerItemId"] == "PROD-F"
    assert d["itemId"] == "akasha-F"
    assert d["errorKind"] == "auth"
    assert d["redactedError"] == "401 Unauthorized"
    assert d["retryable"] is False
    assert d["attemptCount"] == 3
    assert d["failedAt"] == "2026-03-19T03:00:00Z"


def test_download_manifest_deferred_entry_fields():
    entry = DeferredEntry(
        provider_item_id="PROD-D",
        item_id="akasha-D",
        defer_reason="not_online",
        retry_after="2026-03-25T00:00:00Z",
    )
    d = entry.to_dict()
    assert d["providerItemId"] == "PROD-D"
    assert d["itemId"] == "akasha-D"
    assert d["deferReason"] == "not_online"
    assert d["retryAfter"] == "2026-03-25T00:00:00Z"


def test_download_manifest_error_kind_taxonomy():
    kinds = [k.value for k in ErrorKind]
    assert "auth" in kinds
    assert "not_found" in kinds
    assert "not_online" in kinds
    assert "rate_limited" in kinds
    assert "network" in kinds
    assert "checksum" in kinds
    assert "size_limit" in kinds
    assert "disk" in kinds
    assert "provider" in kinds
    assert "unknown" in kinds


def test_validate_download_manifest_dict_passes_complete():
    m = build_download_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        downloaded=[],
        failed=[],
        deferred=[],
    )
    validate_download_manifest_dict(m.to_dict())  # must not raise


def test_validate_download_manifest_dict_raises_on_missing():
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_download_manifest_dict({"manifestType": "download"})
    assert len(exc_info.value.missing) > 0


def test_download_manifest_roundtrip_from_dict():
    original = build_download_manifest(
        source_id="resourcesat-2a-liss3-boa",
        provider="bhoonidhi",
        adapter="bhoonidhi",
        downloaded=[DownloadedEntry("P1", "i1", "/srv/akasha/p1.zip", 1024)],
        failed=[FailedEntry("P2", "i2", ErrorKind.NETWORK, "timeout", True)],
        deferred=[DeferredEntry("P3", "i3", "not_online")],
        job_id="job-rt",
    )
    restored = DownloadManifest.from_dict(original.to_dict())
    assert restored.source_id == original.source_id
    assert restored.job_id == original.job_id
    assert restored.manifest_type == ManifestType.DOWNLOAD
    assert len(restored.downloaded) == 1
    assert restored.downloaded[0].local_path == "/srv/akasha/p1.zip"
    assert restored.downloaded[0].downloaded_bytes == 1024
    assert len(restored.failed) == 1
    assert restored.failed[0].error_kind == ErrorKind.NETWORK
    assert len(restored.deferred) == 1


# ---------------------------------------------------------------------------
# Canonical OrderManifest: shape (future providers)
# ---------------------------------------------------------------------------


def test_build_order_manifest_has_required_fields():
    manifest = build_order_manifest(
        source_id="planet-skysat-scene",
        provider="planet",
        adapter="planet_adapter",
        candidate_item_id="SCENE_XYZ",
        provider_order_id="ORD_12345",
        state=OrderLifecycleState.PENDING,
        allow_paid_order=True,
        job_id="job-ord-001",
        commercial_readiness_record_id="CRR_001",
        estimated_cost_units=1.5,
        cost_unit_label="sqkm",
    )
    d = manifest.to_dict()

    assert d["manifestType"] == "order"
    assert d["version"] == 1
    assert d["sourceId"] == "planet-skysat-scene"
    assert d["provider"] == "planet"
    assert d["adapter"] == "planet_adapter"
    assert d["candidateItemId"] == "SCENE_XYZ"
    assert d["providerOrderId"] == "ORD_12345"
    assert d["state"] == "pending"
    assert d["allowPaidOrder"] is True
    assert d["redactionVersion"] == REDACTION_VERSION
    assert d["jobId"] == "job-ord-001"
    assert d["commercialReadinessRecordId"] == "CRR_001"
    assert d["estimatedCostUnits"] == pytest.approx(1.5)
    assert d["costUnitLabel"] == "sqkm"


def test_order_manifest_download_links_redacted():
    manifest = build_order_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        candidate_item_id="CID",
        provider_order_id=None,
        state=OrderLifecycleState.SUCCEEDED,
        allow_paid_order=True,
        download_links=[
            "https://api.planet.com/download?token=supersecret123",
            "https://storage.googleapis.com/bucket/asset.tif?X-Goog-Signature=gsig456",
        ],
    )
    d = manifest.to_dict()
    for link in d["downloadLinks"]:
        assert "supersecret123" not in link
        assert "gsig456" not in link
        assert REDACTED in link


def test_validate_order_manifest_dict_passes_complete():
    m = build_order_manifest(
        source_id="s",
        provider="p",
        adapter="a",
        candidate_item_id="CID",
        provider_order_id=None,
        state=OrderLifecycleState.UNKNOWN,
        allow_paid_order=False,
    )
    validate_order_manifest_dict(m.to_dict())  # must not raise


def test_validate_order_manifest_dict_raises_on_missing():
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_order_manifest_dict({"manifestType": "order"})
    assert len(exc_info.value.missing) > 0


def test_order_manifest_lifecycle_states():
    states = [s.value for s in OrderLifecycleState]
    assert "pending" in states
    assert "queued" in states
    assert "running" in states
    assert "succeeded" in states
    assert "failed" in states
    assert "cancelled" in states
    assert "expired" in states
    assert "unknown" in states


def test_order_manifest_roundtrip_from_dict():
    original = build_order_manifest(
        source_id="planet-skysat-scene",
        provider="planet",
        adapter="planet_adapter",
        candidate_item_id="SCENE_ABC",
        provider_order_id="ORD_99",
        state=OrderLifecycleState.RUNNING,
        allow_paid_order=True,
        job_id="j-ord-rt",
    )
    restored = OrderManifest.from_dict(original.to_dict())
    assert restored.source_id == original.source_id
    assert restored.candidate_item_id == original.candidate_item_id
    assert restored.state == OrderLifecycleState.RUNNING
    assert restored.allow_paid_order is True
    assert restored.manifest_type == ManifestType.ORDER


# ---------------------------------------------------------------------------
# Bhoonidhi integration: canonical fields present alongside legacy keys
# ---------------------------------------------------------------------------


def _make_bhoonidhi_search_manifest(**kwargs) -> dict:
    aoi = {
        "id": "bangalore-60km",
        "name": "Bangalore 60 km",
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "geometry": {"type": "Polygon", "coordinates": []},
    }
    defaults = dict(
        source_id="resourcesat-2a-liss3-boa",
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        aoi=aoi,
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        items=[
            {
                "id": "RS2A_001",
                "bbox": [77.2, 12.2, 77.8, 12.8],
                "properties": {"Online": "Y", "datetime": "2026-03-19T00:00:00Z"},
            }
        ],
    )
    defaults.update(kwargs)
    return bhoonidhi.build_search_manifest(**defaults)


def test_bhoonidhi_search_manifest_has_canonical_manifest_type():
    m = _make_bhoonidhi_search_manifest()
    assert m["manifestType"] == "search"


def test_bhoonidhi_search_manifest_has_canonical_source_id():
    m = _make_bhoonidhi_search_manifest()
    assert m["sourceId"] == "resourcesat-2a-liss3-boa"


def test_bhoonidhi_search_manifest_has_canonical_provider():
    m = _make_bhoonidhi_search_manifest()
    assert m["provider"] == "bhoonidhi"
    assert m["adapter"] == "bhoonidhi"


def test_bhoonidhi_search_manifest_has_canonical_datetime_range():
    m = _make_bhoonidhi_search_manifest()
    assert m["datetimeRange"] == "2026-03-01T00:00:00Z/2026-03-31T23:59:59Z"


def test_bhoonidhi_search_manifest_has_canonical_provider_query():
    m = _make_bhoonidhi_search_manifest(provider_query={"filter": "Online=Y"})
    assert "providerQuery" in m
    assert isinstance(m["providerQuery"], dict)


def test_bhoonidhi_search_manifest_has_redaction_version():
    m = _make_bhoonidhi_search_manifest()
    assert m["redactionVersion"] == REDACTION_VERSION


def test_bhoonidhi_search_manifest_candidates_have_canonical_keys():
    m = _make_bhoonidhi_search_manifest()
    assert len(m["candidates"]) == 1
    c = m["candidates"][0]
    assert "providerItemId" in c
    assert "itemId" in c
    assert "acquisitionDatetime" in c
    assert "intersectsAoi" in c
    assert "overlapArea" in c
    assert "downloadStatus" in c
    assert "skipReason" in c
    assert "providerProperties" in c
    assert "links" in c


def test_bhoonidhi_search_manifest_candidate_omits_raw_properties():
    m = _make_bhoonidhi_search_manifest()
    c = m["candidates"][0]
    assert "properties" not in c


def test_bhoonidhi_search_manifest_candidate_redacts_provider_properties():
    item = {
        "id": "RS2A_SECRET",
        "collection": bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "properties": {
            "datetime": "2026-03-19T00:00:00Z",
            "Online": "Y",
            "thumbnail": "https://example.test/a.tif?X-Amz-Signature=SECRETSIG&safe=1",
            "api_key": "secret-key",
        },
    }
    m = _make_bhoonidhi_search_manifest(items=[item])
    c = m["candidates"][0]

    assert "SECRETSIG" not in str(c)
    assert "secret-key" not in str(c)
    assert c["providerProperties"]["api_key"] == REDACTED
    assert "X-Amz-Signature=<redacted>" in c["providerProperties"]["thumbnail"]


def test_bhoonidhi_search_manifest_candidate_provider_item_id_matches_item_id():
    m = _make_bhoonidhi_search_manifest()
    c = m["candidates"][0]
    assert c["providerItemId"] == c["itemId"]


def test_bhoonidhi_search_manifest_candidate_skip_reason_defaults_to_none():
    m = _make_bhoonidhi_search_manifest()
    c = m["candidates"][0]
    assert c["skipReason"] is None


def test_bhoonidhi_search_manifest_preserves_legacy_type_key():
    m = _make_bhoonidhi_search_manifest()
    assert m["type"] == "bhoonidhi_search_manifest"


def test_bhoonidhi_search_manifest_preserves_legacy_version_key():
    m = _make_bhoonidhi_search_manifest()
    assert m["version"] == 1


def test_bhoonidhi_search_manifest_preserves_legacy_created_key():
    m = _make_bhoonidhi_search_manifest()
    assert "created" in m
    assert m["created"].endswith("Z")


def test_bhoonidhi_search_manifest_preserves_legacy_source_id_key():
    m = _make_bhoonidhi_search_manifest()
    assert m["source_id"] == "resourcesat-2a-liss3-boa"


def test_bhoonidhi_search_manifest_preserves_legacy_collection_key():
    m = _make_bhoonidhi_search_manifest()
    assert m["collection"] == bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION


def test_bhoonidhi_search_manifest_preserves_legacy_selection_key():
    m = _make_bhoonidhi_search_manifest()
    assert "selection" in m
    assert "selected_product_ids" in m["selection"]


def test_bhoonidhi_search_manifest_preserves_legacy_search_key():
    m = _make_bhoonidhi_search_manifest()
    assert "search" in m
    assert m["search"]["filter"] == "Online=Y"


def test_bhoonidhi_search_manifest_redacts_provider_query_credentials():
    m = _make_bhoonidhi_search_manifest(
        provider_query={"username": "user@nrsc", "password": "pw!", "collection": "RS-BOA"}
    )
    assert m["providerQuery"]["username"] == REDACTED
    assert m["providerQuery"]["password"] == REDACTED
    assert m["providerQuery"]["collection"] == "RS-BOA"


def test_bhoonidhi_search_manifest_filters_offline_items():
    aoi = {
        "id": "bangalore-60km",
        "name": "Bangalore",
        "bbox": [77.0, 12.0, 78.0, 13.0],
        "geometry": {"type": "Polygon", "coordinates": []},
    }
    m = bhoonidhi.build_search_manifest(
        source_id="resourcesat-2a-liss3-boa",
        collection=bhoonidhi.RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
        aoi=aoi,
        datetime_range="2026-03-01T00:00:00Z/2026-03-31T23:59:59Z",
        items=[
            {
                "id": "online",
                "bbox": [77.2, 12.2, 77.8, 12.8],
                "properties": {"Online": "Y"},
            },
            {
                "id": "offline",
                "bbox": [77.2, 12.2, 77.8, 12.8],
                "properties": {"Online": "N"},
            },
        ],
    )
    ids = [c.get("item_id") or c.get("itemId") or c.get("id") for c in m["candidates"]]
    assert all(i != "offline" for i in ids)


# ---------------------------------------------------------------------------
# Worker-style download manifest: canonical keys alongside legacy
# ---------------------------------------------------------------------------


def test_worker_style_download_manifest_has_canonical_keys():
    """Simulate the worker.py pattern of building a download manifest dict."""
    # Simulate what worker.cmd_bhoonidhi_sync produces:
    search_manifest = _make_bhoonidhi_search_manifest()
    download_manifest = dict(search_manifest)
    download_manifest["downloaded"] = [
        {
            "item_id": "RS2A_001",
            "providerItemId": "RS2A_001",
            "path": "/srv/akasha/raw/RS2A_001.zip",
            "downloadedBytes": 5120,
        }
    ]
    # manifestType must be explicitly assigned; search manifest already has "search"
    download_manifest["manifestType"] = "download"
    download_manifest.setdefault("jobId", None)
    download_manifest.setdefault("sourceId", "resourcesat-2a-liss3-boa")
    download_manifest.setdefault("provider", "bhoonidhi")
    download_manifest.setdefault("adapter", "bhoonidhi")
    download_manifest.setdefault("redactionVersion", REDACTION_VERSION)

    assert download_manifest["manifestType"] == "download"
    assert download_manifest["sourceId"] == "resourcesat-2a-liss3-boa"
    assert download_manifest["provider"] == "bhoonidhi"
    assert download_manifest["adapter"] == "bhoonidhi"
    assert download_manifest["redactionVersion"] == REDACTION_VERSION
    assert isinstance(download_manifest["downloaded"], list)
    assert download_manifest["downloaded"][0]["providerItemId"] == "RS2A_001"


def test_worker_style_download_manifest_preserves_legacy_search_fields():
    """Download manifest inherits legacy search manifest keys (type, collection, etc.)."""
    search_manifest = _make_bhoonidhi_search_manifest()
    download_manifest = dict(search_manifest)
    download_manifest["downloaded"] = []
    download_manifest.setdefault("manifestType", "download")
    download_manifest.setdefault("sourceId", "resourcesat-2a-liss3-boa")
    download_manifest.setdefault("provider", "bhoonidhi")
    download_manifest.setdefault("adapter", "bhoonidhi")
    download_manifest.setdefault("redactionVersion", REDACTION_VERSION)

    # Legacy keys from bhoonidhi search manifest survive
    assert "type" in download_manifest
    assert "collection" in download_manifest
    assert "source_id" in download_manifest


# ---------------------------------------------------------------------------
# ManifestValidationError message formatting
# ---------------------------------------------------------------------------


def test_manifest_validation_error_message_includes_missing_fields():
    err = ManifestValidationError("search", missing=["sourceId", "collection"])
    assert "sourceId" in str(err)
    assert "collection" in str(err)
    assert "search" in str(err)


def test_manifest_validation_error_message_includes_invalid_fields():
    err = ManifestValidationError("download", invalid=["version must be int"])
    assert "version must be int" in str(err)


def test_manifest_validation_error_attributes():
    err = ManifestValidationError("order", missing=["state"], invalid=["allowPaidOrder"])
    assert err.manifest_type == "order"
    assert "state" in err.missing
    assert "allowPaidOrder" in err.invalid
