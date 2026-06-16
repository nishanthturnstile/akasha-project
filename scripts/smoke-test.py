#!/usr/bin/env python3
"""Akasha smoke test — Slice 0 + ISRO product surface.

Ordered checks against a running gateway/deployment:
  Slice 0:  /health, /api/health, /api/_skeleton/*
  Product:  /api/config -> /api/sources -> dates -> /api/layers/default
            -> one ResourceSat FCC tile -> POST /api/indices/statistics

The FCC tile + statistics steps need real COGs in MinIO and a running TiTiler.
Where those are unavailable (e.g. the Emergent preview), the BFF returns a
clean 502/503 and this script reports the step as BLOCKED (not a failure), so
the contract is exercised end-to-end without fabricating raster data.

Usage:
    python scripts/smoke-test.py [BASE_URL] [--require-raster] [--login]
                                 [--require-monitoring-clean]
    BASE_URL env var also supported. Default: http://localhost:8080
    --require-raster (or REQUIRE_RASTER=1) turns BLOCKED tile/stat checks into failures.
    --require-monitoring-clean (or REQUIRE_MONITORING_CLEAN=1) fails if operator
    monitoring reports storage errors, zero-byte COG objects, stale active
    sources, missing active field composites, or tile-unavailable dates.
    --login logs in before product checks using AKASHA_SMOKE_USERNAME and
    AKASHA_SMOKE_PASSWORD, then reuses the session cookie.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.request
from typing import Any
from urllib.error import HTTPError, URLError

KNOWN_FLAGS = {"--require-raster", "--login", "--require-monitoring-clean"}
ARGS = [arg for arg in sys.argv[1:] if arg not in KNOWN_FLAGS]
REQUIRE_RASTER = "--require-raster" in sys.argv[1:] or os.environ.get("REQUIRE_RASTER") == "1"
REQUIRE_MONITORING_CLEAN = (
    "--require-monitoring-clean" in sys.argv[1:]
    or os.environ.get("REQUIRE_MONITORING_CLEAN") == "1"
)
LOGIN = (
    "--login" in sys.argv[1:]
    or os.environ.get("AKASHA_SMOKE_LOGIN") == "1"
    or REQUIRE_MONITORING_CLEAN
)
BASE = (ARGS[0] if ARGS else None) or os.environ.get("BASE_URL", "http://localhost:8080")
BASE = BASE.rstrip("/")

passed = failed = blocked = 0
_COOKIE_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_COOKIE_JAR))

_HEADERS = {
    "Accept": "*/*",
    "User-Agent": "akasha-smoke-test/1.0 (+https://github.com) Mozilla/5.0",
}


def _request(path: str, method: str = "GET", body: dict | None = None, timeout: float = 20.0):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(_HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except HTTPError as exc:  # 4xx/5xx still carry a body
        return exc.code, exc.read()


def check(name: str, path: str, expect_json: bool = False, want_key: str | None = None) -> None:
    global passed, failed
    try:
        status, body = _request(path)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return
    ok = status == 200
    detail = f"HTTP {status}"
    if ok and expect_json:
        try:
            data = json.loads(body)
            if want_key is not None:
                ok = want_key in data if isinstance(data, dict) else bool(data)
                detail += f", has '{want_key}'" if ok else f", missing '{want_key}'"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'v' if ok else 'x'}] {name}: {path} -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


def check_json(name: str, path: str, want_key: str | None = None) -> Any | None:
    global passed, failed
    try:
        status, body = _request(path)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return None
    ok = status == 200
    detail = f"HTTP {status}"
    data: Any | None = None
    if ok:
        try:
            data = json.loads(body)
            if want_key is not None:
                ok = want_key in data if isinstance(data, dict) else bool(data)
                detail += f", has '{want_key}'" if ok else f", missing '{want_key}'"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'v' if ok else 'x'}] {name}: {path} -> {detail}")
    if ok:
        passed += 1
        return data
    failed += 1
    return None


def check_monitoring_contract() -> None:
    """Validate the authenticated operator monitoring payload used for deploy gates."""
    global passed, failed
    path = "/api/monitoring/imagery-sources"
    try:
        status, body = _request(path)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] imagery source monitoring: {path} -> ERROR ({exc})")
        failed += 1
        return

    ok = status == 200
    detail = f"HTTP {status}"
    data: dict | None = None
    if ok:
        try:
            parsed = json.loads(body)
            data = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"

    if ok and data is not None:
        contract_errors = _monitoring_contract_errors(data)
        if contract_errors:
            ok = False
            detail += ", contract: " + "; ".join(contract_errors[:3])
        else:
            storage = data.get("storage", {})
            zero_count = storage.get("zeroByteObjectCount")
            storage_status = storage.get("status")
            source_count = len(data.get("sources", []))
            detail += f", sources={source_count}, storage={storage_status}, zero-byte={zero_count}"
            if REQUIRE_MONITORING_CLEAN:
                cleanliness_errors = _monitoring_cleanliness_errors(data)
                if cleanliness_errors:
                    ok = False
                    detail += ", clean gate: " + "; ".join(cleanliness_errors[:3])

    print(f"  [{'v' if ok else 'x'}] imagery source monitoring: {path} -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


def _monitoring_contract_errors(data: dict) -> list[str]:
    errors: list[str] = []
    sources = data.get("sources")
    ledger = data.get("ingestionLedger")
    storage = data.get("storage")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
    if not isinstance(ledger, dict):
        errors.append("ingestionLedger must be an object")
    if not isinstance(storage, dict):
        errors.append("storage must be an object")
        return errors

    if "zeroByteObjectCount" not in storage:
        errors.append("storage.zeroByteObjectCount missing")
    by_prefix = storage.get("byPrefix")
    if not isinstance(by_prefix, list):
        errors.append("storage.byPrefix must be a list")
    else:
        for index, entry in enumerate(by_prefix):
            if not isinstance(entry, dict):
                errors.append(f"storage.byPrefix[{index}] must be an object")
                continue
            if "zeroByteObjectCount" not in entry:
                errors.append(f"storage.byPrefix[{index}].zeroByteObjectCount missing")

    if isinstance(sources, list):
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"sources[{index}] must be an object")
                continue
            if not isinstance(source.get("latestSuccessfulComposites"), list):
                errors.append(f"sources[{index}].latestSuccessfulComposites missing/list")
            if not isinstance(source.get("tileUnavailableReasons"), list):
                errors.append(f"sources[{index}].tileUnavailableReasons missing/list")
    return errors


def _monitoring_cleanliness_errors(data: dict) -> list[str]:
    errors: list[str] = []
    storage = data.get("storage", {})
    status = storage.get("status")
    zero_count = storage.get("zeroByteObjectCount")
    if status not in {"ok", "disabled"}:
        errors.append(f"storage status is {status!r}")
    if isinstance(zero_count, int) and zero_count > 0:
        errors.append(f"{zero_count} zero-byte storage object(s)")

    for source in data.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("sourceId") or "unknown-source")
        if source.get("availabilityStatus") == "gated":
            continue
        if source.get("lastError"):
            errors.append(f"{source_id} monitoring error")
        if source.get("isStale"):
            errors.append(f"{source_id} latest catalog date is stale")
        if source.get("isSuccessfulCompositeStale"):
            errors.append(f"{source_id} latest successful composite is stale")
        if (
            source.get("kind") == "optical"
            and source.get("analysisLevel") == "field"
            and not source.get("latestSuccessfulCompositeDate")
        ):
            errors.append(f"{source_id} has no successful composite")
        tile_reasons = [
            str(reason).strip()
            for reason in source.get("tileUnavailableReasons", [])
            if str(reason).strip()
        ]
        if tile_reasons:
            errors.append(f"{source_id} tile unavailable: {tile_reasons[0]}")
    return errors


def check_allow_blocked(
    name: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    ok_statuses=(200, 204),
    blocked_statuses=(502, 503),
) -> None:
    """Pass on render success; report BLOCKED (not fail) when COGs/TiTiler absent."""
    global passed, failed, blocked
    try:
        status, payload = _request(path, method=method, body=body)
    except (URLError, TimeoutError) as exc:
        print(f"  [x] {name}: {path} -> ERROR ({exc})")
        failed += 1
        return
    if status in ok_statuses:
        print(f"  [v] {name}: {path} -> HTTP {status}")
        passed += 1
    elif status in blocked_statuses:
        code = ""
        try:
            code = json.loads(payload).get("error", {}).get("code", "")
        except Exception:  # noqa: BLE001
            pass
        if REQUIRE_RASTER:
            print(
                f"  [x] {name}: {path} -> HTTP {status} {code} "
                "(raster required; needs real COGs/MinIO/TiTiler)"
            )
            failed += 1
        else:
            print(
                f"  [-] BLOCKED {name}: {path} -> HTTP {status} {code} "
                "(needs real COGs/MinIO/TiTiler)"
            )
            blocked += 1
    else:
        print(f"  [x] {name}: {path} -> HTTP {status}")
        failed += 1


def check_blocked_or_fail(name: str, detail: str) -> None:
    global failed, blocked
    if REQUIRE_RASTER:
        print(f"  [x] {name}: {detail}")
        failed += 1
    else:
        print(f"  [-] BLOCKED {name}: {detail}")
        blocked += 1


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def login() -> None:
    """Authenticate once and keep the session cookie in the global opener."""
    global passed, failed
    username = os.environ.get("AKASHA_SMOKE_USERNAME", "").strip()
    password = os.environ.get("AKASHA_SMOKE_PASSWORD", "")
    remember_me = _bool_env("AKASHA_SMOKE_REMEMBER_ME")
    if not username or not password:
        print(
            "  [x] login: AKASHA_SMOKE_USERNAME and AKASHA_SMOKE_PASSWORD "
            "are required when --login is used"
        )
        failed += 1
        return
    try:
        status, body = _request(
            "/api/auth/login",
            method="POST",
            body={"username": username, "password": password, "rememberMe": remember_me},
        )
    except (URLError, TimeoutError) as exc:
        print(f"  [x] login: /api/auth/login -> ERROR ({exc})")
        failed += 1
        return
    ok = status == 200
    detail = f"HTTP {status}"
    if ok:
        try:
            data = json.loads(body)
            ok = isinstance(data, dict) and "user" in data and "currentTeam" in data
            detail += ", session cookie captured" if ok else ", unexpected response JSON"
        except json.JSONDecodeError:
            ok = False
            detail += ", invalid JSON"
    print(f"  [{'v' if ok else 'x'}] login: /api/auth/login -> {detail}")
    if ok:
        passed += 1
    else:
        failed += 1


IN_FOOTPRINT_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [77.55, 12.95],
            [77.552, 12.95],
            [77.552, 12.952],
            [77.55, 12.952],
            [77.55, 12.95],
        ]
    ],
}


def main() -> int:
    global passed, failed, blocked
    passed = failed = blocked = 0

    print("=" * 64)
    print(f" Akasha smoke test — Slice 0 + ISRO product   base: {BASE}")
    print("=" * 64)

    print("\n> Slice 0 endpoints (must pass)")
    check("web/gateway health", "/health")
    check("api health (proxied)", "/api/health", expect_json=True, want_key="status")
    check("skeleton services", "/api/_skeleton/services", expect_json=True, want_key="services")
    check(
        "skeleton manifest",
        "/api/_skeleton/manifest",
        expect_json=True,
        want_key="pinnedImages",
    )

    if LOGIN:
        print("\n> Authentication (--login)")
        login()

    print("\n> Product endpoints (must pass)")
    check("config", "/api/config", expect_json=True, want_key="supportedIndices")
    check("sources", "/api/sources", expect_json=True, want_key="0")  # non-empty list
    check("dates", "/api/sources/resourcesat-2a-liss3-boa/dates", expect_json=True, want_key="0")
    default_layer = check_json("default layer", "/api/layers/default", want_key="tileUrlTemplate")

    if LOGIN:
        print("\n> Operator monitoring (--login)")
        check_monitoring_contract()

    print("\n> Raster path (pass on render; BLOCKED without real COGs/TiTiler)")
    default_source = (
        default_layer.get("sourceId") if isinstance(default_layer, dict) else None
    ) or "resourcesat-2a-liss3-boa"
    default_date = default_layer.get("acquisitionDate") if isinstance(default_layer, dict) else None
    tile_template = (
        default_layer.get("tileUrlTemplate") if isinstance(default_layer, dict) else None
    )
    if isinstance(tile_template, str) and default_date:
        tile_path = tile_template.replace("{z}", "8").replace("{x}", "183").replace("{y}", "118")
        check_allow_blocked("default fcc tile", tile_path)
    else:
        check_blocked_or_fail(
            "default fcc tile",
            "default layer did not provide acquisitionDate and tileUrlTemplate",
        )
    check_allow_blocked(
        "index statistics",
        "/api/indices/statistics",
        method="POST",
        body={
            "geometry": IN_FOOTPRINT_POLY,
            "sourceId": default_source,
            "acquisitionDate": default_date,
            "indexType": "NDVI",
        },
    )

    print("\n" + "-" * 64)
    print(f" PASSED: {passed}   FAILED: {failed}   BLOCKED: {blocked}")
    print("-" * 64)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
